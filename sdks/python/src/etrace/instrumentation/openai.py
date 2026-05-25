"""OpenAI auto-instrumentor."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from etrace import MAX_ATTR_LEN

from .base import BaseInstrumentor

logger = logging.getLogger("etrace.instrumentation")


class OpenAIInstrumentor(BaseInstrumentor):
    """Patches OpenAI chat completions and embeddings (sync + async)."""

    name: ClassVar[str] = "openai"
    target_packages: ClassVar[list[str]] = ["openai"]

    def instrument(self, tracer: Any, calc_costs: bool = True) -> bool:
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
                    tracer,
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
                    tracer,
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
                    tracer,
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
                    tracer,
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
        model = kwargs.get("model", "")

        if kwargs.get("stream", False):
            span.set_attribute("gen_ai.streaming", True)
            # Streaming responses don't have .usage. Usage is only available
            # with stream_options={"include_usage": True}.
            return

        resp_model = getattr(result, "model", None)
        if resp_model:
            model = resp_model

        usage = getattr(result, "usage", None)
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
            choices = getattr(result, "choices", None)
            if choices:
                msg = getattr(choices[0], "message", None)
                if msg:
                    content = getattr(msg, "content", None)
                    if content:
                        span.set_attribute("gen_ai.output", str(content)[:MAX_ATTR_LEN])
        except Exception:
            pass

    def _process_embeddings(
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

        usage = getattr(result, "usage", None)
        if usage:
            prompt = getattr(usage, "prompt_tokens", 0) or 0
            total = getattr(usage, "total_tokens", 0) or 0
            self._set_usage_and_cost(span, model, prompt, 0, total, calc_costs=calc_costs)
