"""Tests for etrace._exporter — SpanExporter protocol and built-in implementations."""

from __future__ import annotations

from etrace._exporter import (
    ConsoleExporter,
    InMemoryExporter,
    SpanExportResult,
)
from etrace._types import Span, TraceKind, TraceStatus


def _make_span(name: str = "test", kind: TraceKind = TraceKind.TOOL) -> Span:
    return Span(
        trace_id="0" * 32,
        span_id="0" * 16,
        name=name,
        kind=kind,
        status=TraceStatus.OK,
        started_at="2025-01-01T00:00:00Z",
        ended_at="2025-01-01T00:00:01Z",
        duration_ns=1_000_000_000,
    )


# ── SpanExportResult ──────────────────────────────────────────────────────────


class TestSpanExportResult:
    def test_success_failure_values(self):
        assert SpanExportResult.SUCCESS.value == "success"
        assert SpanExportResult.FAILURE.value == "failure"


# ── InMemoryExporter ──────────────────────────────────────────────────────────


class TestInMemoryExporter:
    def test_export_accumulates_spans(self):
        exporter = InMemoryExporter()
        s1, s2 = _make_span("a"), _make_span("b")
        assert exporter.export([s1, s2]) == SpanExportResult.SUCCESS
        assert exporter.get_finished_spans() == [s1, s2]

    def test_export_returns_success(self):
        exporter = InMemoryExporter()
        assert exporter.export([_make_span()]) == SpanExportResult.SUCCESS

    def test_export_empty_batch(self):
        exporter = InMemoryExporter()
        assert exporter.export([]) == SpanExportResult.SUCCESS
        assert exporter.get_finished_spans() == []

    def test_get_finished_spans_returns_copy(self):
        exporter = InMemoryExporter()
        s = _make_span()
        exporter.export([s])
        spans = exporter.get_finished_spans()
        spans.clear()
        assert exporter.get_finished_spans() == [s]

    def test_clear_removes_all_spans(self):
        exporter = InMemoryExporter()
        exporter.export([_make_span(), _make_span()])
        exporter.clear()
        assert exporter.get_finished_spans() == []

    def test_force_flush_returns_true(self):
        exporter = InMemoryExporter()
        assert exporter.force_flush() is True
        assert exporter.force_flush(timeout_millis=1000) is True

    def test_shutdown_is_safe(self):
        exporter = InMemoryExporter()
        exporter.export([_make_span()])
        exporter.shutdown()
        assert exporter.get_finished_spans() == [s for s in exporter.get_finished_spans()]

    def test_multiple_exports_accumulate(self):
        exporter = InMemoryExporter()
        exporter.export([_make_span("1")])
        exporter.export([_make_span("2")])
        exporter.export([_make_span("3")])
        assert len(exporter.get_finished_spans()) == 3

    def test_spans_preserve_all_fields(self):
        exporter = InMemoryExporter()
        s = _make_span()
        s.model = "gpt-4o"
        s.provider = "openai"
        s.input = "hello"
        s.output = "world"
        exporter.export([s])
        exported = exporter.get_finished_spans()[0]
        assert exported.model == "gpt-4o"
        assert exported.provider == "openai"
        assert exported.input == "hello"
        assert exported.output == "world"


# ── ConsoleExporter ───────────────────────────────────────────────────────────


class TestConsoleExporter:
    def test_export_writes_to_stdout(self, capsys):
        exporter = ConsoleExporter()
        s = _make_span("my_span")
        exporter.export([s])
        captured = capsys.readouterr()
        assert "my_span" in captured.out

    def test_export_returns_success(self, capsys):
        exporter = ConsoleExporter()
        assert exporter.export([_make_span()]) == SpanExportResult.SUCCESS

    def test_export_multiple_spans(self, capsys):
        exporter = ConsoleExporter()
        exporter.export([_make_span("span_a"), _make_span("span_b")])
        captured = capsys.readouterr()
        assert "span_a" in captured.out
        assert "span_b" in captured.out

    def test_custom_output_stream(self):
        import io

        buf = io.StringIO()
        exporter = ConsoleExporter(out=buf)
        exporter.export([_make_span("custom_out")])
        assert "custom_out" in buf.getvalue()

    def test_force_flush_returns_true(self):
        exporter = ConsoleExporter()
        assert exporter.force_flush() is True

    def test_shutdown_is_safe(self):
        exporter = ConsoleExporter()
        exporter.shutdown()


# ── Custom exporter (protocol compliance) ─────────────────────────────────────


class TestCustomExporterProtocol:
    def test_custom_exporter_works(self):
        """Any object with export/shutdown/force_flush satisfies the protocol."""

        class MyExporter:
            def __init__(self):
                self.exported = []

            def export(self, spans):
                self.exported.extend(spans)
                return SpanExportResult.SUCCESS

            def shutdown(self):
                pass

            def force_flush(self, timeout_millis=30000):
                return True

        exp = MyExporter()
        s = _make_span()
        exp.export([s])
        assert len(exp.exported) == 1
