"""
Azure Function: Eval Runner

On-demand RAG evaluation endpoints. Generates ground truth Q&A pairs and
runs evaluations against the deployed /chat endpoint, storing results in
blob storage and emitting custom events to Application Insights.
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import azure.functions as func
from azure.identity import DefaultAzureCredential as SyncDefaultAzureCredential
from azure.identity import ManagedIdentityCredential as SyncManagedIdentityCredential
from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential
from azure.storage.blob.aio import BlobServiceClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

logger = logging.getLogger(__name__)


@dataclass
class GlobalSettings:
    async_credential: ManagedIdentityCredential | DefaultAzureCredential
    sync_credential: SyncManagedIdentityCredential | SyncDefaultAzureCredential
    storage_account: str
    eval_blob_container: str


settings: GlobalSettings | None = None


def configure_global_settings():
    global settings

    running_in_production = os.getenv("RUNNING_IN_PRODUCTION", "false").lower() == "true"
    if running_in_production:
        client_id = os.getenv("AZURE_CLIENT_ID")
        if client_id:
            logger.info("Using Managed Identity with client ID: %s", client_id)
            async_credential = ManagedIdentityCredential(client_id=client_id)
            sync_credential = SyncManagedIdentityCredential(client_id=client_id)
        else:
            logger.info("Using default Managed Identity without client ID")
            async_credential = ManagedIdentityCredential()
            sync_credential = SyncManagedIdentityCredential()
    else:
        logger.info("Using DefaultAzureCredential for local development")
        async_credential = DefaultAzureCredential()
        sync_credential = SyncDefaultAzureCredential()

    settings = GlobalSettings(
        async_credential=async_credential,
        sync_credential=sync_credential,
        storage_account=os.environ["AZURE_STORAGE_ACCOUNT"],
        eval_blob_container=os.getenv("EVAL_BLOB_CONTAINER", "eval-data"),
    )


@app.function_name(name="generate")
@app.route(route="generate", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
async def generate_ground_truth(req: func.HttpRequest) -> func.HttpResponse:
    """
    Generate ground truth Q&A pairs from the search index.

    Optional JSON body:
        num_questions: int (default 200)
        num_search_documents: int (default all)
    """
    if settings is None:
        return func.HttpResponse(
            json.dumps({"error": "Settings not initialized"}),
            mimetype="application/json",
            status_code=500,
        )

    try:
        body = req.get_json()
    except Exception:
        body = {}

    num_questions = body.get("num_questions", 50)
    num_search_documents = body.get("num_search_documents")

    from telemetry import emit_operation_completed, emit_operation_started

    emit_operation_started(operation="generate", details=f"num_questions={num_questions}")
    start_time = time.monotonic()

    try:
        from ground_truth_engine import generate_ground_truth as gen_gt

        count = await gen_gt(
            credential=settings.async_credential,
            sync_credential=settings.sync_credential,
            num_questions=num_questions,
            num_search_documents=num_search_documents,
        )
        duration = time.monotonic() - start_time
        emit_operation_completed(
            operation="generate",
            status="success",
            duration_seconds=duration,
            details=f"qa_pairs={count}",
        )
        return func.HttpResponse(
            json.dumps({"status": "success", "qa_pairs_generated": count}),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as e:
        duration = time.monotonic() - start_time
        emit_operation_completed(
            operation="generate",
            status="error",
            duration_seconds=duration,
            error=str(e),
        )
        logger.error("Error generating ground truth: %s", str(e), exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500,
        )


@app.function_name(name="evaluate")
@app.route(route="evaluate", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
async def run_evaluation(req: func.HttpRequest) -> func.HttpResponse:
    """
    Run evaluation against the /chat endpoint.

    Optional JSON body:
        num_questions: int (default all)
        overrides: dict (chat endpoint overrides)
    """
    if settings is None:
        return func.HttpResponse(
            json.dumps({"error": "Settings not initialized"}),
            mimetype="application/json",
            status_code=500,
        )

    try:
        body = req.get_json()
    except Exception:
        body = {}

    num_questions = body.get("num_questions")
    overrides = body.get("overrides")

    from telemetry import emit_operation_completed, emit_operation_started

    emit_operation_started(operation="evaluate", details=f"num_questions={num_questions}")
    start_time = time.monotonic()

    try:
        from eval_engine import run_evaluation as run_eval

        summary = await run_eval(
            credential=settings.async_credential,
            overrides=overrides,
            num_questions=num_questions,
        )
        duration = time.monotonic() - start_time
        emit_operation_completed(
            operation="evaluate",
            status="success",
            duration_seconds=duration,
            details=f"run_id={summary.get('run_id', 'unknown')} questions={summary.get('num_questions', 0)}",
        )
        return func.HttpResponse(
            json.dumps({"status": "success", "summary": summary}),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as e:
        duration = time.monotonic() - start_time
        emit_operation_completed(
            operation="evaluate",
            status="error",
            duration_seconds=duration,
            error=str(e),
        )
        logger.error("Error running evaluation: %s", str(e), exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500,
        )


@app.function_name(name="list_runs")
@app.route(route="runs", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
async def list_runs(req: func.HttpRequest) -> func.HttpResponse:
    """List past evaluation runs from blob storage."""
    if settings is None:
        return func.HttpResponse(
            json.dumps({"error": "Settings not initialized"}),
            mimetype="application/json",
            status_code=500,
        )

    try:
        blob_service_url = f"https://{settings.storage_account}.blob.core.windows.net"
        blob_service = BlobServiceClient(blob_service_url, credential=settings.async_credential)
        container_client = blob_service.get_container_client(settings.eval_blob_container)

        runs = []
        async for blob in container_client.list_blobs(name_starts_with="runs/"):
            if blob.name.endswith("/summary.json"):
                run_id = blob.name.split("/")[1]
                # Download and parse summary
                blob_client = container_client.get_blob_client(blob.name)
                data = await blob_client.download_blob()
                summary = json.loads((await data.readall()).decode("utf-8"))
                runs.append(
                    {
                        "run_id": run_id,
                        "timestamp": blob.last_modified.isoformat() if blob.last_modified else None,
                        "num_questions": summary.get("num_questions"),
                        "groundedness_pass_rate": summary.get("groundedness_pass_rate"),
                        "relevance_pass_rate": summary.get("relevance_pass_rate"),
                        "citations_matched_rate": summary.get("citations_matched_rate"),
                        "latency_mean": summary.get("latency_mean"),
                    }
                )

        await blob_service.close()

        # Sort by timestamp descending
        runs.sort(key=lambda r: r.get("timestamp") or "", reverse=True)

        return func.HttpResponse(
            json.dumps({"runs": runs}),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as e:
        logger.error("Error listing runs: %s", str(e), exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500,
        )


@app.function_name(name="get_run")
@app.route(route="runs/{run_id}", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
async def get_run(req: func.HttpRequest) -> func.HttpResponse:
    """Get detailed results for a specific evaluation run."""
    if settings is None:
        return func.HttpResponse(
            json.dumps({"error": "Settings not initialized"}),
            mimetype="application/json",
            status_code=500,
        )

    run_id = req.route_params.get("run_id")
    if not run_id:
        return func.HttpResponse(
            json.dumps({"error": "run_id is required"}),
            mimetype="application/json",
            status_code=400,
        )

    try:
        blob_service_url = f"https://{settings.storage_account}.blob.core.windows.net"
        blob_service = BlobServiceClient(blob_service_url, credential=settings.async_credential)
        container_client = blob_service.get_container_client(settings.eval_blob_container)

        # Read summary
        summary_blob = container_client.get_blob_client(f"runs/{run_id}/summary.json")
        summary_data = await summary_blob.download_blob()
        summary = json.loads((await summary_data.readall()).decode("utf-8"))

        # Read per-question results
        results_blob = container_client.get_blob_client(f"runs/{run_id}/eval_results.jsonl")
        results_data = await results_blob.download_blob()
        results_text = (await results_data.readall()).decode("utf-8")
        results = [json.loads(line) for line in results_text.strip().split("\n") if line.strip()]

        await blob_service.close()

        return func.HttpResponse(
            json.dumps({"run_id": run_id, "summary": summary, "results": results}),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as e:
        logger.error("Error getting run %s: %s", run_id, str(e), exc_info=True)
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
