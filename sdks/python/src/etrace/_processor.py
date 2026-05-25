"""SpanProcessor protocol and built-in implementations."""

from __future__ import annotations

import logging
import queue
import threading
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from etrace._exporter import SpanExporter
    from etrace._types import Span

logger = logging.getLogger("etrace")


@runtime_checkable
class SpanProcessor(Protocol):
    """Protocol all processors must satisfy."""

    def on_start(self, span: Span) -> None: ...
    def on_end(self, span: Span) -> None: ...
    def shutdown(self) -> None: ...
    def force_flush(self, timeout_millis: int = 30_000) -> bool: ...


class SimpleProcessor:
    """Exports each span immediately on on_end()."""

    def __init__(self, exporter: SpanExporter) -> None:
        self._exporter = exporter

    def on_start(self, span: Span) -> None:
        pass

    def on_end(self, span: Span) -> None:
        try:
            self._exporter.export([span])
        except Exception:
            logger.warning("export failed for span %s", span.name, exc_info=True)

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._exporter.force_flush(timeout_millis)


class BatchProcessor:
    """Queues spans and exports in batches on a background thread."""

    def __init__(
        self,
        exporter: SpanExporter,
        *,
        max_queue_size: int = 2048,
        schedule_delay_ms: int = 5000,
        max_export_batch_size: int = 512,
    ) -> None:
        self._exporter = exporter
        self._max_batch = max_export_batch_size
        self._delay = schedule_delay_ms / 1000
        self._queue: queue.Queue[Span] = queue.Queue(maxsize=max_queue_size)
        self._done = threading.Event()
        self._worker = threading.Thread(target=self._loop, daemon=True)
        self._worker.start()

    def on_start(self, span: Span) -> None:
        pass

    def on_end(self, span: Span) -> None:
        try:
            self._queue.put_nowait(span)
        except queue.Full:
            logger.warning("batch processor queue full — dropping span %s", span.name)

    def shutdown(self) -> None:
        self._done.set()
        self._worker.join(timeout=5)
        self._drain()
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        self._drain()
        return self._exporter.force_flush(timeout_millis)

    def _loop(self) -> None:
        while not self._done.is_set():
            batch = self._collect_batch()
            if batch:
                self._export_batch(batch)

        # Drain anything remaining after shutdown signal
        self._drain()

    def _collect_batch(self) -> list[Span]:
        batch: list[Span] = []
        try:
            span = self._queue.get(timeout=self._delay)
            batch.append(span)
        except queue.Empty:
            return batch

        while len(batch) < self._max_batch:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def _drain(self) -> None:
        batch: list[Span] = []
        while True:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if batch:
            self._export_batch(batch)

    def _export_batch(self, batch: list[Span]) -> None:
        try:
            self._exporter.export(batch)
        except Exception:
            logger.warning("batch export failed (%d spans)", len(batch), exc_info=True)


class MultiProcessor:
    """Fans out events to multiple processors."""

    def __init__(self, processors: Sequence[SpanProcessor]) -> None:
        self._processors = list(processors)

    def on_start(self, span: Span) -> None:
        for p in self._processors:
            p.on_start(span)

    def on_end(self, span: Span) -> None:
        for p in self._processors:
            p.on_end(span)

    def shutdown(self) -> None:
        for p in self._processors:
            p.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        results = [p.force_flush(timeout_millis) for p in self._processors]
        return all(results) if results else True
