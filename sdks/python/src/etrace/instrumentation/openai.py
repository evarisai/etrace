"""OpenAI auto-instrumentor.

Patches OpenAI chat completions and embeddings (sync + async).
Uses etrace spans directly (no OTel dependency).
"""

from __future__ import annotations

import json
import logging
from typing import Any, ClassVar

from etrace import MAX_ATTR_LEN

from .base import BaseInstrumentor

logger = logging.getLogger("etrace.instrumentation")


class OpenAIInstrumentor(BaseInstrumentor):
    """Patches OpenAI chat completions and embeddings (sync + async)."""

    name: ClassVar[str] = "openai"
    target_packages: ClassVar[list[str]] = ["openai"]

    def instrument(self, calc_costs: bool = True) -> bool:
        try:
            from openai.resources.chat.completions import AsyncCompletions, Completions
            from openai.resources.embeddings import AsyncEmbeddings, Embeddings
        except ImportError:
            logger.debug("openai not installed — skipping instrumentation")
            return False

        try:
            self._patch(
                Completions,
                "create",
                self._create_llm_wrapper_factory(
                    "openai.chat",
                    "openai",
                    self._process_chat,
                    calc_costs=calc_costs,
                    is_async=False,
                ),
            )
            self._patch(
                AsyncCompletions,
                "create",
                self._create_llm_wrapper_factory(
                    "openai.chat",
                    "openai",
                    self._process_chat,
                    calc_costs=calc_costs,
                    is_async=True,
                ),
            )
            self._patch(
                Embeddings,
                "create",
                self._create_llm_wrapper_factory(
                    "openai.embeddings",
                    "openai",
                    self._process_embeddings,
                    calc_costs=calc_costs,
                    kind="embedding",
                    is_async=False,
                ),
            )
            self._patch(
                AsyncEmbeddings,
                "create",
                self._create_llm_wrapper_factory(
                    "openai.embeddings",
                    "openai",
                    self._process_embeddings,
                    calc_costs=calc_costs,
                    kind="embedding",
                    is_async=True,
                ),
            )
        except Exception as exc:
            logger.warning("openai patch failed: %s", exc)
            self.uninstrument()
            return False

        logger.info("openai auto-instrumented (chat + embeddings)")
        return True

    def _process_chat(
        self,
        span: Any,
        result: Any,
        kwargs: dict[str, Any],
        calc_costs: bool,
    ) -> None:
        # LangChain (and other frameworks) may use
        # client.chat.completions.with_raw_response.create(...) which
        # returns a LegacyAPIResponse wrapping the real ChatCompletion.
        if type(result).__name__ == "LegacyAPIResponse":
            parsed = result.parse()
        else:
            parsed = result

        model = self._resolve_model(parsed, str(kwargs.get("model", "")))

        if kwargs.get("stream", False):
            span.attributes["gen_ai.streaming"] = True
            # Streaming responses don't have .usage. Usage is only available
            # with stream_options={"include_usage": True}.
            return

        usage = getattr(parsed, "usage", None)
        if usage:
            prompt = getattr(usage, "prompt_tokens", 0) or 0
            completion = getattr(usage, "completion_tokens", 0) or 0
            total = getattr(usage, "total_tokens", 0) or 0

            cached_tokens = 0
            details = getattr(usage, "prompt_tokens_details", None)
            if details:
                cached_tokens = getattr(details, "cached_tokens", 0) or 0

            reasoning_tokens = 0
            comp_details = getattr(usage, "completion_tokens_details", None)
            if comp_details:
                reasoning_tokens = getattr(comp_details, "reasoning_tokens", 0) or 0

            self._set_usage_and_cost(
                span,
                model,
                prompt,
                completion,
                total,
                cached_tokens=cached_tokens,
                reasoning_tokens=reasoning_tokens,
                calc_costs=calc_costs,
            )

        try:
            choices = getattr(parsed, "choices", None)
            if choices:
                msg = getattr(choices[0], "message", None)
                if msg:
                    content = getattr(msg, "content", None)
                    if content:
                        self._capture_output(span, str(content))
                    else:
                        # When content is empty the LLM is requesting tool calls.
                        # Capture them so every LLM span has visible output.
                        tool_calls = getattr(msg, "tool_calls", None)
                        if tool_calls:
                            tc_data = []
                            for tc in tool_calls:
                                tc_data.append({
                                    "name": getattr(tc.function, "name", "") if hasattr(tc, "function") else getattr(tc, "name", ""),
                                    "arguments": getattr(tc.function, "arguments", "") if hasattr(tc, "function") else getattr(tc, "arguments", ""),
                                })
                            self._capture_output(span, json.dumps(tc_data))
        except Exception:
            pass

    def _process_embeddings(
        self,
        span: Any,
        result: Any,
        kwargs: dict[str, Any],
        calc_costs: bool,
    ) -> None:
        model = self._resolve_model(result, str(kwargs.get("model", "")))

        usage = getattr(result, "usage", None)
        if usage:
            prompt = getattr(usage, "prompt_tokens", 0) or 0
            total = getattr(usage, "total_tokens", 0) or 0
            self._set_usage_and_cost(span, model, prompt, 0, total, calc_costs=calc_costs)
