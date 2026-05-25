"""EvarisExporter — sends etrace spans to the Evaris backend via HTTP."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from etrace._exporter import SpanExportResult

if TYPE_CHECKING:
    from etrace._types import Span

logger = logging.getLogger("etrace.evaris")

_DEFAULT_ENDPOINT = "https://runtime.evaris.ai/v1/traces"
DEFAULT_ENDPOINT = _DEFAULT_ENDPOINT


def _span_to_dict(span: Span) -> dict[str, Any]:
    """Serialize an etrace Span to a JSON-compatible dict."""
    data: dict[str, Any] = {
        "trace_id": span.trace_id,
        "span_id": span.span_id,
        "name": span.name,
        "kind": span.kind.value,
        "status": span.status.value,
        "started_at": span.started_at,
        "ended_at": span.ended_at,
        "duration_ns": span.duration_ns,
    }

    if span.parent_span_id:
        data["parent_span_id"] = span.parent_span_id
    if span.input is not None:
        data["input"] = _truncate(span.input)
    if span.output is not None:
        data["output"] = _truncate(span.output)
    if span.model:
        data["model"] = span.model
    if span.provider:
        data["provider"] = span.provider
    if span.tags:
        data["tags"] = span.tags
    if span.attributes:
        data["attributes"] = span.attributes
    if span.usage:
        data["usage"] = {
            "input": span.usage.input,
            "output": span.usage.output,
            "total": span.usage.total,
            "input_cost": span.usage.input_cost,
            "output_cost": span.usage.output_cost,
            "total_cost": span.usage.total_cost,
        }
    if span.error:
        data["error"] = {"message": span.error.message, "type": span.error.type}
    if span.user_id:
        data["user_id"] = span.user_id
    if span.session_id:
        data["session_id"] = span.session_id
    if span.conversation_id:
        data["conversation_id"] = span.conversation_id
    if span.model_parameters:
        data["model_parameters"] = span.model_parameters

    return data


def _truncate(value: Any, max_len: int = 100_000) -> Any:
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len]
    return value


class EvarisExporter:
    """Sends etrace spans to the Evaris backend.

    Args:
        api_key: Evaris API key.
        project_id: Evaris project ID.
        endpoint: Override the default backend URL.
    """

    def __init__(
        self,
        *,
        api_key: str,
        project_id: str,
        endpoint: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._project_id = project_id
        self._endpoint = endpoint or _DEFAULT_ENDPOINT

    def export(self, spans: list[Span]) -> SpanExportResult:
        """POST spans to the Evaris backend."""
        try:
            import httpx

            payload = [_span_to_dict(s) for s in spans]
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "X-Evaris-Project-ID": self._project_id,
                "Content-Type": "application/json",
            }

            resp = httpx.post(
                self._endpoint,
                content=json.dumps(payload),
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            return SpanExportResult.SUCCESS
        except Exception:
            logger.warning("EvarisExporter export failed", exc_info=True)
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True
