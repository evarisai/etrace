"""Base class for LLM provider auto-instrumentors."""

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

try:
    from opentelemetry import context as _otel_ctx
    from opentelemetry import trace as _otel_trace
except ImportError:
    _otel_ctx = None  # type: ignore[assignment]
    _otel_trace = None  # type: ignore[assignment]


class BaseInstrumentor:
    """Base class for auto-instrumentation of LLM providers."""

    name: ClassVar[str] = ""
    target_packages: ClassVar[list[str]] = []

    def __init__(self) -> None:
        self._originals: list[tuple[Any, str, Any]] = []

    def instrument(self, tracer: Any, calc_costs: bool = True) -> bool:
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
        wrapped._evaris_original = original
        setattr(obj, method, wrapped)
        self._originals.append((obj, method, original))

    def _create_llm_wrapper_factory(
        self,
        tracer: Any,
        span_name: str,
        provider: str,
        process_fn: Callable[[Any, Any, dict[str, Any], bool], None],
        *,
        calc_costs: bool = True,
        kind: str = "llm",
        is_async: bool = False,
    ) -> Callable[[Any], Any]:
        inst = self

        def factory(original: Any) -> Any:
            if is_async:

                @functools.wraps(original)
                async def wrapper(*args: Any, **kwargs: Any) -> Any:
                    span, tok = inst._start_llm(tracer, span_name, provider, kwargs, kind=kind)
                    try:
                        result = await original(*args, **kwargs)
                    except Exception as exc:
                        inst._end_llm(span, tok, error=exc)
                        raise
                    process_fn(span, result, kwargs, calc_costs)
                    inst._end_llm(span, tok)
                    return result

                return wrapper
            else:

                @functools.wraps(original)
                def wrapper(*args: Any, **kwargs: Any) -> Any:
                    span, tok = inst._start_llm(tracer, span_name, provider, kwargs, kind=kind)
                    try:
                        result = original(*args, **kwargs)
                    except Exception as exc:
                        inst._end_llm(span, tok, error=exc)
                        raise
                    process_fn(span, result, kwargs, calc_costs)
                    inst._end_llm(span, tok)
                    return result

                return wrapper

        return factory

    def _start_llm(
        self,
        tracer: Any,
        span_name: str,
        provider: str,
        kwargs: dict[str, Any],
        *,
        kind: str = "llm",
    ) -> tuple[Any, Any]:
        model = kwargs.get("model", "")
        attrs: dict[str, Any] = {
            "evaris.kind": kind,
            "gen_ai.system": provider,
            "gen_ai.request.model": str(model),
        }

        messages = kwargs.get("messages")
        if messages:
            with contextlib.suppress(Exception):
                attrs["gen_ai.input.messages"] = json.dumps(messages, default=str)[:MAX_ATTR_LEN]

        span = tracer.start_span(span_name, attributes=attrs)
        ctx = _otel_trace.set_span_in_context(span)
        token = _otel_ctx.attach(ctx)
        return span, token

    def _end_llm(
        self,
        span: Any,
        ctx_token: Any,
        error: BaseException | None = None,
    ) -> None:
        if error is not None:
            span.set_status(_otel_trace.StatusCode.ERROR, str(error))
            span.record_exception(error)
        else:
            span.set_status(_otel_trace.StatusCode.OK)

        _otel_ctx.detach(ctx_token)
        span.end()

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
        span.set_attribute("gen_ai.usage.prompt_tokens", prompt_tokens)
        span.set_attribute("gen_ai.usage.completion_tokens", completion_tokens)
        span.set_attribute(
            "gen_ai.usage.total_tokens",
            total_tokens or (prompt_tokens + completion_tokens),
        )
        if cached_tokens:
            span.set_attribute("gen_ai.usage.cache_read_tokens", cached_tokens)
        if reasoning_tokens:
            span.set_attribute("gen_ai.usage.reasoning_tokens", reasoning_tokens)
        if cache_write_tokens:
            span.set_attribute("gen_ai.usage.cache_write_tokens", cache_write_tokens)
        if calc_costs and model:
            costs = calculate_cost(
                model,
                prompt_tokens,
                completion_tokens,
                cached_tokens=cached_tokens,
                reasoning_tokens=reasoning_tokens,
            )
            if costs:
                span.set_attribute("gen_ai.usage.cost", costs.get("total_cost", 0))
                span.set_attribute("gen_ai.usage.input_cost", costs.get("input_cost", 0))
                span.set_attribute("gen_ai.usage.output_cost", costs.get("output_cost", 0))
                span.set_attribute("gen_ai.usage.calculated_cost", costs.get("total_cost", 0))
