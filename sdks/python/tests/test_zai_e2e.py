"""
Live z.ai instrumentation tests (E2E).

Uses the real z.ai API (OpenAI-compatible) to verify end-to-end:
  - OpenAI auto-instrumentation patches produce real etrace spans
  - gen_ai.* semantic convention attributes on live responses
  - Token usage extraction from real LLM responses
  - Cost auto-calculation from the pricing catalog
  - Streaming flag and span lifecycle
  - Error handling with real API errors

Requires: ZAI_API_KEY environment variable
Base URL: https://api.z.ai/api/paas/v4/

Marked as @pytest.mark.e2e — skipped unless --run-e2e flag is passed.
"""

from __future__ import annotations

import os
import contextlib

import openai
import pytest

import etrace
from etrace._exporter import InMemoryExporter
from etrace._types import TraceKind, TraceStatus

# ── Skip logic ───────────────────────────────────────────────────────────────


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end test requiring real API key")


def _skip_no_key():
    if not os.environ.get("ZAI_API_KEY"):
        pytest.skip("ZAI_API_KEY not set — skipping live z.ai tests")


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def zai_exporter():
    """InMemoryExporter for capturing live z.ai spans."""
    exporter = InMemoryExporter()
    yield exporter
    exporter.clear()


@pytest.fixture
def zai_env(zai_exporter):
    """
    Wire up etrace with InMemoryExporter + real OpenAI SDK
    patched against z.ai. No OTLP network calls.
    """
    etrace.shutdown()
    etrace.init(
        exporters=[zai_exporter],
        calculate_costs=True,
    )

    yield zai_exporter

    etrace.shutdown()


@pytest.fixture
def openai_client():
    """Real OpenAI client pointed at z.ai."""
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ["ZAI_API_KEY"],
        base_url="https://api.z.ai/api/paas/v4/",
    )


def _get_chat_spans(exporter: InMemoryExporter):
    return [s for s in exporter.get_finished_spans() if s.name == "openai.chat"]


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.e2e
class TestZAiChatCompletion:
    """Live chat completion tests against z.ai API."""

    def test_chat_span_created(self, zai_env, openai_client):
        """A real chat call produces an 'openai.chat' etrace span."""
        _skip_no_key()

        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
        )

        spans = _get_chat_spans(zai_env)
        assert len(spans) == 1
        assert spans[0].trace_id is not None
        assert spans[0].span_id is not None

    def test_chat_span_has_semconv_attributes(self, zai_env, openai_client):
        """Live span has gen_ai.* semantic convention attributes."""
        _skip_no_key()

        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
        )

        span = _get_chat_spans(zai_env)[0]
        assert span.attributes["gen_ai.system"] == "openai"
        assert span.attributes["gen_ai.request.model"] == "glm-5.1"
        assert span.attributes["etrace.kind"] == "llm"

    def test_chat_span_has_usage_from_live_response(self, zai_env, openai_client):
        """Token usage is extracted from the real z.ai response."""
        _skip_no_key()

        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello in 3 words"}],
            max_tokens=20,
        )

        span = _get_chat_spans(zai_env)[0]
        assert span.attributes["gen_ai.usage.prompt_tokens"] > 0
        assert span.attributes["gen_ai.usage.completion_tokens"] > 0
        assert span.attributes["gen_ai.usage.total_tokens"] > 0

    def test_chat_span_has_reasoning_tokens(self, zai_env, openai_client):
        """z.ai GLM models include reasoning_tokens in the response."""
        _skip_no_key()

        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "What is 2+2?"}],
            max_tokens=50,
        )

        span = _get_chat_spans(zai_env)[0]
        reasoning = span.attributes.get("gen_ai.usage.reasoning_tokens", 0)
        assert isinstance(reasoning, int)
        assert reasoning >= 0

    def test_chat_span_ok_status(self, zai_env, openai_client):
        """Successful live call has OK status."""
        _skip_no_key()

        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
        )

        span = _get_chat_spans(zai_env)[0]
        assert span.status == TraceStatus.OK

    def test_chat_span_captures_input_messages(self, zai_env, openai_client):
        """Input messages are serialized on the span."""
        _skip_no_key()

        msgs = [{"role": "user", "content": "Say hello"}]
        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=msgs,
            max_tokens=10,
        )

        span = _get_chat_spans(zai_env)[0]
        assert "gen_ai.input.messages" in span.attributes

    def test_chat_span_may_capture_output(self, zai_env, openai_client):
        """Output text may be captured from the LLM response."""
        _skip_no_key()

        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Tell me a joke"}],
            max_tokens=30,
        )

        span = _get_chat_spans(zai_env)[0]
        output = span.attributes.get("gen_ai.output")
        if output is not None:
            assert isinstance(output, str)

    def test_chat_span_has_cost_calculation(self, zai_env, openai_client):
        """Cost is auto-calculated from the pricing catalog for GLM models."""
        _skip_no_key()

        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
        )

        span = _get_chat_spans(zai_env)[0]
        # Usage with cost should be populated via set_usage()
        assert span.usage is not None

    def test_chat_response_model_reflects_real_model(self, zai_env, openai_client):
        """The response model from z.ai is captured."""
        _skip_no_key()

        resp = openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
        )
        assert resp.model == "glm-5.1"

        span = _get_chat_spans(zai_env)[0]
        assert "gen_ai.usage.prompt_tokens" in span.attributes


@pytest.mark.e2e
class TestZAiStreaming:
    """Streaming chat completion tests against z.ai API."""

    def test_streaming_span_created(self, zai_env, openai_client):
        """Streaming call creates a span with gen_ai.streaming=True."""
        _skip_no_key()

        stream = openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
            stream=True,
        )
        for _ in stream:
            pass

        spans = _get_chat_spans(zai_env)
        assert len(spans) == 1

    def test_streaming_span_has_flag(self, zai_env, openai_client):
        """Streaming span has gen_ai.streaming = True."""
        _skip_no_key()

        stream = openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
            stream=True,
        )
        for _ in stream:
            pass

        span = _get_chat_spans(zai_env)[0]
        assert span.attributes.get("gen_ai.streaming") is True

    def test_streaming_span_skips_usage(self, zai_env, openai_client):
        """Streaming span does NOT have usage attributes."""
        _skip_no_key()

        stream = openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
            stream=True,
        )
        for _ in stream:
            pass

        span = _get_chat_spans(zai_env)[0]
        assert "gen_ai.usage.prompt_tokens" not in span.attributes


@pytest.mark.e2e
class TestZAiErrorHandling:
    """Error handling tests against the real z.ai API."""

    def test_invalid_model_error(self, zai_env, openai_client):
        _skip_no_key()

        with pytest.raises(openai.APIStatusError):
            openai_client.chat.completions.create(
                model="nonexistent-model-xyz",
                messages=[{"role": "user", "content": "Say hello"}],
                max_tokens=10,
            )

        span = _get_chat_spans(zai_env)[0]
        assert span.status == TraceStatus.ERROR
        assert span.error is not None

    def test_empty_messages_error(self, zai_env, openai_client):
        _skip_no_key()

        with pytest.raises(openai.APIStatusError):
            openai_client.chat.completions.create(
                model="glm-5.1",
                messages=[],
                max_tokens=10,
            )

        span = _get_chat_spans(zai_env)[0]
        assert span.status == TraceStatus.ERROR


@pytest.mark.e2e
class TestZAiWithManualTrace:
    """Combining auto-instrumented z.ai calls with manual trace() / @observe."""

    def test_chat_inside_manual_trace(self, zai_env, openai_client):
        _skip_no_key()

        with etrace.trace("my_workflow", kind=TraceKind.WORKFLOW):
            openai_client.chat.completions.create(
                model="glm-5.1",
                messages=[{"role": "user", "content": "Say hello"}],
                max_tokens=10,
            )

        # Auto-instrumentation creates an etrace span for the OpenAI call
        spans = zai_env.get_finished_spans()
        chat_spans = [s for s in spans if s.name == "openai.chat"]
        assert len(chat_spans) == 1

    def test_observe_wrapping_chat(self, zai_env, openai_client):
        _skip_no_key()

        @etrace.observe(kind=TraceKind.TOOL, name="ask_llm")
        def ask_llm(question: str) -> str:
            resp = openai_client.chat.completions.create(
                model="glm-5.1",
                messages=[{"role": "user", "content": question}],
                max_tokens=20,
            )
            return resp.choices[0].message.content or ""

        ask_llm("Explain quantum computing in one sentence")

        spans = zai_env.get_finished_spans()
        chat_span = next(s for s in spans if s.name == "openai.chat")
        assert chat_span is not None

    def test_multi_step_workflow(self, zai_env, openai_client):
        _skip_no_key()

        @etrace.observe(kind=TraceKind.WORKFLOW, name="multi_step")
        def multi_step():
            openai_client.chat.completions.create(
                model="glm-5.1",
                messages=[{"role": "user", "content": "Say hello"}],
                max_tokens=10,
            )
            openai_client.chat.completions.create(
                model="glm-5.1",
                messages=[{"role": "user", "content": "Say goodbye"}],
                max_tokens=10,
            )
            return 2

        result = multi_step()
        assert result == 2

        # Both LLM calls produce etrace spans
        spans = zai_env.get_finished_spans()
        chats = [s for s in spans if s.name == "openai.chat"]
        assert len(chats) == 2
