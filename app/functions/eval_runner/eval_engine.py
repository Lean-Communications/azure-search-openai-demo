"""
Evaluation engine for the eval_runner Azure Function.

Adapted from evals/evaluate.py. Reads ground truth from blob storage,
calls the deployed /chat endpoint for each question, grades responses,
stores results in blob, and emits App Insights custom events.
"""

import json
import logging
import os
import re
import time
import uuid

import httpx
from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential
from azure.storage.blob.aio import BlobServiceClient

from telemetry import emit_eval_question_result, emit_eval_run_completed

logger = logging.getLogger("eval_runner.eval_engine")

# Citation regex (same as evals/evaluate.py)
CITATION_REGEX = re.compile(
    r"\[[^\]]+?\.(?:pdf|html?|docx?|pptx?|xlsx?|csv|txt|json|jpe?g|png|bmp|tiff?|heiff?|heif)"
    r"(?:#page=\d+)?(?:\([^()\]]+\))?\]",
    re.IGNORECASE,
)

# Default overrides for the /chat endpoint (matches evaluate_config.json)
DEFAULT_OVERRIDES = {
    "top": 3,
    "results_merge_strategy": "interleaved",
    "temperature": 0.3,
    "minimum_reranker_score": 0,
    "minimum_search_score": 0,
    "retrieval_mode": "hybrid",
    "semantic_ranker": True,
    "semantic_captions": False,
    "query_rewriting": False,
    "reasoning_effort": "minimal",
    "suggest_followup_questions": False,
    "use_oid_security_filter": False,
    "use_groups_security_filter": False,
    "search_text_embeddings": True,
    "search_image_embeddings": True,
    "send_text_sources": True,
    "send_image_sources": True,
    "language": "en",
    "use_agentic_knowledgebase": False,
    "seed": 1,
}


def _compute_any_citation(response_text: str) -> bool:
    """Check if the response contains any citation."""
    return bool(CITATION_REGEX.search(response_text))


def _compute_citations_matched(response_text: str, truth_text: str) -> float:
    """Compute fraction of ground truth citations present in response."""
    truth_citations = set(CITATION_REGEX.findall(truth_text))
    if not truth_citations:
        return 0.0
    response_citations = set(CITATION_REGEX.findall(response_text))
    return len(truth_citations.intersection(response_citations)) / len(truth_citations)


async def _get_bearer_token(credential, app_id: str) -> str | None:
    """Acquire a bearer token for the target app using managed identity."""
    if not app_id:
        return None
    token = await credential.get_token(f"api://{app_id}/.default")
    return token.token


async def _call_chat_endpoint(
    client: httpx.AsyncClient,
    target_url: str,
    question: str,
    overrides: dict,
    bearer_token: str | None = None,
) -> tuple[str, list[str], float]:
    """
    Call the /chat endpoint and return (answer, context_texts, latency_seconds).
    """
    headers = {"Content-Type": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
        logger.info("Sending request with Bearer token (length=%d)", len(bearer_token))
    else:
        logger.warning("No bearer token — sending request without Authorization header")

    payload = {
        "messages": [{"content": question, "role": "user"}],
        "context": {"overrides": overrides},
        "stream": False,
    }

    start = time.monotonic()
    resp = await client.post(target_url, json=payload, headers=headers, timeout=120.0)
    latency = time.monotonic() - start

    if resp.status_code != 200:
        logger.error("Chat endpoint returned %d (url=%s): %s", resp.status_code, str(resp.url), resp.text[:500])
        return "", [], latency

    data = resp.json()
    answer = ""
    context_texts = []

    # Extract answer: message.content
    msg = data.get("message", {})
    if isinstance(msg, dict):
        answer = msg.get("content", "")
    elif isinstance(msg, str):
        answer = msg

    # Extract context: context.data_points.text
    ctx = data.get("context", {})
    dp = ctx.get("data_points", {})
    if isinstance(dp, dict):
        context_texts = dp.get("text", [])
    elif isinstance(dp, list):
        context_texts = dp

    return answer, context_texts, latency


async def _grade_with_gpt(
    client: httpx.AsyncClient,
    azure_endpoint: str,
    deployment: str,
    credential,
    question: str,
    answer: str,
    context_texts: list[str],
) -> dict[str, float]:
    """
    Use GPT to grade groundedness and relevance.
    Returns {"groundedness": float, "relevance": float} each in [1,5].
    """
    from azure.identity.aio import DefaultAzureCredential as AsyncDefault
    from azure.identity.aio import ManagedIdentityCredential as AsyncManaged

    token = await credential.get_token("https://cognitiveservices.azure.com/.default")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token.token}",
        "api-key": "",
    }

    context_str = "\n---\n".join(context_texts[:5]) if context_texts else "(no context)"

    groundedness_prompt = f"""You are an AI assistant that evaluates the groundedness of an answer.
Given the context and the answer, rate how well the answer is grounded in the provided context.
Rate on a scale of 1-5 where:
1 = Completely ungrounded, answer contradicts or has no basis in context
5 = Fully grounded, every claim in the answer is supported by the context

Context:
{context_str}

Answer:
{answer}

Respond with ONLY a single integer from 1 to 5."""

    relevance_prompt = f"""You are an AI assistant that evaluates the relevance of an answer.
Given the question and the answer, rate how relevant the answer is to the question asked.
Rate on a scale of 1-5 where:
1 = Completely irrelevant, does not address the question at all
5 = Highly relevant, directly and fully addresses the question

Question:
{question}

Answer:
{answer}

Respond with ONLY a single integer from 1 to 5."""

    api_url = f"{azure_endpoint}/openai/deployments/{deployment}/chat/completions?api-version=2024-06-01"
    scores = {}

    for metric_name, prompt in [("groundedness", groundedness_prompt), ("relevance", relevance_prompt)]:
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 5,
        }
        try:
            resp = await client.post(api_url, json=payload, headers=headers, timeout=60.0)
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"].strip()
                scores[metric_name] = float(text)
            else:
                logger.warning("GPT grading for %s failed: %d", metric_name, resp.status_code)
                scores[metric_name] = -1.0
        except Exception as e:
            logger.warning("GPT grading for %s error: %s", metric_name, e)
            scores[metric_name] = -1.0

    return scores


async def run_evaluation(
    credential: ManagedIdentityCredential | DefaultAzureCredential,
    overrides: dict | None = None,
    num_questions: int | None = None,
) -> dict:
    """
    Run the full evaluation pipeline.

    1. Read ground truth from blob
    2. Call /chat for each question
    3. Grade responses
    4. Store results in blob
    5. Emit App Insights events
    6. Return summary
    """
    storage_account = os.environ["AZURE_STORAGE_ACCOUNT"]
    container_name = os.getenv("EVAL_BLOB_CONTAINER", "eval-data")
    target_url = os.environ["EVAL_TARGET_URL"]
    target_app_id = os.getenv("EVAL_TARGET_APP_ID", "")
    eval_deployment = os.getenv("AZURE_OPENAI_EVAL_DEPLOYMENT", "eval")

    azure_openai_custom_url = os.getenv("AZURE_OPENAI_CUSTOM_URL")
    if azure_openai_custom_url:
        from urllib.parse import urlparse

        parsed = urlparse(azure_openai_custom_url)
        azure_endpoint = f"{parsed.scheme}://{parsed.netloc}"
    else:
        azure_endpoint = f"https://{os.getenv('AZURE_OPENAI_SERVICE')}.openai.azure.com"

    chat_overrides = {**DEFAULT_OVERRIDES, **(overrides or {})}
    run_id = str(uuid.uuid4())[:8]

    # Read ground truth from blob
    blob_service_url = f"https://{storage_account}.blob.core.windows.net"
    blob_service = BlobServiceClient(blob_service_url, credential=credential)
    container_client = blob_service.get_container_client(container_name)

    gt_blob = container_client.get_blob_client("ground-truth/ground_truth.jsonl")
    gt_data = await gt_blob.download_blob()
    gt_text = (await gt_data.readall()).decode("utf-8")
    qa_pairs = [json.loads(line) for line in gt_text.strip().split("\n") if line.strip()]

    if num_questions and num_questions < len(qa_pairs):
        qa_pairs = qa_pairs[:num_questions]

    logger.info("Running evaluation run_id=%s with %d questions against %s", run_id, len(qa_pairs), target_url)
    logger.info("EVAL_TARGET_APP_ID=%s (truthy=%s)", target_app_id, bool(target_app_id))

    # Acquire bearer token for target app
    bearer_token = await _get_bearer_token(credential, target_app_id)
    logger.info("Bearer token acquired: %s (length=%d)", bearer_token is not None, len(bearer_token) if bearer_token else 0)

    # Decode JWT claims for debugging (token is base64-encoded, no verification needed)
    if bearer_token:
        import base64
        parts = bearer_token.split(".")
        if len(parts) >= 2:
            # Add padding and decode payload
            payload = parts[1] + "=" * (4 - len(parts[1]) % 4)
            try:
                claims = json.loads(base64.b64decode(payload))
                logger.info("JWT claims: aud=%s appid=%s azp=%s iss=%s sub=%s", claims.get("aud"), claims.get("appid"), claims.get("azp"), claims.get("iss"), claims.get("sub"))
            except Exception as e:
                logger.warning("Could not decode JWT: %s", e)

    results = []
    async with httpx.AsyncClient(follow_redirects=False) as client:
        for i, qa in enumerate(qa_pairs):
            question = qa["question"]
            truth = qa.get("truth", "")

            logger.info("Evaluating question %d/%d: %s", i + 1, len(qa_pairs), question[:80])

            # Call chat endpoint
            answer, context_texts, latency = await _call_chat_endpoint(
                client, target_url, question, chat_overrides, bearer_token
            )

            # Local metrics
            any_citation = _compute_any_citation(answer)
            citations_matched = _compute_citations_matched(answer, truth)
            answer_length = len(answer)

            # GPT-based grading
            gpt_scores = await _grade_with_gpt(
                client, azure_endpoint, eval_deployment, credential, question, answer, context_texts
            )

            result = {
                "question": question,
                "truth": truth,
                "answer": answer,
                "context": context_texts[:3],
                "groundedness": gpt_scores.get("groundedness", -1),
                "relevance": gpt_scores.get("relevance", -1),
                "citations_matched": citations_matched,
                "any_citation": any_citation,
                "latency": round(latency, 3),
                "answer_length": answer_length,
            }
            results.append(result)

            # Emit per-question telemetry
            emit_eval_question_result(
                run_id=run_id,
                question=question,
                groundedness=result["groundedness"],
                relevance=result["relevance"],
                citations_matched=citations_matched,
                any_citation=any_citation,
                latency=latency,
                answer_length=answer_length,
            )

    # Compute summary
    valid_groundedness = [r["groundedness"] for r in results if r["groundedness"] >= 0]
    valid_relevance = [r["relevance"] for r in results if r["relevance"] >= 0]
    latencies = [r["latency"] for r in results]

    summary = {
        "run_id": run_id,
        "num_questions": len(results),
        "target_url": target_url,
        "groundedness_mean": round(sum(valid_groundedness) / len(valid_groundedness), 3) if valid_groundedness else -1,
        "groundedness_pass_rate": round(
            sum(1 for g in valid_groundedness if g >= 4) / len(valid_groundedness), 3
        )
        if valid_groundedness
        else 0,
        "relevance_mean": round(sum(valid_relevance) / len(valid_relevance), 3) if valid_relevance else -1,
        "relevance_pass_rate": round(sum(1 for r in valid_relevance if r >= 4) / len(valid_relevance), 3)
        if valid_relevance
        else 0,
        "citations_matched_rate": round(sum(r["citations_matched"] for r in results) / len(results), 3)
        if results
        else 0,
        "any_citation_rate": round(sum(1 for r in results if r["any_citation"]) / len(results), 3) if results else 0,
        "latency_mean": round(sum(latencies) / len(latencies), 3) if latencies else 0,
        "latency_max": round(max(latencies), 3) if latencies else 0,
        "answer_length_mean": round(sum(r["answer_length"] for r in results) / len(results), 1) if results else 0,
    }

    # Store results in blob
    run_prefix = f"runs/{run_id}"

    results_content = "\n".join(json.dumps(r) for r in results) + "\n"
    results_blob = container_client.get_blob_client(f"{run_prefix}/eval_results.jsonl")
    await results_blob.upload_blob(results_content, overwrite=True)

    summary_blob = container_client.get_blob_client(f"{run_prefix}/summary.json")
    await summary_blob.upload_blob(json.dumps(summary, indent=2), overwrite=True)

    await blob_service.close()

    # Emit run-level telemetry
    emit_eval_run_completed(
        run_id=run_id,
        num_questions=summary["num_questions"],
        groundedness_pass_rate=summary["groundedness_pass_rate"],
        groundedness_mean=summary["groundedness_mean"],
        relevance_pass_rate=summary["relevance_pass_rate"],
        relevance_mean=summary["relevance_mean"],
        citations_matched_rate=summary["citations_matched_rate"],
        any_citation_rate=summary["any_citation_rate"],
        latency_mean=summary["latency_mean"],
        latency_max=summary["latency_max"],
        answer_length_mean=summary["answer_length_mean"],
    )

    logger.info("Evaluation complete: run_id=%s, summary=%s", run_id, json.dumps(summary))
    return summary
