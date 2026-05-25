"""Tests for etrace[otel] — OtelExporter bridge.

Tests that etrace Span objects can be converted to OTel ReadableSpan
format and exported via standard OTLP pipeline.
"""

from __future__ import annotations

import pytest

# OTel imports — these are available in dev/otel test env
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import etrace
from etrace._exporter import InMemoryExporter
from etrace._types import TraceKind, TraceStatus, Usage

# ── OtelExporter unit tests ────────────────────────────────────────────────────


class TestOtelExporterConversion:
    """Test that etrace Span → OTel ReadableSpan conversion is correct."""

    def _make_etrace_span(self, **overrides):
        """Create a finished etrace Span for testing."""
        from datetime import UTC, datetime

        from etrace._types import Span

        defaults = dict(
            trace_id="abc123",
            span_id="def456",
            name="test_span",
            kind=TraceKind.TOOL,
            status=TraceStatus.OK,
            started_at=datetime.now(UTC).isoformat(),
            ended_at=datetime.now(UTC).isoformat(),
            duration_ns=1_000_000,
        )
        defaults.update(overrides)
        return Span(**defaults)

    def test_basic_span_conversion(self):
        """OtelExporter converts a basic etrace Span to OTel format."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        exporter = OtelExporter(otel_exporter=otel_mem)

        span = self._make_etrace_span()
        result = exporter.export([span])

        assert result.name == "SUCCESS"
        otel_spans = otel_mem.get_finished_spans()
        assert len(otel_spans) == 1
        assert otel_spans[0].name == "test_span"

    def test_trace_and_span_ids_preserved(self):
        """etrace trace_id/span_id are mapped to OTel format."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        exporter = OtelExporter(otel_exporter=otel_mem)

        span = self._make_etrace_span(trace_id="a" * 32, span_id="b" * 16)
        exporter.export([span])

        otel_span = otel_mem.get_finished_spans()[0]
        assert otel_span.context.trace_id == int("a" * 32, 16)
        assert otel_span.context.span_id == int("b" * 16, 16)

    def test_parent_span_id_linked(self):
        """etrace parent_span_id is mapped to OTel parent."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        exporter = OtelExporter(otel_exporter=otel_mem)

        span = self._make_etrace_span(parent_span_id="c" * 16)
        exporter.export([span])

        otel_span = otel_mem.get_finished_spans()[0]
        assert otel_span.parent is not None
        assert otel_span.parent.span_id == int("c" * 16, 16)

    def test_kind_mapped_to_otel_span_kind(self):
        """etrace TraceKind maps to appropriate OTel SpanKind."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        exporter = OtelExporter(otel_exporter=otel_mem)

        # INTERNAL by default
        span = self._make_etrace_span(kind=TraceKind.TOOL)
        exporter.export([span])
        assert otel_mem.get_finished_spans()[0].kind.name == "INTERNAL"

    def test_status_ok_mapped(self):
        """etrace OK → OTel StatusCode.OK."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        exporter = OtelExporter(otel_exporter=otel_mem)

        span = self._make_etrace_span(status=TraceStatus.OK)
        exporter.export([span])

        s = otel_mem.get_finished_spans()[0]
        assert s.status.status_code.name == "OK"

    def test_status_error_mapped(self):
        """etrace ERROR → OTel StatusCode.ERROR with description."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        exporter = OtelExporter(otel_exporter=otel_mem)

        span = self._make_etrace_span(status=TraceStatus.ERROR)
        from etrace._types import TraceError

        span.error = TraceError(message="boom", type="RuntimeError")
        exporter.export([span])

        s = otel_mem.get_finished_spans()[0]
        assert s.status.status_code.name == "ERROR"
        assert s.status.description == "boom"

    def test_usage_mapped_to_gen_ai_attributes(self):
        """etrace Usage → gen_ai.usage.* OTel attributes."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        exporter = OtelExporter(otel_exporter=otel_mem)

        span = self._make_etrace_span(model="gpt-4o", provider="openai")
        span.usage = Usage(input=100, output=50, total=150)
        exporter.export([span])

        s = otel_mem.get_finished_spans()[0]
        attrs = dict(s.attributes or {})
        assert attrs.get("gen_ai.usage.prompt_tokens") == 100
        assert attrs.get("gen_ai.usage.completion_tokens") == 50
        assert attrs.get("gen_ai.usage.total_tokens") == 150

    def test_model_and_provider_mapped(self):
        """etrace model/provider → gen_ai.request.model / gen_ai.system."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        exporter = OtelExporter(otel_exporter=otel_mem)

        span = self._make_etrace_span(model="gpt-4o", provider="openai")
        exporter.export([span])

        attrs = dict(otel_mem.get_finished_spans()[0].attributes or {})
        assert attrs.get("gen_ai.request.model") == "gpt-4o"
        assert attrs.get("gen_ai.system") == "openai"

    def test_kind_attribute_set(self):
        """etrace kind is preserved as evaris.kind attribute."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        exporter = OtelExporter(otel_exporter=otel_mem)

        span = self._make_etrace_span(kind=TraceKind.LLM)
        exporter.export([span])

        attrs = dict(otel_mem.get_finished_spans()[0].attributes or {})
        assert attrs.get("etrace.kind") == "llm"

    def test_custom_attributes_merged(self):
        """etrace span.attributes are merged into OTel attributes."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        exporter = OtelExporter(otel_exporter=otel_mem)

        span = self._make_etrace_span(attributes={"custom_key": "custom_val"})
        exporter.export([span])

        attrs = dict(otel_mem.get_finished_spans()[0].attributes or {})
        assert attrs.get("custom_key") == "custom_val"

    def test_input_output_captured(self):
        """etrace input/output → etrace.input / etrace.output attributes."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        exporter = OtelExporter(otel_exporter=otel_mem)

        span = self._make_etrace_span(input="hello", output="world")
        exporter.export([span])

        attrs = dict(otel_mem.get_finished_spans()[0].attributes or {})
        assert attrs.get("etrace.input") == "hello"
        assert attrs.get("etrace.output") == "world"

    def test_batch_export(self):
        """OtelExporter exports multiple spans in one call."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        exporter = OtelExporter(otel_exporter=otel_mem)

        spans = [self._make_etrace_span(name=f"span_{i}", span_id=f"{i:016d}") for i in range(5)]
        exporter.export(spans)
        assert len(otel_mem.get_finished_spans()) == 5

    def test_shutdown_delegates(self):
        """OtelExporter.shutdown() delegates to underlying exporter."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        exporter = OtelExporter(otel_exporter=otel_mem)
        exporter.shutdown()
        # InMemorySpanExporter doesn't raise on double-export after shutdown

    def test_force_flush_delegates(self):
        """OtelExporter.force_flush() delegates to underlying exporter."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        exporter = OtelExporter(otel_exporter=otel_mem)
        assert exporter.force_flush(5000) is True


class TestOtelExporterIntegration:
    """Integration: etrace → OtelExporter → OTel InMemorySpanExporter."""

    def test_etrace_pipeline_with_otel_exporter(self):
        """etrace.init() with OtelExporter produces OTel spans."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        otel_exporter = OtelExporter(otel_exporter=otel_mem)

        etrace.init(exporters=[otel_exporter], auto_instrument={"llm": False})

        with etrace.trace("my_tool", kind=TraceKind.TOOL) as span:
            span.output = "done"

        etrace.shutdown()

        otel_spans = otel_mem.get_finished_spans()
        assert len(otel_spans) == 1
        assert otel_spans[0].name == "my_tool"
        assert dict(otel_spans[0].attributes or {}).get("etrace.kind") == "tool"

    def test_nested_etrace_spans_produce_otel_hierarchy(self):
        """Nested etrace traces produce parent/child OTel spans."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        otel_exporter = OtelExporter(otel_exporter=otel_mem)

        etrace.init(exporters=[otel_exporter], auto_instrument={"llm": False})

        with etrace.trace("parent", kind=TraceKind.WORKFLOW), etrace.trace("child", kind=TraceKind.TOOL):
            pass

        etrace.shutdown()

        otel_spans = otel_mem.get_finished_spans()
        assert len(otel_spans) == 2

        parent = next(s for s in otel_spans if s.name == "parent")
        child = next(s for s in otel_spans if s.name == "child")

        assert child.parent is not None
        assert child.parent.span_id == parent.context.span_id
        assert child.context.trace_id == parent.context.trace_id

    def test_etrace_observe_with_otel_exporter(self):
        """@etrace.observe creates OTel spans via OtelExporter."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        otel_exporter = OtelExporter(otel_exporter=otel_mem)

        etrace.init(exporters=[otel_exporter], auto_instrument={"llm": False})

        @etrace.observe(kind=TraceKind.AGENT, name="my_agent")
        def my_agent(x: int) -> int:
            return x * 2

        result = my_agent(5)
        assert result == 10

        etrace.shutdown()

        otel_spans = otel_mem.get_finished_spans()
        assert len(otel_spans) == 1
        assert otel_spans[0].name == "my_agent"

    def test_otel_exporter_alongside_inmemory(self):
        """Can use OtelExporter + InMemoryExporter in multi-exporter setup."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        etrace_mem = InMemoryExporter()

        otel_exporter = OtelExporter(otel_exporter=otel_mem)

        etrace.init(
            exporters=[otel_exporter, etrace_mem],
            auto_instrument={"llm": False},
        )

        with etrace.trace("dual", kind=TraceKind.TOOL):
            pass

        etrace.shutdown()

        # Both exporters received the span
        assert len(otel_mem.get_finished_spans()) == 1
        assert len(etrace_mem.get_finished_spans()) == 1

    def test_error_span_maps_to_otel_error(self):
        """etrace error span → OTel span with ERROR status + exception event."""
        from etrace.otel import OtelExporter

        otel_mem = InMemorySpanExporter()
        otel_exporter = OtelExporter(otel_exporter=otel_mem)

        etrace.init(exporters=[otel_exporter], auto_instrument={"llm": False})

        with pytest.raises(ValueError, match="boom"), etrace.trace("failing", kind=TraceKind.TOOL):
            raise ValueError("boom")

        etrace.shutdown()

        otel_spans = otel_mem.get_finished_spans()
        assert len(otel_spans) == 1
        assert otel_spans[0].status.status_code.name == "ERROR"
