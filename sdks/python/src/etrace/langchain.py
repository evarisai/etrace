"""Callback adapter for framework-driven agent tracing.

Translates callback events into the generic :class:`~etrace.tracing.RunTracker`
API so that LLM calls, tool executions, and chain steps become properly nested
etrace spans.

Usage::

    from etrace.langchain import EtraceLangChainHandler

    handler = EtraceLangChainHandler()
    result = agent.invoke(
        {"messages": [HumanMessage(content="...")]},
        config={"callbacks": [handler]},
    )

The handler is auto-registered when the supported callback package is installed
and ``etrace.init()`` is called with callback integration enabled.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from .tracing import RunTracker, _Run

logger = logging.getLogger("etrace.langchain")

if TYPE_CHECKING:
    from uuid import UUID

try:
    from langchain_core.callbacks import BaseCallbackHandler  # type: ignore[import-not-found]

    _HAS_LANGCHAIN = True
except ImportError:
    # Provide a stub so the class can still be imported for type checking
    class BaseCallbackHandler:  # type: ignore[no-redef]
        pass

    _HAS_LANGCHAIN = False


def _serialize_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """Convert callback message objects to a serializable list."""
    result = []
    for msg in messages:
        entry = {
            "role": getattr(msg, "type", "unknown"),
            "content": getattr(msg, "content", ""),
        }
        tc = getattr(msg, "tool_calls", None)
        if tc:
            entry["tool_calls"] = [{"name": t.get("name"), "args": t.get("args")} for t in tc]
        result.append(entry)
    return result


class EtraceLangChainHandler(BaseCallbackHandler):  # type: ignore[misc]
    """Callback handler backed by :class:`RunTracker`.

    Maps callback ``run_id`` / ``parent_run_id`` values to tracker run IDs so
    spans nest correctly.
    """

    def __init__(self) -> None:
        if not _HAS_LANGCHAIN:
            raise ImportError(
                "langchain-core is required for EtraceLangChainHandler. Install it with: pip install langchain-core"
            )
        self._tracker = RunTracker()
        self._last_llm_run_id: str | None = None

    # ── LLM callbacks ────────────────────────────────────────────────────

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        model_name = (metadata or {}).get("ls_model_name", "")
        provider = (metadata or {}).get("ls_provider", "")
        input_data = _serialize_messages(messages[0]) if messages else None

        self._tracker.on_run_start(
            name=f"{provider}.chat" if provider else "chat_model",
            run_id=str(run_id),
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            kind="llm",
            input=input_data,
            model=model_name,
            provider=provider,
            attributes={
                "etrace.kind": "llm",
                "gen_ai.system": provider,
                "gen_ai.request.model": model_name,
            },
        )
        self._last_llm_run_id = str(run_id)

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        model_name = (metadata or {}).get("ls_model_name", "")
        provider = (metadata or {}).get("ls_provider", "")

        self._tracker.on_run_start(
            name=f"{provider}.chat" if provider else "llm",
            run_id=str(run_id),
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            kind="llm",
            input=prompts[0] if prompts else None,
            model=model_name,
            provider=provider,
            attributes={
                "etrace.kind": "llm",
                "gen_ai.system": provider,
                "gen_ai.request.model": model_name,
            },
        )
        self._last_llm_run_id = str(run_id)

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        pending = self._tracker._spans.get(str(run_id))
        if not pending:
            return

        usage: dict[str, int] = {}
        output: Any = None
        extra_attrs: dict[str, Any] = {}

        gens = response.generations[0][0] if response.generations else None
        if gens:
            msg = getattr(gens, "message", None)
            if msg:
                rm = getattr(msg, "response_metadata", {})
                tu = rm.get("token_usage", {})
                prompt = tu.get("prompt_tokens", 0) or 0
                completion = tu.get("completion_tokens", 0) or 0
                if prompt or completion:
                    usage = {
                        "prompt_tokens": prompt,
                        "completion_tokens": completion,
                        "total_tokens": tu.get("total_tokens", prompt + completion),
                    }

                content = getattr(msg, "content", None)
                if content:
                    output = content
                    extra_attrs["gen_ai.output"] = str(content)[:100_000]
                else:
                    tool_calls = getattr(msg, "tool_calls", None)
                    if tool_calls:
                        tc_data = [
                            {
                                "name": tc.get("name", ""),
                                "arguments": tc.get("args", {}),
                            }
                            for tc in tool_calls
                        ]
                        output = json.dumps(tc_data)
                        extra_attrs["gen_ai.output"] = output

                resp_model = rm.get("model_name", "")
                if resp_model:
                    extra_attrs["gen_ai.response.model"] = resp_model

        self._tracker.on_run_end(
            str(run_id),
            output=output,
            usage=usage or None,
            model=extra_attrs.get("gen_ai.response.model"),
            attributes=extra_attrs or None,
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._tracker.on_run_error(str(run_id), error)

    # ── Tool callbacks ────────────────────────────────────────────────────

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "tool")

        # In LangGraph, the tools node is a sibling of the model node,
        # so parent_run_id points to "tools" chain, not the LLM.
        # We track the last LLM run_id so tools become children of
        # the LLM that triggered them.
        effective_parent = self._last_llm_run_id or parent_run_id

        self._tracker.on_run_start(
            name=tool_name,
            run_id=str(run_id),
            parent_run_id=str(effective_parent) if effective_parent else None,
            kind="tool",
            input=inputs or input_str,
            attributes={"etrace.kind": "tool"},
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._tracker.on_run_end(str(run_id), output=output)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._tracker.on_run_error(str(run_id), error)

    # ── Chain callbacks ───────────────────────────────────────────────────

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        # Record the run_id so children can resolve their parent, but
        # do NOT create an etrace span.  LangGraph chain nodes are
        # internal plumbing (middleware, routing) that add noise.
        self._tracker._spans[str(run_id)] = _Run(
            span=None,
            start=0.0,
            parent_run_id=str(parent_run_id) if parent_run_id else None,
        )

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        # Noop — chain runs are not traced, only used for parent lookup.
        pass

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        pass

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def flush(self) -> None:
        """Close any remaining open runs."""
        self._tracker.flush()
