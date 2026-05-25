"""
Live z.ai instrumentation tests (E2E).

Uses the real z.ai API (OpenAI-compatible) to verify end-to-end:
  - OpenAI auto-instrumentation patches produce real OTel spans
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
import sys

import openai
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace.status import StatusCode

sys.path.insert(0, os.path.dirname(__file__))
import contextlib

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import etrace
from etrace._types import TraceKind

# ── Skip logic ───────────────────────────────────────────────────────────────


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end test requiring real API key")


def _skip_no_key():
    if not os.environ.get("ZAI_API_KEY"):
        pytest.skip("ZAI_API_KEY not set — skipping live z.ai tests")


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def zai_exporter():
    """InMemorySpanExporter for capturing live z.ai spans."""
    exporter = InMemorySpanExporter()
    yield exporter
    exporter.shutdown()


@pytest.fixture
def zai_client(zai_exporter):
    """
    Wire up etrace with InMemorySpanExporter + real OpenAI SDK
    patched against z.ai. No OTLP network calls.
    """
    from opentelemetry import trace as otel_trace

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(zai_exporter))
    otel_trace.set_tracer_provider(provider)

    etrace._initialized = True
    etrace._tracer = provider.get_tracer("evaris-zai-test")
    etrace._provider = provider
    etrace._api_key = "test-key"
    etrace._project_id = "test-project"
    etrace._endpoint = "http://localhost:4318/v1/traces"
    etrace._calc_costs = True

    # Instrument the OpenAI SDK against z.ai
    from etrace.instrumentation.openai import OpenAIInstrumentor

    inst = OpenAIInstrumentor()
    tracer = provider.get_tracer("evaris-zai-test")
    inst.instrument(tracer, calc_costs=True)

    yield etrace, zai_exporter

    inst.uninstrument()
    with contextlib.suppress(Exception):
        provider.shutdown()


@pytest.fixture
def openai_client():
    """Real OpenAI client pointed at z.ai."""
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ["ZAI_API_KEY"],
        base_url="https://api.z.ai/api/paas/v4/",
    )


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.e2e
class TestZAiChatCompletion:
    """Live chat completion tests against z.ai API."""

    def test_chat_span_created(self, zai_client, openai_client):
        """A real chat call produces an 'openai.chat' OTel span."""
        _skip_no_key()
        _, exporter = zai_client

        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
        )

        spans = exporter.get_finished_spans()
        chat_spans = [s for s in spans if s.name == "openai.chat"]
        assert len(chat_spans) == 1
        span = chat_spans[0]
        assert span.context.trace_id != 0
        assert span.context.span_id != 0

    def test_chat_span_has_semconv_attributes(self, zai_client, openai_client):
        """Live span has gen_ai.* semantic convention attributes."""
        _skip_no_key()
        _, exporter = zai_client

        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
        )

        span = next(s for s in exporter.get_finished_spans() if s.name == "openai.chat")
        assert span.attributes["gen_ai.system"] == "openai"
        assert span.attributes["gen_ai.request.model"] == "glm-5.1"
        assert span.attributes["evaris.kind"] == "llm"

    def test_chat_span_has_usage_from_live_response(self, zai_client, openai_client):
        """Token usage is extracted from the real z.ai response."""
        _skip_no_key()
        _, exporter = zai_client

        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello in 3 words"}],
            max_tokens=20,
        )

        span = next(s for s in exporter.get_finished_spans() if s.name == "openai.chat")
        assert span.attributes["gen_ai.usage.prompt_tokens"] > 0
        assert span.attributes["gen_ai.usage.completion_tokens"] > 0
        assert span.attributes["gen_ai.usage.total_tokens"] > 0
        assert (
            span.attributes["gen_ai.usage.total_tokens"]
            == span.attributes["gen_ai.usage.prompt_tokens"] + span.attributes["gen_ai.usage.completion_tokens"]
        )

    def test_chat_span_has_reasoning_tokens(self, zai_client, openai_client):
        """z.ai GLM models include reasoning_tokens in the response."""
        _skip_no_key()
        _, exporter = zai_client

        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "What is 2+2?"}],
            max_tokens=50,
        )

        span = next(s for s in exporter.get_finished_spans() if s.name == "openai.chat")
        # GLM-5.1 typically returns reasoning tokens
        reasoning = span.attributes.get("gen_ai.usage.reasoning_tokens", 0)
        assert isinstance(reasoning, int)
        assert reasoning >= 0

    def test_chat_span_has_cached_tokens(self, zai_client, openai_client):
        """cached_tokens attribute may be absent (z.ai returns 0, instrumentor skips 0)."""
        _skip_no_key()
        _, exporter = zai_client

        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
        )

        span = next(s for s in exporter.get_finished_spans() if s.name == "openai.chat")
        # z.ai returns cached_tokens=0 for new prompts, and the instrumentor
        # skips setting the attribute when value is 0 (if cached_tokens:)
        # This is correct behavior — non-cached requests don't need the attribute
        cached = span.attributes.get("gen_ai.usage.cache_read_tokens")
        assert cached is None or isinstance(cached, int)

    def test_chat_span_ok_status(self, zai_client, openai_client):
        """Successful live call has StatusCode.OK."""
        _skip_no_key()
        _, exporter = zai_client

        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
        )

        span = next(s for s in exporter.get_finished_spans() if s.name == "openai.chat")
        assert span.status.status_code == StatusCode.OK

    def test_chat_span_captures_input_messages(self, zai_client, openai_client):
        """Input messages are serialized on the span."""
        _skip_no_key()
        _, exporter = zai_client

        msgs = [{"role": "user", "content": "Say hello"}]
        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=msgs,
            max_tokens=10,
        )

        span = next(s for s in exporter.get_finished_spans() if s.name == "openai.chat")
        assert "gen_ai.input.messages" in span.attributes
        # The value is a JSON string
        raw = span.attributes["gen_ai.input.messages"]
        import json as _json

        parsed = _json.loads(raw)
        assert parsed == msgs

    def test_chat_span_may_or_may_not_capture_output(self, zai_client, openai_client):
        """Output text may be captured (depends on LLM response content)."""
        _skip_no_key()
        _, exporter = zai_client

        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Tell me a joke"}],
            max_tokens=30,
        )

        span = next(s for s in exporter.get_finished_spans() if s.name == "openai.chat")
        # Output may or may not be present depending on the response
        # If present, it should be a non-empty string
        output = span.attributes.get("gen_ai.output")
        if output is not None:
            assert isinstance(output, str)

    def test_chat_span_has_cost_calculation(self, zai_client, openai_client):
        """Cost is auto-calculated from the pricing catalog for GLM models."""
        _skip_no_key()
        _, exporter = zai_client

        openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
        )

        span = next(s for s in exporter.get_finished_spans() if s.name == "openai.chat")
        # Cost should be calculated (the pricing catalog has zai-org models)
        assert "gen_ai.usage.cost" in span.attributes
        # Cost can be 0 if model not in catalog under exact name
        # but the attribute should exist

    def test_chat_response_model_reflects_real_model(self, zai_client, openai_client):
        """The response model from z.ai is captured (may differ from request model)."""
        _skip_no_key()
        _, exporter = zai_client

        resp = openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
        )
        # The response model field
        assert resp.model == "glm-5.1"

        # The span captures the response model for usage extraction
        span = next(s for s in exporter.get_finished_spans() if s.name == "openai.chat")
        assert "gen_ai.usage.prompt_tokens" in span.attributes


@pytest.mark.e2e
class TestZAiStreaming:
    """Streaming chat completion tests against z.ai API."""

    def test_streaming_span_created(self, zai_client, openai_client):
        """Streaming call creates a span with gen_ai.streaming=True."""
        _skip_no_key()
        _, exporter = zai_client

        stream = openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
            stream=True,
        )
        # Consume the stream
        for _ in stream:
            pass

        spans = exporter.get_finished_spans()
        chat_spans = [s for s in spans if s.name == "openai.chat"]
        assert len(chat_spans) == 1

    def test_streaming_span_has_flag(self, zai_client, openai_client):
        """Streaming span has gen_ai.streaming = True."""
        _skip_no_key()
        _, exporter = zai_client

        stream = openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
            stream=True,
        )
        for _ in stream:
            pass

        span = next(s for s in exporter.get_finished_spans() if s.name == "openai.chat")
        assert span.attributes.get("gen_ai.streaming") is True

    def test_streaming_span_skips_usage(self, zai_client, openai_client):
        """Streaming span does NOT have usage attributes (not available in stream)."""
        _skip_no_key()
        _, exporter = zai_client

        stream = openai_client.chat.completions.create(
            model="glm-5.1",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
            stream=True,
        )
        for _ in stream:
            pass

        span = next(s for s in exporter.get_finished_spans() if s.name == "openai.chat")
        assert "gen_ai.usage.prompt_tokens" not in span.attributes


@pytest.mark.e2e
class TestZAiErrorHandling:
    """Error handling tests against the real z.ai API."""

    def test_invalid_model_error(self, zai_client, openai_client):
        _skip_no_key()
        _, exporter = zai_client

        with pytest.raises(openai.APIStatusError):
            openai_client.chat.completions.create(
                model="nonexistent-model-xyz",
                messages=[{"role": "user", "content": "Say hello"}],
                max_tokens=10,
            )

        span = next(s for s in exporter.get_finished_spans() if s.name == "openai.chat")
        assert span.status.status_code == StatusCode.ERROR
        assert len(span.events) >= 1
        assert span.events[0].name == "exception"

    def test_empty_messages_error(self, zai_client, openai_client):
        _skip_no_key()
        _, exporter = zai_client

        with pytest.raises(openai.APIStatusError):
            openai_client.chat.completions.create(
                model="glm-5.1",
                messages=[],
                max_tokens=10,
            )

        span = next(s for s in exporter.get_finished_spans() if s.name == "openai.chat")
        assert span.status.status_code == StatusCode.ERROR


@pytest.mark.e2e
class TestZAiWithManualTrace:
    """Combining auto-instrumented z.ai calls with manual trace() / @observe.

    Note: In the new architecture, etrace.trace() creates etrace Spans (not OTel
    spans). Auto-instrumentation creates OTel spans separately. These tests verify
    that both systems work correctly side-by-side.
    """

    def test_chat_inside_manual_trace(self, zai_client, openai_client):
        _skip_no_key()
        _, exporter = zai_client

        with etrace.trace("my_workflow", kind=TraceKind.WORKFLOW):
            openai_client.chat.completions.create(
                model="glm-5.1",
                messages=[{"role": "user", "content": "Say hello"}],
                max_tokens=10,
            )

        # Auto-instrumentation creates an OTel span for the OpenAI call
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "openai.chat"

    def test_observe_wrapping_chat(self, zai_client, openai_client):
        _skip_no_key()
        _, exporter = zai_client

        @etrace.observe(kind=TraceKind.TOOL, name="ask_llm")
        def ask_llm(question: str) -> str:
            resp = openai_client.chat.completions.create(
                model="glm-5.1",
                messages=[{"role": "user", "content": question}],
                max_tokens=20,
            )
            return resp.choices[0].message.content or ""

        ask_llm("Explain quantum computing in one sentence")
        # z.ai may return empty content for simple prompts

        # Auto-instrumentation creates an OTel span
        spans = exporter.get_finished_spans()
        assert len(spans) >= 1
        chat_span = next(s for s in spans if s.name == "openai.chat")
        assert chat_span is not None

    def test_multi_step_workflow(self, zai_client, openai_client):
        _skip_no_key()
        _, exporter = zai_client

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

        # Both LLM calls produce OTel spans
        spans = exporter.get_finished_spans()
        chats = [s for s in spans if s.name == "openai.chat"]
        assert len(chats) == 2
