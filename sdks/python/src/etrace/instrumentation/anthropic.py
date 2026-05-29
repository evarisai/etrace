"""Anthropic auto-instrumentor.

Patches Anthropic messages (sync + async).
Uses etrace spans directly (no OTel dependency).
"""

from __future__ import annotations

import json
import logging
from typing import Any, ClassVar

from .base import BaseInstrumentor

logger = logging.getLogger("etrace.instrumentation")


class AnthropicInstrumentor(BaseInstrumentor):
    """Patches Anthropic messages (sync + async)."""

    name: ClassVar[str] = "anthropic"
    target_packages: ClassVar[list[str]] = ["anthropic"]

    def instrument(self, calc_costs: bool = True) -> bool:
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
        model = self._resolve_model(result, str(kwargs.get("model", "")))

        if kwargs.get("stream", False):
            span.attributes["gen_ai.streaming"] = True
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
                    self._capture_output(span, text)
                else:
                    # When no text, the LLM is requesting tool use.
                    tool_blocks = [b for b in content if getattr(b, "type", None) == "tool_use"]
                    if tool_blocks:
                        tc_data = [
                            {"name": getattr(b, "name", ""), "input": getattr(b, "input", {})} for b in tool_blocks
                        ]
                        self._capture_output(span, json.dumps(tc_data))
        except Exception:
            pass
