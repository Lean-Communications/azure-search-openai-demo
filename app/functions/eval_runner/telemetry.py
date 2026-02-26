"""
Telemetry helper for emitting custom events to Application Insights.

Uses the OpenCensus Azure Monitor exporter to send custom events
directly to the App Insights customEvents table.
"""

import logging
import os

from opencensus.ext.azure.log_exporter import AzureEventHandler

logger = logging.getLogger("eval_runner.telemetry")

# Set up a dedicated logger that sends custom events to App Insights
_event_logger = logging.getLogger("eval_runner.events")
_event_logger.setLevel(logging.INFO)

_conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
if _conn_str:
    _handler = AzureEventHandler(connection_string=_conn_str)
    _event_logger.addHandler(_handler)
    logger.info("App Insights event handler configured")
else:
    logger.warning("APPLICATIONINSIGHTS_CONNECTION_STRING not set — events will not be sent")


def emit_eval_run_completed(
    *,
    run_id: str,
    num_questions: int,
    groundedness_pass_rate: float,
    groundedness_mean: float,
    relevance_pass_rate: float,
    relevance_mean: float,
    citations_matched_rate: float,
    any_citation_rate: float,
    latency_mean: float,
    latency_max: float,
    answer_length_mean: float,
):
    """Emit an EvalRunCompleted custom event to App Insights."""
    props = {
        "custom_dimensions": {
            "run_id": run_id,
            "num_questions": num_questions,
            "groundedness_pass_rate": groundedness_pass_rate,
            "groundedness_mean": groundedness_mean,
            "relevance_pass_rate": relevance_pass_rate,
            "relevance_mean": relevance_mean,
            "citations_matched_rate": citations_matched_rate,
            "any_citation_rate": any_citation_rate,
            "latency_mean": latency_mean,
            "latency_max": latency_max,
            "answer_length_mean": answer_length_mean,
        }
    }
    _event_logger.info("EvalRunCompleted", extra=props)
    logger.info("Emitted EvalRunCompleted event: run_id=%s questions=%d", run_id, num_questions)


def emit_eval_question_result(
    *,
    run_id: str,
    question: str,
    groundedness: float,
    relevance: float,
    citations_matched: float,
    any_citation: bool,
    latency: float,
    answer_length: int,
):
    """Emit an EvalQuestionResult custom event to App Insights."""
    props = {
        "custom_dimensions": {
            "run_id": run_id,
            "question": question[:500],
            "groundedness": groundedness,
            "relevance": relevance,
            "citations_matched": citations_matched,
            "any_citation": any_citation,
            "latency": latency,
            "answer_length": answer_length,
        }
    }
    _event_logger.info("EvalQuestionResult", extra=props)
    logger.info("Emitted EvalQuestionResult event: run_id=%s q=%s", run_id, question[:80])
