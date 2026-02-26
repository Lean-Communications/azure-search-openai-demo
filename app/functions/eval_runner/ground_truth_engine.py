"""
Ground truth generation engine for the eval_runner Azure Function.

Adapted from evals/generate_ground_truth.py to use blob storage instead of local files.
Fetches document chunks from Azure AI Search, builds a RAGAS knowledge graph,
generates Q&A pairs, and stores results in blob storage.
"""

import json
import logging
import os
import re
import sys
import tempfile
import types

# Azure Functions worker doesn't have a __main__ module, but dill (a transitive
# dependency of ragas via datasets) requires it. Provide a dummy module.
if "__main__" not in sys.modules:
    sys.modules["__main__"] = types.ModuleType("__main__")

# Allow RAGAS to use asyncio inside the Azure Functions worker event loop.
# Without this, RAGAS's internal asyncio.run() calls would fail with
# "Cannot run the event loop while another one is running".
import nest_asyncio

nest_asyncio.apply()

from azure.search.documents import SearchClient
from azure.storage.blob import BlobServiceClient
from langchain_core.documents import Document as LCDocument
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.testset import TestsetGenerator
from ragas.testset.graph import KnowledgeGraph, Node, NodeType
from ragas.testset.transforms import apply_transforms, default_transforms

logger = logging.getLogger("eval_runner.ground_truth")


def _get_search_documents(
    search_service: str,
    search_index: str,
    credential,
    num_search_documents: int | None = None,
) -> list[dict]:
    """Fetch all document chunks from Azure AI Search (sync SDK)."""
    search_client = SearchClient(
        endpoint=f"https://{search_service}.search.windows.net",
        index_name=search_index,
        credential=credential,
    )
    all_documents = []
    top = num_search_documents or 100000
    logger.info("Fetching up to %d document chunks from index '%s'", top, search_index)
    response = search_client.search(search_text="*", top=top).by_page()
    for page in response:
        all_documents.extend(list(page))
    logger.info("Fetched %d document chunks", len(all_documents))
    return all_documents


def _build_openai_components(credential, azure_endpoint: str):
    """Build LangChain-wrapped LLM and embeddings for RAGAS."""
    from azure.identity import get_bearer_token_provider

    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
    token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")

    llm = LangchainLLMWrapper(
        AzureChatOpenAI(
            openai_api_version=api_version,
            azure_endpoint=azure_endpoint,
            azure_ad_token_provider=token_provider,
            azure_deployment=os.getenv("AZURE_OPENAI_EVAL_DEPLOYMENT", "eval"),
            model=os.environ.get("AZURE_OPENAI_EVAL_MODEL", "gpt-4o"),
            validate_base_url=False,
        )
    )
    embeddings = LangchainEmbeddingsWrapper(
        AzureOpenAIEmbeddings(
            openai_api_version=api_version,
            azure_endpoint=azure_endpoint,
            azure_ad_token_provider=token_provider,
            azure_deployment=os.getenv("AZURE_OPENAI_EMB_DEPLOYMENT", "text-embedding-3-large"),
            model=os.environ.get("AZURE_OPENAI_EMB_MODEL_NAME", "text-embedding-3-large"),
        )
    )
    return llm, embeddings


async def generate_ground_truth(
    credential,
    sync_credential,
    num_questions: int = 200,
    num_search_documents: int | None = None,
) -> int:
    """
    Generate ground truth Q&A pairs and store in blob storage.

    Uses nest_asyncio to allow RAGAS's internal asyncio calls to run inside
    the Azure Functions worker event loop. All work stays on the main thread
    so Flex Consumption correctly tracks the invocation as active.

    Returns the number of Q&A pairs generated.
    """
    storage_account = os.environ["AZURE_STORAGE_ACCOUNT"]
    container_name = os.getenv("EVAL_BLOB_CONTAINER", "eval-data")
    search_service = os.environ["AZURE_SEARCH_SERVICE"]
    search_index = os.environ["AZURE_SEARCH_INDEX"]

    azure_openai_custom_url = os.getenv("AZURE_OPENAI_CUSTOM_URL")
    if azure_openai_custom_url:
        from urllib.parse import urlparse

        parsed = urlparse(azure_openai_custom_url)
        azure_endpoint = f"{parsed.scheme}://{parsed.netloc}"
    else:
        azure_endpoint = f"https://{os.getenv('AZURE_OPENAI_SERVICE')}.openai.azure.com"

    # Fetch documents from search (sync SDK)
    search_docs = _get_search_documents(search_service, search_index, sync_credential, num_search_documents)
    if not search_docs:
        logger.warning("No documents found in search index '%s'", search_index)
        return 0

    # Build knowledge graph
    content_field = os.getenv("KB_FIELDS_CONTENT", "content")
    sourcepage_field = os.getenv("KB_FIELDS_SOURCEPAGE", "sourcepage")

    logger.info("Building knowledge graph nodes from %d documents", len(search_docs))
    nodes = []
    for doc in search_docs:
        content = doc[content_field]
        citation = doc.get(sourcepage_field) or doc.get("chunk_id") or doc.get("id", "unknown")
        node = Node(
            type=NodeType.DOCUMENT,
            properties={
                "page_content": f"[[{citation}]]: {content}",
                "document_metadata": {"citation": citation},
            },
        )
        nodes.append(node)

    kg = KnowledgeGraph(nodes=nodes)
    logger.info("Knowledge graph created with %d nodes", len(nodes))

    try:
        llm, embeddings = _build_openai_components(sync_credential, azure_endpoint)
        logger.info("OpenAI components built (endpoint=%s)", azure_endpoint)
    except Exception as e:
        logger.error("Failed to build OpenAI components: %s", e, exc_info=True)
        raise

    # Run RAGAS transforms — nest_asyncio allows RAGAS's internal asyncio.run()
    # to work inside the already-running Azure Functions event loop.
    try:
        logger.info("Applying RAGAS transforms to knowledge graph with %d nodes", len(nodes))
        transforms = default_transforms(
            documents=[LCDocument(page_content=doc[content_field]) for doc in search_docs],
            llm=llm,
            embedding_model=embeddings,
        )
        apply_transforms(kg, transforms)
        logger.info("RAGAS transforms applied successfully")
    except Exception as e:
        logger.error("Failed during RAGAS transforms: %s", e, exc_info=True)
        raise

    # Generate Q&A pairs in Norwegian
    try:
        from ragas.testset.synthesizers.single_hop.specific import SingleHopSpecificQuerySynthesizer

        logger.info("Adapting RAGAS prompts for Norwegian")
        query_synthesizer = SingleHopSpecificQuerySynthesizer(llm=llm)
        adapted_prompts = await query_synthesizer.adapt_prompts("norwegian", llm=llm)
        query_synthesizer.set_prompts(**adapted_prompts)

        logger.info("Generating %d questions with RAGAS (Norwegian)", num_questions)
        generator = TestsetGenerator(llm=llm, embedding_model=embeddings, knowledge_graph=kg)
        dataset = generator.generate(
            testset_size=num_questions,
            query_distribution=[(query_synthesizer, 1.0)],
            with_debugging_logs=True,
        )
        logger.info("RAGAS generated %d samples", len(dataset.samples))
    except Exception as e:
        logger.error("Failed during RAGAS generation: %s", e, exc_info=True)
        raise

    # Extract Q&A pairs
    qa_pairs = []
    for sample in dataset.samples:
        question = sample.eval_sample.user_input
        truth = sample.eval_sample.reference
        citations = []
        for context in sample.eval_sample.reference_contexts:
            match = re.search(r"\[\[(.*?)\]\]", context)
            if match:
                citations.append(f"[{match.group(1)}]")
        truth += " " + " ".join(citations)
        qa_pairs.append({"question": question, "truth": truth})

    logger.info("Extracted %d Q&A pairs", len(qa_pairs))

    # Store in blob storage (sync SDK to stay on main thread)
    blob_service_url = f"https://{storage_account}.blob.core.windows.net"
    blob_service = BlobServiceClient(blob_service_url, credential=sync_credential)
    container_client = blob_service.get_container_client(container_name)

    try:
        container_client.create_container()
    except Exception:
        pass  # Container already exists

    # Upload ground truth JSONL
    gt_content = "\n".join(json.dumps(pair) for pair in qa_pairs) + "\n"
    gt_blob = container_client.get_blob_client("ground-truth/ground_truth.jsonl")
    gt_blob.upload_blob(gt_content, overwrite=True)

    # Upload knowledge graph
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        kg.save(tmp_path)
        with open(tmp_path, "rb") as f:
            kg_data = f.read()
        kg_blob = container_client.get_blob_client("ground-truth/ground_truth_kg.json")
        kg_blob.upload_blob(kg_data, overwrite=True)
    finally:
        os.unlink(tmp_path)

    blob_service.close()
    logger.info("Stored %d Q&A pairs in blob storage", len(qa_pairs))
    return len(qa_pairs)
