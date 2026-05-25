"""Tests for etrace._processor — SpanProcessor protocol and built-in implementations."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from etrace._exporter import InMemoryExporter
from etrace._processor import BatchProcessor, MultiProcessor, SimpleProcessor
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


# ── SimpleProcessor ───────────────────────────────────────────────────────────


class TestSimpleProcessor:
    def test_on_end_calls_exporter_immediately(self):
        exporter = InMemoryExporter()
        processor = SimpleProcessor(exporter)
        s = _make_span()
        processor.on_end(s)
        assert exporter.get_finished_spans() == [s]

    def test_on_start_does_not_export(self):
        exporter = InMemoryExporter()
        processor = SimpleProcessor(exporter)
        s = _make_span()
        processor.on_start(s)
        assert exporter.get_finished_spans() == []

    def test_multiple_spans_exported_individually(self):
        exporter = InMemoryExporter()
        processor = SimpleProcessor(exporter)
        s1, s2, s3 = _make_span("a"), _make_span("b"), _make_span("c")
        processor.on_end(s1)
        processor.on_end(s2)
        processor.on_end(s3)
        # SimpleProcessor exports each span individually (batch of 1)
        assert len(exporter.get_finished_spans()) == 3
        assert exporter.get_finished_spans() == [s1, s2, s3]

    def test_shutdown_calls_exporter_shutdown(self):
        exporter = MagicMock()
        processor = SimpleProcessor(exporter)
        processor.shutdown()
        exporter.shutdown.assert_called_once()

    def test_force_flush_calls_exporter_flush(self):
        exporter = MagicMock()
        exporter.force_flush.return_value = True
        processor = SimpleProcessor(exporter)
        assert processor.force_flush(timeout_millis=5000) is True
        exporter.force_flush.assert_called_once_with(5000)

    def test_force_flush_propagates_false(self):
        exporter = MagicMock()
        exporter.force_flush.return_value = False
        processor = SimpleProcessor(exporter)
        assert processor.force_flush() is False


# ── BatchProcessor ────────────────────────────────────────────────────────────


class TestBatchProcessor:
    def test_on_end_does_not_export_immediately(self):
        exporter = InMemoryExporter()
        processor = BatchProcessor(exporter, schedule_delay_ms=10000)
        processor.on_end(_make_span())
        # Give it a tiny moment to make sure no background export happened
        assert exporter.get_finished_spans() == []

    def test_force_flush_exports_queued_spans(self):
        exporter = InMemoryExporter()
        processor = BatchProcessor(exporter, schedule_delay_ms=60000)
        s1, s2 = _make_span("a"), _make_span("b")
        processor.on_end(s1)
        processor.on_end(s2)
        processor.force_flush(timeout_millis=5000)
        spans = exporter.get_finished_spans()
        assert len(spans) == 2
        names = {s.name for s in spans}
        assert names == {"a", "b"}

    def test_shutdown_flushes_remaining_spans(self):
        exporter = InMemoryExporter()
        processor = BatchProcessor(exporter, schedule_delay_ms=60000)
        processor.on_end(_make_span("final"))
        processor.shutdown()
        assert len(exporter.get_finished_spans()) == 1

    def test_respects_max_export_batch_size(self):
        exporter = InMemoryExporter()
        processor = BatchProcessor(exporter, schedule_delay_ms=60000, max_export_batch_size=2)
        for i in range(5):
            processor.on_end(_make_span(f"span_{i}"))
        processor.force_flush(timeout_millis=5000)
        assert len(exporter.get_finished_spans()) == 5

    def test_background_flush_on_schedule(self):
        """Spans are exported by the background thread after schedule_delay."""
        exporter = InMemoryExporter()
        processor = BatchProcessor(exporter, schedule_delay_ms=50)
        processor.on_end(_make_span("bg"))
        time.sleep(0.3)
        assert len(exporter.get_finished_spans()) >= 1
        processor.shutdown()

    def test_shutdown_calls_exporter_shutdown(self):
        exporter = MagicMock()
        processor = BatchProcessor(exporter, schedule_delay_ms=60000)
        processor.shutdown()
        exporter.shutdown.assert_called_once()

    def test_on_start_does_not_queue(self):
        exporter = InMemoryExporter()
        processor = BatchProcessor(exporter, schedule_delay_ms=60000)
        processor.on_start(_make_span())
        processor.force_flush(timeout_millis=1000)
        assert exporter.get_finished_spans() == []


# ── MultiProcessor ────────────────────────────────────────────────────────────


class TestMultiProcessor:
    def test_fans_out_on_end_to_all(self):
        exp1 = InMemoryExporter()
        exp2 = InMemoryExporter()
        proc = MultiProcessor([SimpleProcessor(exp1), SimpleProcessor(exp2)])
        s = _make_span()
        proc.on_end(s)
        assert exp1.get_finished_spans() == [s]
        assert exp2.get_finished_spans() == [s]

    def test_fans_out_on_start_to_all(self):
        p1 = MagicMock()
        p2 = MagicMock()
        proc = MultiProcessor([p1, p2])
        s = _make_span()
        proc.on_start(s)
        p1.on_start.assert_called_once_with(s)
        p2.on_start.assert_called_once_with(s)

    def test_shutdown_shuts_down_all(self):
        p1 = MagicMock()
        p2 = MagicMock()
        proc = MultiProcessor([p1, p2])
        proc.shutdown()
        p1.shutdown.assert_called_once()
        p2.shutdown.assert_called_once()

    def test_force_flush_flushes_all(self):
        p1 = MagicMock()
        p2 = MagicMock()
        p1.force_flush.return_value = True
        p2.force_flush.return_value = True
        proc = MultiProcessor([p1, p2])
        assert proc.force_flush() is True
        p1.force_flush.assert_called_once()
        p2.force_flush.assert_called_once()

    def test_force_flush_returns_false_if_any_fails(self):
        p1 = MagicMock()
        p2 = MagicMock()
        p1.force_flush.return_value = True
        p2.force_flush.return_value = False
        proc = MultiProcessor([p1, p2])
        assert proc.force_flush() is False

    def test_empty_multi_is_safe(self):
        proc = MultiProcessor([])
        proc.on_start(_make_span())
        proc.on_end(_make_span())
        proc.shutdown()
        assert proc.force_flush() is True
