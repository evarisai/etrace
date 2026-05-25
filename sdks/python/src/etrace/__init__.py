"""
etrace — AI agent tracing library.

Zero-dep core. Everything is a span with a kind.

Usage:
    import etrace
    etrace.init()                  # In-memory (local dev)
    etrace.init(exporters=[...])   # Custom exporters
    etrace.init(processors=[...])  # Custom processors

    with etrace.trace("agent", kind="agent"):
        result = do_work()
"""

from __future__ import annotations

import asyncio
import atexit
import contextvars as _cv
import functools
import inspect
import json
import logging
import threading
import time
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from typing import Any, TypeVar

from ._exporter import InMemoryExporter
from ._processor import MultiProcessor, SimpleProcessor, SpanProcessor
from ._types import (
    ContextOptions,
    ScoreOptions,
    Span,
    TraceError,
    TraceEvent,
    TraceKind,
    TraceLevel,
    TraceStatus,
    Usage,
)

logger = logging.getLogger("etrace")

F = TypeVar("F", bound=Callable[..., Any])

# ── Global state ──────────────────────────────────────────────────────────────

_initialized = False
_lock = threading.Lock()
_processor: SpanProcessor | None = None
_exporters: list[Any] = []
_config: dict[str, Any] = {}
_calc_costs = True
MAX_ATTR_LEN = 100_000

_current_span: _cv.ContextVar[Span | None] = _cv.ContextVar("etrace_span", default=None)
_context_opts: _cv.ContextVar[ContextOptions | None] = _cv.ContextVar("etrace_ctx", default=None)


# ── Serialization helpers ─────────────────────────────────────────────────────


def _ser(v: Any) -> str:
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, default=str)
    except Exception:
        return str(v)


# ── Public API: Context ───────────────────────────────────────────────────────


def set_context(options: ContextOptions) -> None:
    """Merge context that propagates to all child spans."""
    cur = _context_opts.get() or ContextOptions()
    _context_opts.set(
        ContextOptions(
            user_id=options.user_id or cur.user_id,
            session_id=options.session_id or cur.session_id,
            conversation_id=options.conversation_id or cur.conversation_id,
            eval_run_id=options.eval_run_id or cur.eval_run_id,
            tags=list(set((cur.tags or []) + (options.tags or []))),
            version=options.version or cur.version,
            release=options.release or cur.release,
        )
    )


def get_context() -> ContextOptions:
    return _context_opts.get() or ContextOptions()


def get_current_span() -> Span | None:
    return _current_span.get()


# ── Public API: init() ────────────────────────────────────────────────────────


def init(
    *,
    service_name: str = "etrace-app",
    environment: str = "production",
    exporters: list[Any] | None = None,
    processors: list[SpanProcessor] | None = None,
    auto_instrument: dict[str, bool] | None = None,
    calculate_costs: bool = True,
    debug: bool = False,
    version: str | None = None,
    release: str | None = None,
) -> None:
    """
    Initialize tracing.

    Args:
        exporters: List of SpanExporter instances. Default: [InMemoryExporter()].
        processors: List of SpanProcessor instances. If provided, exporters is ignored.
        auto_instrument: Which providers to auto-instrument. Default: {"llm": True}.
        calculate_costs: Auto-calculate costs from pricing catalog.
        debug: Enable debug logging.
    """
    global _initialized, _processor, _exporters, _config, _calc_costs

    with _lock:
        if _initialized:
            return

        _calc_costs = calculate_costs

        if debug:
            logging.getLogger("etrace").setLevel(logging.DEBUG)

        _config = {
            "service_name": service_name,
            "environment": environment,
            "version": version,
            "release": release,
        }

        if auto_instrument is None:
            auto_instrument = {"llm": True}

        # Build processor pipeline
        if processors:
            _processor = MultiProcessor(processors) if len(processors) > 1 else processors[0]
            _exporters = []
        elif exporters:
            _exporters = list(exporters)
            procs = [SimpleProcessor(e) for e in _exporters]
            _processor = MultiProcessor(procs) if len(procs) > 1 else procs[0]
        else:
            mem = InMemoryExporter()
            _exporters = [mem]
            _processor = SimpleProcessor(mem)

        if auto_instrument.get("llm", True):
            _init_instrumentation()

        _initialized = True
        atexit.register(shutdown)
        logger.info("etrace initialized (service=%s)", service_name)


def _init_instrumentation() -> None:
    try:
        from .instrumentation import instrument_all

        instrument_all(None, _calc_costs)
    except Exception as e:
        logger.warning("Auto-instrumentation failed (non-fatal): %s", e)


# ── Public API: trace() ──────────────────────────────────────────────────────


@contextmanager
def trace(
    name: str,
    kind: TraceKind = TraceKind.CUSTOM,
    input: Any | None = None,
    *,
    model: str | None = None,
    provider: str | None = None,
    attributes: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    level: TraceLevel | None = None,
    version: str | None = None,
    release: str | None = None,
    model_parameters: dict[str, Any] | None = None,
    prompt_id: str | None = None,
) -> Generator[Span, None, None]:
    """Create a traced span. Everything is a span with a kind."""
    if not _initialized or not _processor:
        yield from _run_span(
            name,
            kind,
            input,
            model,
            provider,
            tags,
            level,
            version,
            release,
            model_parameters,
            prompt_id,
            attributes,
            processor=None,
        )
        return

    span, token, start = _start_span(
        name, kind, input, model, provider, tags, level, version, release, model_parameters, prompt_id, attributes
    )
    try:
        yield span
        if span.status == TraceStatus.UNSET:
            span.status = TraceStatus.OK
    except Exception as e:
        span.error = TraceError(message=str(e), type=type(e).__name__)
        span.status = TraceStatus.ERROR
        raise
    finally:
        _finish_span(span, token, start)


def _run_span(
    name: str,
    kind: TraceKind,
    input: Any | None,
    model: str | None,
    provider: str | None,
    tags: list[str] | None,
    level: TraceLevel | None,
    version: str | None,
    release: str | None,
    model_parameters: dict[str, Any] | None,
    prompt_id: str | None,
    attributes: dict[str, Any] | None,
    *,
    processor: SpanProcessor | None = None,
) -> Generator[Span, None, None]:
    """Unified span lifecycle for both active and noop mode."""
    span, token, start = _start_span(
        name, kind, input, model, provider, tags, level, version, release, model_parameters, prompt_id, attributes
    )
    try:
        yield span
        if span.status == TraceStatus.UNSET:
            span.status = TraceStatus.OK
    except Exception as e:
        span.error = TraceError(message=str(e), type=type(e).__name__)
        span.status = TraceStatus.ERROR
        raise
    finally:
        _finish_span(span, token, start, processor=processor)


def _start_span(
    name: str,
    kind: TraceKind,
    input: Any | None,
    model: str | None,
    provider: str | None,
    tags: list[str] | None,
    level: TraceLevel | None,
    version: str | None,
    release: str | None,
    model_parameters: dict[str, Any] | None,
    prompt_id: str | None,
    attributes: dict[str, Any] | None,
) -> tuple[Span, Any, float]:
    """Create, populate, and activate a new span. Returns (span, token, start_time)."""
    ctx = _context_opts.get() or ContextOptions()
    parent = _current_span.get()

    span = _make_span(name, kind, input=input, model=model, provider=provider)
    span.trace_id = parent.trace_id if parent else span.trace_id
    span.parent_span_id = parent.span_id if parent else None
    span.tags = tags or []
    span.level = level or TraceLevel.DEFAULT
    span.version = version or ctx.version
    span.release = release or ctx.release
    span.user_id = ctx.user_id
    span.session_id = ctx.session_id
    span.conversation_id = ctx.conversation_id
    span.model_parameters = model_parameters
    span.prompt_id = prompt_id
    if attributes:
        span.attributes.update(attributes)

    token = _current_span.set(span)
    start = time.monotonic()

    if _processor:
        _processor.on_start(span)

    return span, token, start


def _finish_span(
    span: Span,
    token: Any,
    start: float,
    *,
    processor: SpanProcessor | None = None,
) -> None:
    """Finalize and deactivate a span."""
    _end_span(span, start)
    _current_span.reset(token)
    proc = processor or _processor
    if proc:
        proc.on_end(span)


# ── Public API: @observe ──────────────────────────────────────────────────────


def observe(
    _func: F | None = None,
    *,
    name: str | None = None,
    kind: TraceKind = TraceKind.CUSTOM,
    capture_input: bool = True,
    capture_output: bool = True,
    **kwargs: Any,
) -> Callable[[F], F] | F:
    """Decorator to trace any function."""

    def decorator(fn: F) -> F:
        tname = name or fn.__name__ or kind.value

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kw: Any) -> Any:
            captured = _capture_args(fn, args, kw) if capture_input else None
            with trace(tname, kind=kind, input=captured, **kwargs) as span:
                result = fn(*args, **kw)
                if capture_output:
                    span.output = result
                return result

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kw: Any) -> Any:
            captured = _capture_args(fn, args, kw) if capture_input else None
            with trace(tname, kind=kind, input=captured, **kwargs) as span:
                result = await fn(*args, **kw)
                if capture_output:
                    span.output = result
                return result

        if asyncio.iscoroutinefunction(fn):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    if _func is not None:
        return decorator(_func)
    return decorator


# ── Convenience decorators ────────────────────────────────────────────────────


def workflow(func: Any = None, **kw: Any) -> Any:
    return observe(func, kind=TraceKind.WORKFLOW, **kw)


def agent(func: Any = None, **kw: Any) -> Any:
    return observe(func, kind=TraceKind.AGENT, **kw)


def step(func: Any = None, **kw: Any) -> Any:
    return observe(func, kind=TraceKind.STEP, **kw)


def tool(func: Any = None, **kw: Any) -> Any:
    return observe(func, kind=TraceKind.TOOL, **kw)


def llm(func: Any = None, **kw: Any) -> Any:
    return observe(func, kind=TraceKind.LLM, **kw)


def http(func: Any = None, **kw: Any) -> Any:
    return observe(func, kind=TraceKind.HTTP, **kw)


def retrieval(func: Any = None, **kw: Any) -> Any:
    return observe(func, kind=TraceKind.RETRIEVAL, **kw)


def reranker(func: Any = None, **kw: Any) -> Any:
    return observe(func, kind=TraceKind.RERANKER, **kw)


def embedding(func: Any = None, **kw: Any) -> Any:
    return observe(func, kind=TraceKind.EMBEDDING, **kw)


def sandbox(func: Any = None, **kw: Any) -> Any:
    return observe(func, kind=TraceKind.SANDBOX, **kw)


def handoff(func: Any = None, **kw: Any) -> Any:
    return observe(func, kind=TraceKind.HANDOFF, **kw)


def approval(func: Any = None, **kw: Any) -> Any:
    return observe(func, kind=TraceKind.APPROVAL, **kw)


def guardrail(func: Any = None, **kw: Any) -> Any:
    return observe(func, kind=TraceKind.GUARDRAIL, **kw)


def evaluation(func: Any = None, **kw: Any) -> Any:
    return observe(func, kind=TraceKind.EVAL, **kw)


def scorer(func: Any = None, **kw: Any) -> Any:
    return observe(func, kind=TraceKind.SCORER, **kw)


# ── Span enrichment ───────────────────────────────────────────────────────────


def set_usage(
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    cached_tokens: int = 0,
    reasoning_tokens: int = 0,
    model: str | None = None,
) -> Usage:
    """Set token usage on the current span.

    When calculate_costs=True (default in init()), costs are auto-populated
    by delegating to calculate_usage_cost().
    """
    span = _current_span.get()
    if not span:
        logger.debug("set_usage() called without an active span")
        return Usage()

    total = total_tokens or (input_tokens + output_tokens)
    usage = Usage(
        input=input_tokens,
        output=output_tokens,
        total=total,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
    )
    span.usage = usage
    if model:
        span.model = model

    if _calc_costs:
        resolved_model = model or span.model
        if resolved_model:
            span.usage = calculate_usage_cost(usage, model=resolved_model)

    return span.usage


def calculate_usage_cost(usage: Usage, *, model: str | None = None) -> Usage:
    """Calculate cost for a Usage object. Pure function — no span mutation.

    Returns a NEW Usage with calculated_* and input/output/total_cost populated.
    The original Usage is not modified.
    """
    if not model:
        return Usage(
            input=usage.input,
            output=usage.output,
            total=usage.total,
            cached_tokens=usage.cached_tokens,
            reasoning_tokens=usage.reasoning_tokens,
        )

    try:
        from ._pricing import calculate_cost

        costs = calculate_cost(
            model,
            usage.input,
            usage.output,
            cached_tokens=usage.cached_tokens,
            reasoning_tokens=usage.reasoning_tokens,
        )
    except Exception as exc:
        logger.warning("Cost calculation failed for model '%s': %s", model, exc)
        return Usage(
            input=usage.input,
            output=usage.output,
            total=usage.total,
            cached_tokens=usage.cached_tokens,
            reasoning_tokens=usage.reasoning_tokens,
        )

    if not costs:
        return Usage(
            input=usage.input,
            output=usage.output,
            total=usage.total,
            cached_tokens=usage.cached_tokens,
            reasoning_tokens=usage.reasoning_tokens,
        )

    result = Usage(
        input=usage.input,
        output=usage.output,
        total=usage.total,
        cached_tokens=usage.cached_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        calculated_input_cost=costs["input_cost"],
        calculated_output_cost=costs["output_cost"],
        calculated_total_cost=costs["total_cost"],
        input_cost=costs["input_cost"],
        output_cost=costs["output_cost"],
        total_cost=costs["total_cost"],
    )
    return result


def set_output(value: Any) -> None:
    span = _current_span.get()
    if span:
        span.output = value


def set_error(message: str, error_type: str | None = None) -> None:
    span = _current_span.get()
    if span:
        span.error = TraceError(message=message, type=error_type)
        span.status = TraceStatus.ERROR


def set_attribute(key: str, value: Any) -> None:
    span = _current_span.get()
    if span:
        span.attributes[key] = value


def score(options: ScoreOptions) -> dict[str, Any]:
    """Attach a score to a trace."""
    current = _current_span.get()
    trace_id = options.trace_id or (current.trace_id if current else None)
    if not trace_id:
        raise ValueError("Cannot score: no trace_id. Pass trace_id= or call score() within a trace context.")

    if current:
        current.events.append(
            TraceEvent(
                name="score",
                timestamp=datetime.now(UTC).isoformat(),
                attributes={"score_name": options.name, "score_value": str(options.value)},
            )
        )

    logger.info("score recorded: %s=%s (trace_id=%s)", options.name, options.value, trace_id)
    return {"trace_id": trace_id, "name": options.name, "value": options.value}


# ── Lifecycle ─────────────────────────────────────────────────────────────────


def flush(timeout_ms: int = 30000) -> bool:
    if _processor:
        try:
            return _processor.force_flush(timeout_ms)
        except Exception:
            return False
    return True


def shutdown() -> None:
    global _initialized, _processor, _exporters

    with _lock:
        try:
            from .instrumentation import uninstrument_all

            uninstrument_all()
        except Exception:
            pass

        if _processor:
            with suppress(Exception):
                _processor.shutdown()
            _processor = None
        _exporters = []
        _initialized = False


def is_initialized() -> bool:
    return _initialized


# ── Internal helpers ──────────────────────────────────────────────────────────


def _make_span(
    name: str,
    kind: TraceKind,
    input: Any = None,
    model: str | None = None,
    provider: str | None = None,
) -> Span:
    return Span(
        trace_id=uuid.uuid4().hex,
        span_id=uuid.uuid4().hex[:16],
        name=name,
        kind=kind,
        status=TraceStatus.UNSET,
        started_at=datetime.now(UTC).isoformat(),
        input=input,
        model=model,
        provider=provider,
    )


def _end_span(span: Span, start_monotonic: float) -> None:
    span.ended_at = datetime.now(UTC).isoformat()
    span.duration_ns = int((time.monotonic() - start_monotonic) * 1_000_000_000)


def _capture_args(
    fn: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    max_len: int = 10_000,
) -> dict[str, Any]:
    try:
        sig = inspect.signature(fn)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        result = {}
        for key, val in bound.arguments.items():
            if key in ("self", "cls"):
                continue
            s = _ser(val)
            result[key] = s[:max_len] if len(s) > max_len else val
        return result
    except Exception:
        return {"args": [str(a)[:max_len] for a in args[:10]]}
