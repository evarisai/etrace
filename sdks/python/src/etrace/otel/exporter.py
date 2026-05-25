"""OtelExporter — converts etrace Span → OTel ReadableSpan → OTLP."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from etrace import MAX_ATTR_LEN
from etrace._exporter import SpanExportResult
from etrace._types import TraceStatus

if TYPE_CHECKING:
    from opentelemetry.sdk.trace.export import SpanExporter as OtelSpanExporter

    from etrace._types import Span

logger = logging.getLogger("etrace.otel")

_TRACE_ID_HEX_LEN = 32
_SPAN_ID_HEX_LEN = 16


def _hex_to_int(hex_str: str, expected_len: int) -> int:
    padded = hex_str[:expected_len].ljust(expected_len, "0")
    return int(padded, 16)


def _status_to_otel(status: TraceStatus) -> tuple[Any, str | None]:
    from opentelemetry.trace import StatusCode

    if status == TraceStatus.OK:
        return StatusCode.OK, None
    if status == TraceStatus.ERROR:
        return StatusCode.ERROR, None
    return StatusCode.UNSET, None


def _iso_to_ns(iso_str: str) -> int | None:
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(iso_str)
        return int(dt.timestamp() * 1_000_000_000)
    except Exception:
        return None


def _span_to_attributes(span: Span) -> dict[str, Any]:
    attrs: dict[str, Any] = {}

    attrs["etrace.kind"] = span.kind.value

    if span.model:
        attrs["gen_ai.request.model"] = span.model
    if span.provider:
        attrs["gen_ai.system"] = span.provider

    if span.usage:
        u = span.usage
        attrs["gen_ai.usage.prompt_tokens"] = u.input
        attrs["gen_ai.usage.completion_tokens"] = u.output
        attrs["gen_ai.usage.total_tokens"] = u.total or (u.input + u.output)
        if u.cached_tokens:
            attrs["gen_ai.usage.cache_read_tokens"] = u.cached_tokens
        if u.reasoning_tokens:
            attrs["gen_ai.usage.reasoning_tokens"] = u.reasoning_tokens
        if u.total_cost:
            attrs["gen_ai.usage.cost"] = u.total_cost

    if span.input is not None:
        attrs["etrace.input"] = str(span.input)[:MAX_ATTR_LEN]
    if span.output is not None:
        attrs["etrace.output"] = str(span.output)[:MAX_ATTR_LEN]

    if span.tags:
        attrs["etrace.tags"] = ",".join(span.tags)

    if span.user_id:
        attrs["etrace.user_id"] = span.user_id
    if span.session_id:
        attrs["etrace.session_id"] = span.session_id
    if span.conversation_id:
        attrs["etrace.conversation_id"] = span.conversation_id

    attrs.update(span.attributes)
    return attrs


class _NoopProcessor:
    def on_start(self, *a: Any, **kw: Any) -> None:
        pass

    def on_end(self, *a: Any, **kw: Any) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def force_flush(self, *a: Any, **kw: Any) -> bool:
        return True


def _etrace_to_otel_span(span: Span) -> Any:
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import _Span
    from opentelemetry.trace import SpanContext, SpanKind, TraceFlags
    from opentelemetry.trace.status import Status

    trace_id_int = _hex_to_int(span.trace_id, _TRACE_ID_HEX_LEN)
    span_id_int = _hex_to_int(span.span_id, _SPAN_ID_HEX_LEN)

    ctx = SpanContext(
        trace_id=trace_id_int,
        span_id=span_id_int,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.DEFAULT),
    )

    parent_ctx = None
    if span.parent_span_id:
        parent_ctx = SpanContext(
            trace_id=trace_id_int,
            span_id=_hex_to_int(span.parent_span_id, _SPAN_ID_HEX_LEN),
            is_remote=False,
            trace_flags=TraceFlags(TraceFlags.DEFAULT),
        )

    attrs = _span_to_attributes(span)
    status_code, status_desc = _status_to_otel(span.status)
    if span.error and status_code.name == "ERROR":
        status_desc = span.error.message

    start_time = _iso_to_ns(span.started_at) if span.started_at else None
    end_time = _iso_to_ns(span.ended_at) if span.ended_at else None

    otel_span = _Span(
        name=span.name,
        context=ctx,
        parent=parent_ctx,
        resource=Resource.create({}),
        attributes=attrs,
        kind=SpanKind.INTERNAL,
        span_processor=_NoopProcessor(),  # type: ignore[arg-type]
    )

    # Set status BEFORE end_time (OTel warns on status change after end)
    otel_span.set_status(Status(status_code, status_desc))

    if span.error:
        otel_span.set_attribute("exception.type", span.error.type or "unknown")
        otel_span.set_attribute("exception.message", span.error.message)

    # Set timing last (marks span as ended)
    if start_time is not None:
        otel_span._start_time = start_time
    if end_time is not None:
        otel_span._end_time = end_time

    return otel_span


class OtelExporter:
    """Bridges etrace Span → OTel ReadableSpan → standard OTel SpanExporter.

    Args:
        otel_exporter: An OTel SpanExporter to delegate to.
            If not provided, creates OTLP HTTP exporter from OTEL_* env vars.
    """

    def __init__(self, otel_exporter: OtelSpanExporter | None = None) -> None:
        if otel_exporter is not None:
            self._exporter = otel_exporter
        else:
            self._exporter = self._create_default_otlp_exporter()

    def _create_default_otlp_exporter(self) -> OtelSpanExporter:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter()

    def export(self, spans: list[Span]) -> SpanExportResult:
        try:
            otel_spans = [_etrace_to_otel_span(s) for s in spans]
            result = self._exporter.export(otel_spans)
            if hasattr(result, "name") and result.name == "SUCCESS":
                return SpanExportResult.SUCCESS
            return SpanExportResult.FAILURE
        except Exception:
            logger.warning("OtelExporter export failed", exc_info=True)
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._exporter.force_flush(timeout_millis)
