"""Base class for LLM provider auto-instrumentors.

Uses etrace spans directly (no OTel tracer dependency).
Every instrumentor follows the same pattern:
  1. Try to import the target package.
  2. Patch specific methods with wrappers that emit etrace spans.
  3. Extract usage (tokens) from the response.
  4. Auto-calculate cost from the pricing catalog.
  5. Restore originals on uninstrument().
"""

from __future__ import annotations

import contextlib
import functools
import json
import logging
from typing import TYPE_CHECKING, Any, ClassVar

from .. import MAX_ATTR_LEN
from .._pricing import calculate_cost

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("etrace.instrumentation")


class BaseInstrumentor:
    """Base class for auto-instrumentation of LLM providers."""

    name: ClassVar[str] = ""
    target_packages: ClassVar[list[str]] = []

    def __init__(self) -> None:
        self._originals: list[tuple[Any, str, Any]] = []
        self._calc_costs: bool = True

    def instrument(self, calc_costs: bool = True) -> bool:
        raise NotImplementedError

    def uninstrument(self) -> None:
        for obj, attr, original in self._originals:
            with contextlib.suppress(Exception):
                setattr(obj, attr, original)
        self._originals.clear()

    def _patch(
        self,
        obj: Any,
        method: str,
        factory: Callable[..., Any],
    ) -> None:
        original = getattr(obj, method)
        wrapped = factory(original)
        functools.update_wrapper(wrapped, original)
        wrapped._etrace_original = original
        setattr(obj, method, wrapped)
        self._originals.append((obj, method, original))

    # ── Shared LLM call wrapper ──────────────────────────────────────────

    def _create_llm_wrapper_factory(
        self,
        span_name: str,
        provider: str,
        process_fn: Callable[[Any, Any, dict[str, Any], bool], None],
        *,
        calc_costs: bool = True,
        kind: str = "llm",
        is_async: bool = False,
    ) -> Callable[[Any], Any]:
        """Create a wrapper factory that uses etrace.trace() internally."""
        inst = self

        def _trace_and_process(span, model, result, kwargs):
            """Post-result processing shared by sync and async wrappers."""
            if not span:
                return
            resolved_model = inst._resolve_model(result, model)
            span.model = resolved_model
            process_fn(span, result, kwargs, calc_costs)

        def factory(original: Any) -> Any:
            if is_async:

                @functools.wraps(original)
                async def wrapper(*args: Any, **kwargs: Any) -> Any:
                    from .. import trace as etrace_trace, get_current_span
                    from .._types import TraceKind

                    trace_kind = TraceKind(kind) if kind in ("llm", "embedding") else TraceKind.LLM
                    model = str(kwargs.get("model", ""))

                    with etrace_trace(
                        span_name,
                        kind=trace_kind,
                        model=model,
                        provider=provider,
                        input=kwargs.get("messages"),
                    ):
                        span = get_current_span()
                        if span:
                            inst._set_semconv_attrs(span, provider, model)
                            inst._capture_input(span, kwargs)

                        result = await original(*args, **kwargs)
                        _trace_and_process(span, model, result, kwargs)
                        return result

                return wrapper
            else:

                @functools.wraps(original)
                def wrapper(*args: Any, **kwargs: Any) -> Any:
                    from .. import trace as etrace_trace, get_current_span
                    from .._types import TraceKind

                    trace_kind = TraceKind(kind) if kind in ("llm", "embedding") else TraceKind.LLM
                    model = str(kwargs.get("model", ""))

                    with etrace_trace(
                        span_name,
                        kind=trace_kind,
                        model=model,
                        provider=provider,
                        input=kwargs.get("messages"),
                    ):
                        span = get_current_span()
                        if span:
                            inst._set_semconv_attrs(span, provider, model)
                            inst._capture_input(span, kwargs)

                        result = original(*args, **kwargs)
                        _trace_and_process(span, model, result, kwargs)
                        return result

                return wrapper

        return factory

    # ── Helpers ───────────────────────────────────────────────────────────

    def _set_semconv_attrs(self, span: Any, provider: str, model: str) -> None:
        """Set semantic convention attributes on an etrace span."""
        span.attributes["gen_ai.system"] = provider
        if model:
            span.attributes["gen_ai.request.model"] = model
        span.attributes["etrace.kind"] = span.kind.value

    def _capture_input(self, span: Any, kwargs: dict[str, Any]) -> None:
        """Capture input messages on the span."""
        messages = kwargs.get("messages")
        if messages:
            with contextlib.suppress(Exception):
                span.attributes["gen_ai.input.messages"] = json.dumps(messages, default=str)[
                    :MAX_ATTR_LEN
                ]

    def _capture_output(self, span: Any, text: str) -> None:
        """Capture output text on the span."""
        span.attributes["gen_ai.output"] = text[:MAX_ATTR_LEN]
        span.output = text[:MAX_ATTR_LEN]

    def _resolve_model(self, result: Any, request_model: str) -> str:
        """Use response model if available, otherwise fall back to request model."""
        resp_model = getattr(result, "model", None)
        return resp_model if resp_model else request_model

    def _set_usage_and_cost(
        self,
        span: Any,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int = 0,
        cached_tokens: int = 0,
        reasoning_tokens: int = 0,
        cache_write_tokens: int = 0,
        calc_costs: bool = True,
    ) -> None:
        """Set token usage attributes and auto-calculate cost on an etrace span."""
        total = total_tokens or (prompt_tokens + completion_tokens)

        span.attributes["gen_ai.usage.prompt_tokens"] = prompt_tokens
        span.attributes["gen_ai.usage.completion_tokens"] = completion_tokens
        span.attributes["gen_ai.usage.total_tokens"] = total
        if cached_tokens:
            span.attributes["gen_ai.usage.cache_read_tokens"] = cached_tokens
        if reasoning_tokens:
            span.attributes["gen_ai.usage.reasoning_tokens"] = reasoning_tokens
        if cache_write_tokens:
            span.attributes["gen_ai.usage.cache_write_tokens"] = cache_write_tokens

        # Use etrace's set_usage for proper cost tracking
        from .. import set_usage

        set_usage(
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            total_tokens=total,
            cached_tokens=cached_tokens,
            reasoning_tokens=reasoning_tokens,
            model=model,
        )
