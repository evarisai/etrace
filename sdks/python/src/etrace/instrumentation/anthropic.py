"""Anthropic auto-instrumentor."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from etrace import MAX_ATTR_LEN

from .base import BaseInstrumentor

logger = logging.getLogger("etrace.instrumentation")


class AnthropicInstrumentor(BaseInstrumentor):
    """Patches Anthropic messages (sync + async)."""

    name: ClassVar[str] = "anthropic"
    target_packages: ClassVar[list[str]] = ["anthropic"]

    def instrument(self, tracer: Any, calc_costs: bool = True) -> bool:
        try:
            from anthropic.resources.messages import AsyncMessages, Messages
        except ImportError:
            logger.debug("anthropic not installed — skipping instrumentation")
            return False

        try:
            self._patch(
                Messages,
                "create",
                self._create_llm_wrapper_factory(
                    tracer,
                    "anthropic.messages",
                    "anthropic",
                    self._process_messages,
                    calc_costs=calc_costs,
                    is_async=False,
                ),
            )
            self._patch(
                AsyncMessages,
                "create",
                self._create_llm_wrapper_factory(
                    tracer,
                    "anthropic.messages",
                    "anthropic",
                    self._process_messages,
                    calc_costs=calc_costs,
                    is_async=True,
                ),
            )
        except Exception as exc:
            logger.warning("anthropic patch failed: %s", exc)
            self.uninstrument()
            return False

        logger.info("anthropic auto-instrumented (messages)")
        return True

    def _process_messages(
        self,
        span: Any,
        result: Any,
        kwargs: dict[str, Any],
        calc_costs: bool,
    ) -> None:
        model = kwargs.get("model", "")
        resp_model = getattr(result, "model", None)
        if resp_model:
            model = resp_model

        if kwargs.get("stream", False):
            span.set_attribute("gen_ai.streaming", True)
            return

        usage = getattr(result, "usage", None)
        if usage:
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0

            self._set_usage_and_cost(
                span,
                model,
                input_tokens,
                output_tokens,
                cached_tokens=cache_read,
                cache_write_tokens=cache_creation,
                calc_costs=calc_costs,
            )

        try:
            content = getattr(result, "content", None)
            if content:
                text = "".join(block.text for block in content if hasattr(block, "text") and block.text)
                if text:
                    span.set_attribute("gen_ai.output", text[:MAX_ATTR_LEN])
        except Exception:
            pass
