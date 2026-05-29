"""Generic run-based tracing for agent frameworks.

Provides :class:`RunTracker`, a framework-agnostic mixin that maps
``run_id`` / ``parent_run_id`` pairs to etrace spans with correct
parent-child nesting.  Framework-specific adapters (LangChain, CrewAI,
AutoGen, …) compose ``RunTracker`` with the framework's callback base
class and translate events into the generic ``on_run_*`` API.

Minimal usage::

    from etrace.tracing import RunTracker

    tracker = RunTracker()

    # Framework adapter calls these:
    rid  = tracker.on_run_start("openai.chat", kind="llm", parent_run_id=None)
    tracker.on_run_end(rid, output="Paris", usage={"prompt_tokens": 100, ...})
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from ._types import Span, TraceKind, TraceStatus

logger = logging.getLogger("etrace.tracing")


class RunTracker:
    """Generic run tracker that produces etrace spans.

    Maintains a mapping of ``run_id`` → pending span so that
    ``parent_run_id`` can be resolved to the correct etrace parent.
    Callers (framework adapters) create unique ``run_id`` values and
    pass ``parent_run_id`` to establish nesting.
    """

    def __init__(self) -> None:
        self._spans: dict[str, _Run | None] = {}
        self._root_trace_id: str | None = None
        self._root_parent_span_id: str | None = None

        # Inherit from an active etrace.trace() context if one exists
        from . import get_current_span

        active = get_current_span()
        if active:
            self._root_trace_id = active.trace_id
            self._root_parent_span_id = active.span_id

    # ── Public run lifecycle ─────────────────────────────────────────────

    def on_run_start(
        self,
        name: str,
        *,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        kind: TraceKind | str = TraceKind.CUSTOM,
        input: Any = None,
        model: str | None = None,
        provider: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> str:
        """Start a new traced run.  Returns the ``run_id``."""
        from . import _processor

        rid = run_id or uuid.uuid4().hex

        if isinstance(kind, str):
            try:
                kind = TraceKind(kind.lower())
            except ValueError:
                kind = TraceKind.CUSTOM

        span = Span(
            trace_id=self._root_trace_id or uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name=name,
            kind=kind,
            status=TraceStatus.UNSET,
            started_at=datetime.now(UTC).isoformat(),
            input=input,
            model=model,
            provider=provider,
        )
        if attributes:
            span.attributes.update(attributes)

        # Resolve parent by walking up the run tree, skipping runs
        # that have no span (e.g. chain nodes that are internal plumbing).
        resolved_parent = self._resolve_parent(parent_run_id)
        if resolved_parent:
            span.trace_id = resolved_parent.trace_id
            span.parent_span_id = resolved_parent.span_id
        elif self._root_parent_span_id:
            # No etrace parent found in the run tree — either this is a
            # top-level run or all ancestors were skipped (chain plumbing).
            # Attach to the active etrace.trace() context.
            span.parent_span_id = self._root_parent_span_id
            if self._root_trace_id:
                span.trace_id = self._root_trace_id

        # First run establishes the trace ID
        if self._root_trace_id is None:
            self._root_trace_id = span.trace_id

        # Set _current_span so that nested etrace.trace() / @etrace.tool
        # calls inside this run become children of this span.
        from . import _current_span

        cv_token = _current_span.set(span)

        self._spans[rid] = _Run(span=span, start=time.monotonic(), parent_run_id=parent_run_id, _cv_token=cv_token)

        if _processor:
            _processor.on_start(span)

        return rid

    def on_run_end(
        self,
        run_id: str,
        *,
        output: Any = None,
        status: TraceStatus = TraceStatus.OK,
        usage: dict[str, int] | None = None,
        model: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """End a traced run and export the span."""
        from . import _processor

        run = self._spans.get(run_id)
        if not run or not run.span:
            return

        span = run.span

        if output is not None:
            span.output = output

        if model:
            span.model = model

        if status:
            span.status = status

        if attributes:
            span.attributes.update(attributes)

        if usage:
            self._apply_usage(span, usage)

        span.ended_at = datetime.now(UTC).isoformat()
        span.duration_ns = int((time.monotonic() - run.start) * 1_000_000_000)

        # Restore previous _current_span so we don't leak context
        if run._cv_token is not None:
            from . import _current_span

            _current_span.reset(run._cv_token)

        if _processor:
            _processor.on_end(span)

    def on_run_error(
        self,
        run_id: str,
        error: BaseException,
    ) -> None:
        """End a run with an error status."""
        self.on_run_end(
            run_id,
            output=str(error)[:100_000],
            status=TraceStatus.ERROR,
        )

    def flush(self) -> None:
        """Close any remaining open runs."""
        for rid in list(self._spans):
            run = self._spans.get(rid)
            if run and run.span and run.span.status == TraceStatus.UNSET:
                self.on_run_end(rid)

    # ── Usage helpers ────────────────────────────────────────────────────

    def _resolve_parent(self, run_id: str | None) -> Span | None:
        """Walk up the run tree to find the nearest ancestor that has a span."""
        visited = set()
        current = run_id
        while current and current not in visited:
            visited.add(current)
            run = self._spans.get(current)
            if run is None:
                return None
            if run.span:
                return run.span
            # This run has no span (chain plumbing) — walk up to its parent.
            # We need to track parent_run_id per run for this lookup.
            current = run.parent_run_id
        return None

    def _apply_usage(
        self,
        span: Span,
        usage: dict[str, int],
    ) -> None:
        """Set token usage attributes and trigger cost calculation."""
        prompt = usage.get("prompt_tokens", 0) or 0
        completion = usage.get("completion_tokens", 0) or 0
        total = usage.get("total_tokens", 0) or (prompt + completion)
        cached = usage.get("cached_tokens", 0) or 0
        reasoning = usage.get("reasoning_tokens", 0) or 0

        span.attributes["gen_ai.usage.prompt_tokens"] = prompt
        span.attributes["gen_ai.usage.completion_tokens"] = completion
        span.attributes["gen_ai.usage.total_tokens"] = total
        if cached:
            span.attributes["gen_ai.usage.cache_read_tokens"] = cached
        if reasoning:
            span.attributes["gen_ai.usage.reasoning_tokens"] = reasoning

        model = str(span.model or usage.get("model", ""))
        if model and (prompt or completion):
            from . import set_usage

            set_usage(
                input_tokens=prompt,
                output_tokens=completion,
                total_tokens=total,
                cached_tokens=cached,
                reasoning_tokens=reasoning,
                model=model,
            )


class _Run:
    """An in-flight run tied to a single etrace span."""

    __slots__ = ("_cv_token", "parent_run_id", "span", "start")

    def __init__(
        self, span: Span | None, start: float, parent_run_id: str | None = None, _cv_token: Any = None
    ) -> None:
        self.span = span
        self.start = start
        self.parent_run_id = parent_run_id
        self._cv_token = _cv_token
