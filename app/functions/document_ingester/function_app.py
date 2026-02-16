"""
Azure Function: Document Ingester
Receives documents from Logic Apps, extracts text/images, embeds, and pushes to Azure AI Search.
"""

import io
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote

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
    search_info: SearchInfo
    search_manager: SearchManager
    splitter: SentenceTextSplitter
    field_name_embedding: str


settings: GlobalSettings | None = None
_index_ensured = False


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

    # Always extract and describe figures from documents using GPT-4o.
    # This is independent of USE_MULTIMODAL (which controls image *vector* embeddings in search).
    # Figures are described as text, embedded as text, and the images stored in blob storage.
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

    # Figure processor — always use GPT-4o to describe extracted figures
    figure_processor = setup_figure_processor(
        credential=azure_credential,
        use_multimodal=True,
        use_content_understanding=use_content_understanding,
        content_understanding_endpoint=content_understanding_endpoint,
        openai_client=openai_client,
        openai_model=chatgpt_model,
        openai_deployment=chatgpt_deployment,
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

    # Search
    search_info = setup_search_info(
        search_service=search_service,
        index_name=search_index,
        azure_credential=azure_credential,
        azure_openai_endpoint=azure_openai_endpoint,
    )

    search_manager = SearchManager(
        search_info=search_info,
        embeddings=embeddings,
        field_name_embedding=field_name_embedding,
        search_images=False,
    )

    settings = GlobalSettings(
        file_processors=file_processors,
        azure_credential=azure_credential,
        blob_manager=blob_manager,
        embeddings=embeddings,
        figure_processor=figure_processor,
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
    Body:
        Raw file bytes
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
        return func.HttpResponse(
            json.dumps({"error": "Request body is empty"}),
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

    # 3. Process figures (describe with GPT-4o, upload to blob)
    for page in pages:
        for image in page.images:
            await process_page_image(
                image=image,
                document_filename=filename,
                blob_manager=settings.blob_manager,
                image_embeddings_client=None,
                figure_processor=settings.figure_processor,
            )

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


# Initialize settings at module load time, unless we're in a test environment
if os.environ.get("PYTEST_CURRENT_TEST") is None:
    try:
        configure_global_settings()
    except KeyError as e:
        logger.warning("Could not initialize settings at module load time: %s", e)
