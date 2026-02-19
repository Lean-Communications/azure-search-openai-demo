"""
Azure Function: Document Ingester
Receives documents from Logic Apps, extracts text/images, embeds, and pushes to Azure AI Search.
"""

import asyncio
import io
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote

import httpx

import azure.functions as func
from azure.core.exceptions import HttpResponseError
from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential

from prepdocslib.blobmanager import BlobManager
from prepdocslib.embeddings import OpenAIEmbeddings
from prepdocslib.figureprocessor import FigureProcessor, process_page_image
from prepdocslib.fileprocessor import FileProcessor
from prepdocslib.listfilestrategy import File
from prepdocslib.page import Page
from prepdocslib.searchmanager import SearchManager, Section
from prepdocslib.servicesetup import (
    OpenAIHost,
    build_file_processors,
    select_processor_for_filename,
    setup_blob_manager,
    setup_embeddings_service,
    setup_figure_processor,
    setup_image_embeddings_service,
    setup_openai_client,
    setup_search_info,
)
from prepdocslib.strategy import SearchInfo
from prepdocslib.textprocessor import process_text
from prepdocslib.textsplitter import SentenceTextSplitter

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

logger = logging.getLogger(__name__)


@dataclass
class GlobalSettings:
    file_processors: dict[str, FileProcessor]
    azure_credential: ManagedIdentityCredential
    blob_manager: BlobManager
    embeddings: OpenAIEmbeddings
    figure_processor: Optional[FigureProcessor]
    image_embeddings: object  # Optional[ImageEmbeddings]
    use_multimodal: bool
    search_info: SearchInfo
    search_manager: SearchManager
    splitter: SentenceTextSplitter
    field_name_embedding: str


settings: GlobalSettings | None = None
_index_ensured = False


async def download_from_sharepoint(drive_id: str, item_id: str) -> bytes | None:
    """Download a file from SharePoint via Microsoft Graph API.

    Uses the function's managed identity to authenticate. Graph's /content
    endpoint returns a 302 redirect to the actual download URL.
    """
    if settings is None:
        return None

    token = settings.azure_credential.get_token("https://graph.microsoft.com/.default")
    access_token = (await token).token

    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content"
    logger.info("Downloading drive=%s item=%s from SharePoint via Graph API", drive_id, item_id)

    async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        if resp.status_code != 200:
            logger.error("Graph API download failed: %s %s", resp.status_code, resp.text[:500])
            return None

    logger.info("Downloaded %d bytes from SharePoint", len(resp.content))
    return resp.content


def configure_global_settings():
    global settings

    # Credential — use ManagedIdentity in Azure, DefaultAzureCredential locally
    running_in_production = os.getenv("RUNNING_IN_PRODUCTION", "false").lower() == "true"
    if running_in_production:
        if AZURE_CLIENT_ID := os.getenv("AZURE_CLIENT_ID"):
            logger.info("Using Managed Identity with client ID: %s", AZURE_CLIENT_ID)
            azure_credential = ManagedIdentityCredential(client_id=AZURE_CLIENT_ID)
        else:
            logger.info("Using default Managed Identity without client ID")
            azure_credential = ManagedIdentityCredential()
    else:
        logger.info("Using DefaultAzureCredential for local development")
        azure_credential = DefaultAzureCredential()

    # Environment
    openai_host = OpenAIHost(os.getenv("OPENAI_HOST", "azure"))
    use_multimodal = os.getenv("USE_MULTIMODAL", "false").lower() == "true"
    use_content_understanding = os.getenv("USE_MEDIA_DESCRIBER_AZURE_CU", "false").lower() == "true"
    content_understanding_endpoint = os.getenv("AZURE_CONTENTUNDERSTANDING_ENDPOINT")
    vision_endpoint = os.getenv("AZURE_VISION_ENDPOINT")
    document_intelligence_service = os.getenv("AZURE_DOCUMENTINTELLIGENCE_SERVICE")
    storage_account = os.getenv("AZURE_CLOUD_INGESTION_STORAGE_ACCOUNT") or os.environ["AZURE_STORAGE_ACCOUNT"]
    storage_container = os.environ["AZURE_STORAGE_CONTAINER"]
    image_storage_container = os.getenv("AZURE_IMAGESTORAGE_CONTAINER", "images")
    search_service = os.environ["AZURE_SEARCH_SERVICE"]
    search_index = os.environ["AZURE_SEARCH_INDEX"]
    field_name_embedding = os.getenv("AZURE_SEARCH_FIELD_NAME_EMBEDDING", "embedding")
    emb_model_name = os.getenv("AZURE_OPENAI_EMB_MODEL_NAME", "text-embedding-3-large")
    emb_dimensions = int(os.getenv("AZURE_OPENAI_EMB_DIMENSIONS", "3072"))
    emb_deployment = os.getenv("AZURE_OPENAI_EMB_DEPLOYMENT", emb_model_name)
    openai_service = os.getenv("AZURE_OPENAI_SERVICE")
    chatgpt_model = os.getenv("AZURE_OPENAI_CHATGPT_MODEL", "gpt-4o")
    chatgpt_deployment = os.getenv("AZURE_OPENAI_CHATGPT_DEPLOYMENT", chatgpt_model)
    # Use gpt-4o-mini for figure descriptions — much faster and cheaper than gpt-4o
    figure_model = os.getenv("AZURE_OPENAI_FIGURE_MODEL", "gpt-4o-mini")
    figure_deployment = os.getenv("AZURE_OPENAI_FIGURE_DEPLOYMENT", figure_model)

    # OpenAI client
    azure_openai_custom_url = os.getenv("AZURE_OPENAI_CUSTOM_URL")
    openai_client, azure_openai_endpoint = setup_openai_client(
        openai_host=openai_host,
        azure_credential=azure_credential,
        azure_openai_service=openai_service,
        azure_openai_custom_url=azure_openai_custom_url,
        azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY_OVERRIDE"),
    )

    # For azure_custom, derive endpoint from the custom URL (strip /openai/v1 suffix)
    if azure_openai_endpoint is None and azure_openai_custom_url:
        from urllib.parse import urlparse
        parsed = urlparse(azure_openai_custom_url)
        azure_openai_endpoint = f"{parsed.scheme}://{parsed.netloc}"

    # Always extract figures from documents (images are uploaded to blob for UI display).
    # When multimodal is enabled, GPT-4o descriptions are skipped — multimodal embeddings
    # handle retrieval directly. Otherwise, figures are described and embedded as text.
    process_figures = True

    # File processors (parsers)
    file_processors = build_file_processors(
        azure_credential=azure_credential,
        document_intelligence_service=document_intelligence_service,
        document_intelligence_key=None,
        use_local_pdf_parser=os.getenv("USE_LOCAL_PDF_PARSER", "false").lower() == "true",
        use_local_html_parser=os.getenv("USE_LOCAL_HTML_PARSER", "false").lower() == "true",
        process_figures=process_figures,
    )

    # Figure processor — uses gpt-4o-mini for fast image descriptions
    figure_processor = setup_figure_processor(
        credential=azure_credential,
        use_multimodal=True,
        use_content_understanding=use_content_understanding,
        content_understanding_endpoint=content_understanding_endpoint,
        openai_client=openai_client,
        openai_model=figure_model,
        openai_deployment=figure_deployment,
    )

    # Blob manager (for uploading extracted images)
    blob_manager = setup_blob_manager(
        azure_credential=azure_credential,
        storage_account=storage_account,
        storage_container=storage_container,
        storage_resource_group=os.getenv("AZURE_STORAGE_RESOURCE_GROUP"),
        subscription_id=os.getenv("AZURE_SUBSCRIPTION_ID"),
        image_storage_container=image_storage_container,
    )

    # Embeddings
    embeddings = setup_embeddings_service(
        openai_host=openai_host,
        open_ai_client=openai_client,
        emb_model_name=emb_model_name,
        emb_model_dimensions=emb_dimensions,
        azure_openai_deployment=emb_deployment,
        azure_openai_endpoint=azure_openai_endpoint,
    )

    # Image embeddings (multimodal)
    image_embeddings = setup_image_embeddings_service(
        azure_credential=azure_credential,
        vision_endpoint=vision_endpoint,
        use_multimodal=use_multimodal,
    )

    # Search
    search_info = setup_search_info(
        search_service=search_service,
        index_name=search_index,
        azure_credential=azure_credential,
        azure_openai_endpoint=azure_openai_endpoint,
        azure_vision_endpoint=vision_endpoint,
    )

    search_manager = SearchManager(
        search_info=search_info,
        embeddings=embeddings,
        field_name_embedding=field_name_embedding,
        search_images=use_multimodal,
    )

    settings = GlobalSettings(
        file_processors=file_processors,
        azure_credential=azure_credential,
        blob_manager=blob_manager,
        embeddings=embeddings,
        figure_processor=figure_processor,
        image_embeddings=image_embeddings,
        use_multimodal=use_multimodal,
        search_info=search_info,
        search_manager=search_manager,
        splitter=SentenceTextSplitter(),
        field_name_embedding=field_name_embedding,
    )


@app.function_name(name="ingest")
@app.route(route="ingest", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def ingest_document(req: func.HttpRequest) -> func.HttpResponse:
    """
    Ingest a single document from Logic Apps.

    Headers:
        X-Filename: Original filename (e.g. slides.pptx)
        X-Source-Url: Optional source URL for the document
        X-Drive-Id: SharePoint drive ID (used when body is empty)
        X-Drive-Item-Id: SharePoint drive item ID (used when body is empty)
    Body:
        Raw file bytes (optional if drive headers are provided)
    """
    if settings is None:
        return func.HttpResponse(
            json.dumps({"error": "Settings not initialized"}),
            mimetype="application/json",
            status_code=500,
        )

    global _index_ensured
    if not _index_ensured:
        await settings.search_manager.create_index()
        _index_ensured = True

    raw_filename = req.headers.get("X-Filename")
    if not raw_filename:
        return func.HttpResponse(
            json.dumps({"error": "X-Filename header is required"}),
            mimetype="application/json",
            status_code=400,
        )
    filename = unquote(raw_filename)

    source_url = req.headers.get("X-Source-Url")
    document_bytes = req.get_body()

    if not document_bytes:
        drive_id = req.headers.get("X-Drive-Id")
        drive_item_id = req.headers.get("X-Drive-Item-Id")
        if drive_id and drive_item_id:
            document_bytes = await download_from_sharepoint(drive_id, drive_item_id)
            if not document_bytes:
                return func.HttpResponse(
                    json.dumps({"error": "Failed to download file from SharePoint via Graph API"}),
                    mimetype="application/json",
                    status_code=502,
                )
        else:
            return func.HttpResponse(
                json.dumps({"error": "Request body is empty and X-Drive-Id/X-Drive-Item-Id headers are missing"}),
                mimetype="application/json",
                status_code=400,
            )

    try:
        chunks_indexed = await process_and_index_document(filename, document_bytes, source_url)
        return func.HttpResponse(
            json.dumps({"status": "success", "filename": filename, "chunks_indexed": chunks_indexed}),
            mimetype="application/json",
            status_code=200,
        )
    except ValueError as e:
        logger.error("Validation error for %s: %s", filename, str(e))
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=400,
        )
    except Exception as e:
        logger.error("Error processing %s: %s", filename, str(e), exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500,
        )


async def process_and_index_document(filename: str, document_bytes: bytes, source_url: str | None = None) -> int:
    """Parse, describe figures, chunk, embed, and push a document to Azure AI Search."""
    if settings is None:
        raise RuntimeError("Global settings not initialized")

    # 1. Select parser
    file_processor = select_processor_for_filename(filename, settings.file_processors)
    parser = file_processor.parser

    # 2. Parse document
    document_stream = io.BytesIO(document_bytes)
    document_stream.name = filename
    pages: list[Page] = []
    try:
        pages = [page async for page in parser.parse(content=document_stream)]
    except HttpResponseError as exc:
        raise ValueError(f"Parser failed for {filename}: {exc.message}") from exc
    finally:
        document_stream.close()

    if not pages:
        logger.warning("No pages extracted from %s", filename)
        return 0

    # 2.5. Extract embedded images from Office documents (PPTX/DOCX)
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".pptx", ".docx"):
        from prepdocslib.officeimageextractor import extract_and_merge_office_images

        extract_and_merge_office_images(filename, document_bytes, pages)

    # 3. Process figures (upload to blob + describe + embed) — parallelized
    # Always generate GPT-4o descriptions so images are findable via text search.
    # When multimodal is also enabled, images additionally get visual embeddings.
    all_images = [image for page in pages for image in page.images]
    if all_images:
        sem = asyncio.Semaphore(30)

        async def _process(img):
            async with sem:
                return await process_page_image(
                    image=img,
                    document_filename=filename,
                    blob_manager=settings.blob_manager,
                    image_embeddings_client=settings.image_embeddings,
                    figure_processor=settings.figure_processor,
                )

        logger.info("Processing %d figures concurrently for %s", len(all_images), filename)
        await asyncio.gather(*[_process(img) for img in all_images])

    # 4. Chunk text (combines text with figure descriptions, then splits)
    file_obj = File(content=io.BytesIO(document_bytes))
    file_obj.content.name = filename
    sections = process_text(
        pages=pages,
        file=file_obj,
        splitter=settings.splitter,
    )

    if not sections:
        logger.warning("No sections produced from %s", filename)
        return 0

    # 5. Remove old chunks for this file (avoids stale orphans on re-ingestion)
    await settings.search_manager.remove_content(path=filename)

    # 6. Embed and push to search index
    await settings.search_manager.update_content(sections, url=source_url)

    return len(sections)


@app.function_name(name="setup")
@app.route(route="setup", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def setup_index(req: func.HttpRequest) -> func.HttpResponse:
    """
    Create or update the Azure AI Search index.
    Idempotent — safe to call multiple times.
    """
    if settings is None:
        return func.HttpResponse(
            json.dumps({"error": "Settings not initialized"}),
            mimetype="application/json",
            status_code=500,
        )

    try:
        await settings.search_manager.create_index()
        return func.HttpResponse(
            json.dumps({"status": "success", "index": settings.search_info.index_name}),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as e:
        logger.error("Error creating index: %s", str(e), exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500,
        )


@app.function_name(name="store")
@app.route(route="store", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def store_document(req: func.HttpRequest) -> func.HttpResponse:
    """
    Lightweight endpoint: download from SharePoint and upload to blob storage.
    No parsing or processing — the Azure AI Search indexer handles that.

    Headers:
        X-Filename: Original filename (e.g. slides.pptx)
        X-Drive-Id: SharePoint drive ID
        X-Drive-Item-Id: SharePoint drive item ID
    Body:
        Raw file bytes (optional if drive headers are provided)
    """
    if settings is None:
        return func.HttpResponse(
            json.dumps({"error": "Settings not initialized"}),
            mimetype="application/json",
            status_code=500,
        )

    raw_filename = req.headers.get("X-Filename")
    if not raw_filename:
        return func.HttpResponse(
            json.dumps({"error": "X-Filename header is required"}),
            mimetype="application/json",
            status_code=400,
        )
    filename = unquote(raw_filename)

    document_bytes = req.get_body()

    if not document_bytes:
        drive_id = req.headers.get("X-Drive-Id")
        drive_item_id = req.headers.get("X-Drive-Item-Id")
        if drive_id and drive_item_id:
            document_bytes = await download_from_sharepoint(drive_id, drive_item_id)
            if not document_bytes:
                return func.HttpResponse(
                    json.dumps({"error": "Failed to download file from SharePoint via Graph API"}),
                    mimetype="application/json",
                    status_code=502,
                )
        else:
            return func.HttpResponse(
                json.dumps({"error": "Request body is empty and X-Drive-Id/X-Drive-Item-Id headers are missing"}),
                mimetype="application/json",
                status_code=400,
            )

    try:
        container_client = settings.blob_manager.blob_service_client.get_container_client(
            os.environ["AZURE_STORAGE_CONTAINER"]
        )
        await container_client.upload_blob(name=filename, data=document_bytes, overwrite=True)
        logger.info("Stored %s (%d bytes) in blob storage", filename, len(document_bytes))
        return func.HttpResponse(
            json.dumps({"status": "stored", "filename": filename, "size": len(document_bytes)}),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as e:
        logger.error("Error storing %s: %s", filename, str(e), exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500,
        )


# Initialize settings at module load time, unless we're in a test environment
if os.environ.get("PYTEST_CURRENT_TEST") is None:
    try:
        configure_global_settings()
    except KeyError as e:
        logger.warning("Could not initialize settings at module load time: %s", e)
