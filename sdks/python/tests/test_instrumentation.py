"""
Auto-instrumentation tests.

Tests the OpenAI and Anthropic auto-instrumentation wrappers using
mocked SDK response objects. Verifies that patched calls:
  - Create correctly named etrace spans
  - Set gen_ai.* semantic convention attributes
  - Extract token usage from responses
  - Auto-calculate cost from the pricing catalog
  - Handle streaming (set gen_ai.streaming flag)
  - Propagate exceptions with ERROR status
  - Are reversible via uninstrument()

No real API keys or network calls needed — SDK response objects are mocked.
Uses etrace's InMemoryExporter (not OTel).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import etrace
from etrace._exporter import InMemoryExporter
from etrace._types import Span, TraceStatus
from etrace.instrumentation import (
    AnthropicInstrumentor,
    OpenAIInstrumentor,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_exporter():
    return InMemoryExporter()


# ── Mock response factories ──────────────────────────────────────────────────


def _openai_chat_response(
    model="gpt-4o",
    prompt_tokens=100,
    completion_tokens=50,
    total_tokens=150,
    cached_tokens=0,
    reasoning_tokens=0,
    content="Hello! How can I help?",
):
    """Build a mock openai.types.chat.ChatCompletion-like object."""
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        prompt_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
        completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning_tokens),
    )
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(model=model, usage=usage, choices=[choice])


def _openai_embedding_response(
    model="text-embedding-3-small",
    prompt_tokens=20,
    total_tokens=20,
):
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, total_tokens=total_tokens)
    return SimpleNamespace(model=model, usage=usage, data=[SimpleNamespace(embedding=[0.1, 0.2])])


def _anthropic_message_response(
    model="claude-sonnet-4-20250514",
    input_tokens=80,
    output_tokens=40,
    cache_read=0,
    cache_creation=0,
    text="Hi there!",
):
    usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_creation,
    )
    block = SimpleNamespace(text=text)
    return SimpleNamespace(model=model, usage=usage, content=[block])


# ── OpenAI Tests ─────────────────────────────────────────────────────────────


class TestOpenAIInstrumentation:
    """Tests for OpenAIInstrumentor patching and etrace span emission."""

    def _instrument(self, exporter: InMemoryExporter, calc_costs: bool = False):
        """Instrument mock OpenAI classes and return the instrumentor + mocks."""
        etrace.init(exporters=[exporter], auto_instrument={"llm": False})
        inst = OpenAIInstrumentor()

        mock_sync_chat = MagicMock(return_value=_openai_chat_response())
        mock_async_chat = MagicMock()
        mock_sync_emb = MagicMock(return_value=_openai_embedding_response())
        mock_async_emb = MagicMock()

        # Build mock module hierarchy
        chat_completions_mod = MagicMock()
        chat_completions_mod.Completions.create = mock_sync_chat
        chat_completions_mod.AsyncCompletions.create = mock_async_chat

        emb_mod = MagicMock()
        emb_mod.Embeddings.create = mock_sync_emb
        emb_mod.AsyncEmbeddings.create = mock_async_emb

        patches = patch.dict(
            "sys.modules",
            {
                "openai": MagicMock(),
                "openai.resources": MagicMock(),
                "openai.resources.chat": MagicMock(),
                "openai.resources.chat.completions": chat_completions_mod,
                "openai.resources.embeddings": emb_mod,
            },
        )
        patches.start()

        inst.instrument(calc_costs=calc_costs)

        return inst, mock_sync_chat, mock_sync_emb, patches

    def _cleanup(self, inst, patches):
        inst.uninstrument()
        patches.stop()
        etrace.shutdown()

    def _get_spans(self, exporter: InMemoryExporter) -> list[Span]:
        return exporter.get_finished_spans()

    def test_instrument_returns_true_on_success(self):
        inst = OpenAIInstrumentor()

        chat_mod = MagicMock()
        chat_mod.Completions.create = MagicMock()
        chat_mod.AsyncCompletions.create = MagicMock()
        emb_mod = MagicMock()
        emb_mod.Embeddings.create = MagicMock()
        emb_mod.AsyncEmbeddings.create = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "openai": MagicMock(),
                "openai.resources": MagicMock(),
                "openai.resources.chat": MagicMock(),
                "openai.resources.chat.completions": chat_mod,
                "openai.resources.embeddings": emb_mod,
            },
        ):
            result = inst.instrument()
            assert result is True
            inst.uninstrument()

    def test_uninstrument_restores_originals(self):
        exporter = _make_exporter()
        inst, mock_chat, _mock_emb, p = self._instrument(exporter)

        from openai.resources.chat.completions import Completions

        assert hasattr(Completions.create, "_etrace_original")

        self._cleanup(inst, p)
        assert Completions.create is mock_chat

    def test_chat_span_created(self):
        exporter = _make_exporter()
        inst, _mock_chat, _mock_emb, p = self._instrument(exporter)

        from openai.resources.chat.completions import Completions

        Completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

        spans = self._get_spans(exporter)
        assert len(spans) == 1
        assert spans[0].name == "openai.chat"
        self._cleanup(inst, p)

    def test_chat_span_has_semconv_attributes(self):
        exporter = _make_exporter()
        inst, _, _, p = self._instrument(exporter)

        from openai.resources.chat.completions import Completions

        Completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert span.attributes["gen_ai.system"] == "openai"
        assert span.attributes["gen_ai.request.model"] == "gpt-4o"
        assert span.attributes["etrace.kind"] == "llm"
        self._cleanup(inst, p)

    def test_chat_span_has_usage_tokens(self):
        exporter = _make_exporter()
        inst, mock_chat, _, p = self._instrument(exporter)

        from openai.resources.chat.completions import Completions

        mock_chat.return_value = _openai_chat_response(
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
        )
        Completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert span.attributes["gen_ai.usage.prompt_tokens"] == 200
        assert span.attributes["gen_ai.usage.completion_tokens"] == 100
        assert span.attributes["gen_ai.usage.total_tokens"] == 300
        self._cleanup(inst, p)

    def test_chat_span_has_cached_tokens(self):
        exporter = _make_exporter()
        inst, mock_chat, _, p = self._instrument(exporter)

        from openai.resources.chat.completions import Completions

        mock_chat.return_value = _openai_chat_response(cached_tokens=500)
        Completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert span.attributes["gen_ai.usage.cache_read_tokens"] == 500
        self._cleanup(inst, p)

    def test_chat_span_has_reasoning_tokens(self):
        exporter = _make_exporter()
        inst, mock_chat, _, p = self._instrument(exporter)

        from openai.resources.chat.completions import Completions

        mock_chat.return_value = _openai_chat_response(reasoning_tokens=1000)
        Completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert span.attributes["gen_ai.usage.reasoning_tokens"] == 1000
        self._cleanup(inst, p)

    def test_chat_span_captures_output(self):
        exporter = _make_exporter()
        inst, mock_chat, _, p = self._instrument(exporter)

        from openai.resources.chat.completions import Completions

        mock_chat.return_value = _openai_chat_response(content="Test response")
        Completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert span.attributes["gen_ai.output"] == "Test response"
        assert span.output == "Test response"
        self._cleanup(inst, p)

    def test_chat_span_captures_input_messages(self):
        exporter = _make_exporter()
        inst, _, _, p = self._instrument(exporter)

        from openai.resources.chat.completions import Completions

        msgs = [{"role": "user", "content": "hi"}]
        Completions.create(model="gpt-4o", messages=msgs)

        span = self._get_spans(exporter)[0]
        assert "gen_ai.input.messages" in span.attributes
        parsed = json.loads(span.attributes["gen_ai.input.messages"])
        assert parsed == msgs
        self._cleanup(inst, p)

    def test_chat_span_ok_status(self):
        exporter = _make_exporter()
        inst, _, _, p = self._instrument(exporter)

        from openai.resources.chat.completions import Completions

        Completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert span.status == TraceStatus.OK
        self._cleanup(inst, p)

    def test_chat_span_error_status_on_exception(self):
        exporter = _make_exporter()
        inst, mock_chat, _, p = self._instrument(exporter)

        from openai.resources.chat.completions import Completions

        mock_chat.side_effect = ValueError("bad_api_key")

        with pytest.raises(ValueError, match="bad_api_key"):
            Completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert span.status == TraceStatus.ERROR
        assert span.error is not None
        assert "bad_api_key" in span.error.message
        self._cleanup(inst, p)

    def test_chat_streaming_flag(self):
        exporter = _make_exporter()
        inst, _, _, p = self._instrument(exporter)

        from openai.resources.chat.completions import Completions

        Completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}], stream=True)

        span = self._get_spans(exporter)[0]
        assert span.attributes.get("gen_ai.streaming") is True
        assert "gen_ai.usage.prompt_tokens" not in span.attributes
        self._cleanup(inst, p)

    def test_chat_response_model_overrides_kwargs(self):
        exporter = _make_exporter()
        inst, mock_chat, _, p = self._instrument(exporter)

        from openai.resources.chat.completions import Completions

        mock_chat.return_value = _openai_chat_response(model="gpt-4o-2024-08-06")
        Completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert span.model == "gpt-4o-2024-08-06"
        assert "gen_ai.usage.prompt_tokens" in span.attributes
        self._cleanup(inst, p)

    def test_embedding_span_created(self):
        exporter = _make_exporter()
        inst, _, _mock_emb, p = self._instrument(exporter)

        from openai.resources.embeddings import Embeddings

        Embeddings.create(model="text-embedding-3-small", input="hello")

        spans = self._get_spans(exporter)
        assert len(spans) == 1
        assert spans[0].name == "openai.embeddings"
        self._cleanup(inst, p)

    def test_embedding_span_has_kind_embedding(self):
        exporter = _make_exporter()
        inst, _, _, p = self._instrument(exporter)

        from openai.resources.embeddings import Embeddings

        Embeddings.create(model="text-embedding-3-small", input="hello")

        span = self._get_spans(exporter)[0]
        assert span.attributes["etrace.kind"] == "embedding"
        assert span.attributes["gen_ai.system"] == "openai"
        assert span.attributes["gen_ai.request.model"] == "text-embedding-3-small"
        self._cleanup(inst, p)

    def test_embedding_span_has_usage(self):
        exporter = _make_exporter()
        mock_sync_emb = MagicMock(return_value=_openai_embedding_response(prompt_tokens=30, total_tokens=30))
        mock_sync_chat = MagicMock(return_value=_openai_chat_response())

        etrace.init(exporters=[exporter], auto_instrument={"llm": False})
        inst = OpenAIInstrumentor()

        chat_completions_mod = MagicMock()
        chat_completions_mod.Completions.create = mock_sync_chat
        chat_completions_mod.AsyncCompletions.create = MagicMock()
        emb_mod = MagicMock()
        emb_mod.Embeddings.create = mock_sync_emb
        emb_mod.AsyncEmbeddings.create = MagicMock()

        p = patch.dict(
            "sys.modules",
            {
                "openai": MagicMock(),
                "openai.resources": MagicMock(),
                "openai.resources.chat": MagicMock(),
                "openai.resources.chat.completions": chat_completions_mod,
                "openai.resources.embeddings": emb_mod,
            },
        )
        p.start()
        inst.instrument(calc_costs=False)

        from openai.resources.embeddings import Embeddings

        Embeddings.create(model="text-embedding-3-small", input="hello")

        span = self._get_spans(exporter)[0]
        assert span.attributes["gen_ai.usage.prompt_tokens"] == 30
        assert span.attributes["gen_ai.usage.completion_tokens"] == 0
        assert span.attributes["gen_ai.usage.total_tokens"] == 30
        inst.uninstrument()
        p.stop()
        etrace.shutdown()

    def test_chat_with_cost_calculation(self):
        """When calc_costs=True and model has pricing, cost attributes and usage are set."""
        exporter = _make_exporter()
        inst = OpenAIInstrumentor()

        mock_chat = MagicMock(
            return_value=_openai_chat_response(
                model="gpt-4o",
                prompt_tokens=100,
                completion_tokens=50,
            )
        )

        chat_mod = MagicMock()
        chat_mod.Completions.create = mock_chat
        chat_mod.AsyncCompletions.create = MagicMock()
        emb_mod = MagicMock()
        emb_mod.Embeddings.create = MagicMock()
        emb_mod.AsyncEmbeddings.create = MagicMock()

        etrace.init(exporters=[exporter], auto_instrument={"llm": False})

        p = patch.dict(
            "sys.modules",
            {
                "openai": MagicMock(),
                "openai.resources": MagicMock(),
                "openai.resources.chat": MagicMock(),
                "openai.resources.chat.completions": chat_mod,
                "openai.resources.embeddings": emb_mod,
            },
        )
        p.start()
        inst.instrument(calc_costs=True)

        from openai.resources.chat.completions import Completions

        Completions.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        # Usage should be populated via set_usage()
        assert span.usage is not None
        assert span.usage.total_cost > 0
        assert span.usage.input_cost > 0
        assert span.usage.output_cost > 0
        inst.uninstrument()
        p.stop()
        etrace.shutdown()


# ── Anthropic Tests ──────────────────────────────────────────────────────────


class TestAnthropicInstrumentation:
    """Tests for AnthropicInstrumentor patching and etrace span emission."""

    def _instrument(self, exporter: InMemoryExporter, calc_costs: bool = False):
        etrace.init(exporters=[exporter], auto_instrument={"llm": False})
        inst = AnthropicInstrumentor()

        mock_sync = MagicMock(return_value=_anthropic_message_response())
        mock_async = MagicMock()

        msg_mod = MagicMock()
        msg_mod.Messages.create = mock_sync
        msg_mod.AsyncMessages.create = mock_async

        patches = patch.dict(
            "sys.modules",
            {
                "anthropic": MagicMock(),
                "anthropic.resources": MagicMock(),
                "anthropic.resources.messages": msg_mod,
            },
        )
        patches.start()

        inst.instrument(calc_costs=calc_costs)

        return inst, mock_sync, patches

    def _cleanup(self, inst, patches):
        inst.uninstrument()
        patches.stop()
        etrace.shutdown()

    def _get_spans(self, exporter: InMemoryExporter) -> list[Span]:
        return exporter.get_finished_spans()

    def test_instrument_returns_true(self):
        exporter = _make_exporter()
        inst, _, p = self._instrument(exporter)
        assert len(inst._originals) > 0
        self._cleanup(inst, p)

    def test_messages_span_created(self):
        exporter = _make_exporter()
        inst, _, p = self._instrument(exporter)

        from anthropic.resources.messages import Messages

        Messages.create(model="claude-sonnet-4-20250514", messages=[{"role": "user", "content": "hi"}])

        spans = self._get_spans(exporter)
        assert len(spans) == 1
        assert spans[0].name == "anthropic.messages"
        self._cleanup(inst, p)

    def test_messages_span_has_semconv_attributes(self):
        exporter = _make_exporter()
        inst, _, p = self._instrument(exporter)

        from anthropic.resources.messages import Messages

        Messages.create(model="claude-sonnet-4-20250514", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert span.attributes["gen_ai.system"] == "anthropic"
        assert span.attributes["gen_ai.request.model"] == "claude-sonnet-4-20250514"
        assert span.attributes["etrace.kind"] == "llm"
        self._cleanup(inst, p)

    def test_messages_span_has_usage_tokens(self):
        exporter = _make_exporter()
        inst, mock_sync, p = self._instrument(exporter)

        from anthropic.resources.messages import Messages

        mock_sync.return_value = _anthropic_message_response(
            input_tokens=80,
            output_tokens=40,
        )
        Messages.create(model="claude-sonnet-4-20250514", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert span.attributes["gen_ai.usage.prompt_tokens"] == 80
        assert span.attributes["gen_ai.usage.completion_tokens"] == 40
        assert span.attributes["gen_ai.usage.total_tokens"] == 120
        self._cleanup(inst, p)

    def test_messages_span_has_cache_tokens(self):
        exporter = _make_exporter()
        inst, mock_sync, p = self._instrument(exporter)

        from anthropic.resources.messages import Messages

        mock_sync.return_value = _anthropic_message_response(cache_read=500, cache_creation=100)
        Messages.create(model="claude-sonnet-4-20250514", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert span.attributes["gen_ai.usage.cache_read_tokens"] == 500
        assert span.attributes["gen_ai.usage.cache_write_tokens"] == 100
        self._cleanup(inst, p)

    def test_messages_span_captures_output(self):
        exporter = _make_exporter()
        inst, mock_sync, p = self._instrument(exporter)

        from anthropic.resources.messages import Messages

        mock_sync.return_value = _anthropic_message_response(text="Test response from Claude")
        Messages.create(model="claude-sonnet-4-20250514", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert span.attributes["gen_ai.output"] == "Test response from Claude"
        assert span.output == "Test response from Claude"
        self._cleanup(inst, p)

    def test_messages_span_captures_input(self):
        exporter = _make_exporter()
        inst, _, p = self._instrument(exporter)

        from anthropic.resources.messages import Messages

        Messages.create(model="claude-sonnet-4-20250514", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert "gen_ai.input.messages" in span.attributes
        self._cleanup(inst, p)

    def test_messages_span_ok_status(self):
        exporter = _make_exporter()
        inst, _, p = self._instrument(exporter)

        from anthropic.resources.messages import Messages

        Messages.create(model="claude-sonnet-4-20250514", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert span.status == TraceStatus.OK
        self._cleanup(inst, p)

    def test_messages_span_error_on_exception(self):
        exporter = _make_exporter()
        inst, mock_sync, p = self._instrument(exporter)

        from anthropic.resources.messages import Messages

        mock_sync.side_effect = ConnectionError("timeout")

        with pytest.raises(ConnectionError, match="timeout"):
            Messages.create(model="claude-sonnet-4-20250514", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert span.status == TraceStatus.ERROR
        assert span.error is not None
        self._cleanup(inst, p)

    def test_messages_streaming_flag(self):
        exporter = _make_exporter()
        inst, _, p = self._instrument(exporter)

        from anthropic.resources.messages import Messages

        Messages.create(model="claude-sonnet-4-20250514", messages=[{"role": "user", "content": "hi"}], stream=True)

        span = self._get_spans(exporter)[0]
        assert span.attributes.get("gen_ai.streaming") is True
        assert "gen_ai.usage.prompt_tokens" not in span.attributes
        self._cleanup(inst, p)

    def test_messages_response_model_overrides(self):
        exporter = _make_exporter()
        inst, mock_sync, p = self._instrument(exporter)

        from anthropic.resources.messages import Messages

        mock_sync.return_value = _anthropic_message_response(model="claude-sonnet-4-20250514")
        Messages.create(model="claude-3.5-sonnet", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        # Response model is used for usage/cost, request model kept in attrs
        assert span.model == "claude-sonnet-4-20250514"
        self._cleanup(inst, p)

    def test_messages_with_cost_calculation(self):
        exporter = _make_exporter()
        inst, mock_sync, p = self._instrument(exporter, calc_costs=True)

        from anthropic.resources.messages import Messages

        mock_sync.return_value = _anthropic_message_response(
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
        )
        Messages.create(model="claude-sonnet-4-20250514", messages=[{"role": "user", "content": "hi"}])

        span = self._get_spans(exporter)[0]
        assert span.usage is not None
        assert span.usage.total_cost > 0
        self._cleanup(inst, p)

    def test_uninstrument_restores_originals(self):
        exporter = _make_exporter()
        inst, mock_sync, p = self._instrument(exporter)

        from anthropic.resources.messages import Messages

        patched = Messages.create
        assert hasattr(patched, "_etrace_original")

        self._cleanup(inst, p)
        assert Messages.create is mock_sync


# ── BaseInstrumentor Tests ───────────────────────────────────────────────────


class TestBaseInstrumentor:
    """Tests for BaseInstrumentor shared utilities."""

    def test_uninstrument_with_no_patches(self):
        inst = OpenAIInstrumentor()
        inst.uninstrument()  # Should not raise

    def test_patch_wraps_and_stores_original(self):
        inst = OpenAIInstrumentor()

        class FakeTarget:
            @staticmethod
            def method():
                return "original"

        original = FakeTarget.method
        inst._patch(FakeTarget, "method", lambda orig: lambda: "wrapped")

        assert FakeTarget.method() == "wrapped"
        assert inst._originals[0] == (FakeTarget, "method", original)

        inst.uninstrument()
        assert FakeTarget.method() == "original"
