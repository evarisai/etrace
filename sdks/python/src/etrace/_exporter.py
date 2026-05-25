"""SpanExporter protocol and built-in implementations."""

from __future__ import annotations

import contextlib
import sys
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from etrace._types import Span


class SpanExportResult(Enum):
    SUCCESS = "success"
    FAILURE = "failure"


@runtime_checkable
class SpanExporter(Protocol):
    """Protocol all exporters must satisfy."""

    def export(self, spans: Sequence[Span]) -> SpanExportResult: ...
    def shutdown(self) -> None: ...
    def force_flush(self, timeout_millis: int = 30_000) -> bool: ...


class InMemoryExporter:
    """Accumulates spans in a list. For testing and local dev."""

    def __init__(self) -> None:
        self._spans: list[Span] = []

    def export(self, spans: Sequence[Span]) -> SpanExportResult:
        self._spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True

    def get_finished_spans(self) -> list[Span]:
        return list(self._spans)

    def clear(self) -> None:
        self._spans.clear()


class ConsoleExporter:
    """Prints spans to stdout (or custom stream). For debugging."""

    def __init__(self, out: Any = None) -> None:
        self._out = out or sys.stdout

    def export(self, spans: Sequence[Span]) -> SpanExportResult:
        for span in spans:
            with contextlib.suppress(Exception):
                print(
                    f"[etrace] {span.name} kind={span.kind.value} "
                    f"status={span.status.value} duration={span.duration_ns}ns",
                    file=self._out,
                )
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True
