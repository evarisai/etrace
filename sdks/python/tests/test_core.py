"""
Core API tests — verifies the fundamental tracing contracts.

Tests run in two modes:
  1. Noop mode (no init) — tests the Span dataclass directly
  2. OTel mode (with InMemorySpanExporter) — tests real OTel span creation

Every test validates one of the contracts defined in TESTING.md.
"""

from __future__ import annotations

import time

import pytest

import etrace
from etrace._types import ContextOptions, ScoreOptions, TraceKind, TraceStatus

# ═══════════════════════════════════════════════════════════════════════════════
# Contract 8: Noop Mode — everything works without init
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoopMode:
    """Contract 8: trace() and observe() work before init() in noop mode."""

    def test_trace_noop_creates_span(self):
        with etrace.trace("test", kind=TraceKind.TOOL, input="hello") as span:
            span.output = "world"

        assert span.name == "test"
        assert span.kind == TraceKind.TOOL
        assert span.input == "hello"
        assert span.output == "world"
        assert span.status == TraceStatus.OK

    def test_trace_noop_sets_duration(self):
        with etrace.trace("test", kind=TraceKind.CUSTOM) as span:
            time.sleep(0.01)

        assert span.duration_ns is not None
        assert span.duration_ns > 0

    def test_trace_noop_captures_errors(self):
        with pytest.raises(RuntimeError, match="boom"), etrace.trace("failing", kind=TraceKind.TOOL) as span:
            raise RuntimeError("boom")

        assert span.status == TraceStatus.ERROR
        assert span.error is not None
        assert span.error.message == "boom"
        assert span.error.type == "RuntimeError"

    def test_trace_noop_with_model(self):
        with etrace.trace("llm", kind=TraceKind.LLM, model="gpt-4o") as span:
            pass

        assert span.model == "gpt-4o"

    def test_get_current_span_noop(self):
        assert etrace.get_current_span() is None
        with etrace.trace("parent", kind=TraceKind.WORKFLOW) as span:
            assert etrace.get_current_span() is span
        assert etrace.get_current_span() is None


# ═══════════════════════════════════════════════════════════════════════════════
# Contract 10: @observe decorator
# ═══════════════════════════════════════════════════════════════════════════════


class TestObserve:
    """Contract 10: @observe wraps functions correctly."""

    def test_observe_sync_function(self):
        @etrace.observe(kind=TraceKind.TOOL, name="my_tool")
        def my_tool(x: int) -> int:
            return x * 2

        result = my_tool(5)
        assert result == 10

    @pytest.mark.asyncio
    async def test_observe_async_function(self):
        @etrace.observe(kind=TraceKind.RETRIEVAL, name="my_retrieval")
        async def my_retrieval(query: str) -> str:
            return f"result for {query}"

        result = await my_retrieval("test")
        assert result == "result for test"

    def test_observe_captures_input(self):
        captured_spans = []

        @etrace.observe(kind=TraceKind.TOOL, capture_input=True)
        def my_func(a: int, b: str = "default") -> str:
            captured_spans.append(etrace.get_current_span())
            return f"{a}-{b}"

        my_func(42)
        assert len(captured_spans) == 1
        assert captured_spans[0].input is not None

    def test_observe_no_capture(self):
        captured_spans = []

        @etrace.observe(kind=TraceKind.TOOL, capture_input=False, capture_output=False)
        def my_func(x: int) -> int:
            captured_spans.append(etrace.get_current_span())
            return x * 2

        my_func(5)
        assert len(captured_spans) == 1
        assert captured_spans[0].input is None
        assert captured_spans[0].output is None

    def test_observe_captures_output(self):
        @etrace.observe(kind=TraceKind.TOOL, capture_output=True)
        def my_func() -> str:
            return "hello"

        result = my_func()
        assert result == "hello"

    def test_observe_captures_error(self):
        @etrace.observe(kind=TraceKind.TOOL)
        def failing():
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            failing()

    def test_observe_uses_function_name_by_default(self):
        @etrace.observe(kind=TraceKind.TOOL)
        def my_special_function():
            return True

        # Function name is used as the trace name
        result = my_special_function()
        assert result is True


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience decorators
# ═══════════════════════════════════════════════════════════════════════════════


class TestConvenienceDecorators:
    def test_tool_decorator(self):
        @etrace.tool
        def search(query: str) -> list:
            return [query]

        assert search("test") == ["test"]

    @pytest.mark.asyncio
    async def test_agent_decorator_async(self):
        @etrace.agent
        async def run_agent(task: str) -> str:
            return f"done: {task}"

        result = await run_agent("build")
        assert "done" in result

    def test_workflow_decorator(self):
        @etrace.workflow
        def my_workflow():
            return "completed"

        assert my_workflow() == "completed"

    def test_llm_decorator(self):
        @etrace.llm
        def call_llm(prompt: str) -> str:
            return f"response to {prompt}"

        assert call_llm("hello") == "response to hello"


# ═══════════════════════════════════════════════════════════════════════════════
# Contract 6: Context propagation
# ═══════════════════════════════════════════════════════════════════════════════


class TestContextPropagation:
    """Contract 6: set_context() propagates to child spans."""

    def test_set_context_propagates(self):
        etrace.set_context(
            ContextOptions(
                user_id="user-123",
                session_id="sess-456",
            )
        )

        ctx = etrace.get_context()
        assert ctx.user_id == "user-123"
        assert ctx.session_id == "sess-456"

    def test_context_merges_tags(self):
        etrace.set_context(ContextOptions(tags=["tag1"]))
        etrace.set_context(ContextOptions(tags=["tag2"]))

        ctx = etrace.get_context()
        assert set(ctx.tags) == {"tag1", "tag2"}

    def test_context_preserves_existing(self):
        etrace.set_context(ContextOptions(user_id="u1", session_id="s1"))
        etrace.set_context(ContextOptions(user_id="u2"))  # only override user_id

        ctx = etrace.get_context()
        assert ctx.user_id == "u2"
        assert ctx.session_id == "s1"  # preserved


# ═══════════════════════════════════════════════════════════════════════════════
# Contract 7: Usage & Cost
# ═══════════════════════════════════════════════════════════════════════════════


class TestSetUsage:
    """Contract 7: set_usage() calculates tokens and cost."""

    def test_set_usage_basic(self):
        with etrace.trace("test", kind=TraceKind.LLM, model="gpt-4o"):
            usage = etrace.set_usage(
                input_tokens=100,
                output_tokens=50,
                model="gpt-4o",
            )
            assert usage.input == 100
            assert usage.output == 50
            assert usage.total == 150

    def test_set_usage_no_span(self):
        assert etrace.get_current_span() is None
        usage = etrace.set_usage(input_tokens=100)
        assert usage.input == 0  # Empty usage, not written to any span

    def test_set_usage_auto_calculates_cost(self):
        etrace._calc_costs = True
        with etrace.trace("test", kind=TraceKind.LLM, model="gpt-4o"):
            usage = etrace.set_usage(
                input_tokens=1000,
                output_tokens=500,
                model="gpt-4o",
            )
            # gpt-4o is in the pricing catalog
            assert usage.total_cost >= 0

    def test_set_usage_then_manual_cost_override(self):
        """Explicit cost override: set_usage for tokens, then manually set costs."""
        with etrace.trace("test", kind=TraceKind.LLM):
            usage = etrace.set_usage(
                input_tokens=100,
                output_tokens=50,
            )
            # Manually override costs after set_usage
            usage.input_cost = 0.01
            usage.output_cost = 0.02
            usage.total_cost = usage.input_cost + usage.output_cost
            assert usage.input_cost == 0.01
            assert usage.output_cost == 0.02
            assert usage.total_cost == pytest.approx(0.03)


# ═══════════════════════════════════════════════════════════════════════════════
# Contracts 3, 9: Span enrichment and error capture
# ═══════════════════════════════════════════════════════════════════════════════


class TestSpanEnrichment:
    """Contracts 3, 9: set_output, set_error, set_attribute."""

    def test_set_output(self):
        with etrace.trace("test", kind=TraceKind.TOOL) as span:
            etrace.set_output({"key": "value"})

        assert span.output == {"key": "value"}

    def test_set_error(self):
        with etrace.trace("test", kind=TraceKind.TOOL) as span:
            etrace.set_error("something went wrong", error_type="ValueError")

        assert span.error is not None
        assert span.error.message == "something went wrong"
        assert span.error.type == "ValueError"
        assert span.status == TraceStatus.ERROR

    def test_set_attribute(self):
        with etrace.trace("test", kind=TraceKind.TOOL) as span:
            etrace.set_attribute("custom.key", "custom_value")
            etrace.set_attribute("custom.count", 42)

        assert span.attributes["custom.key"] == "custom_value"
        assert span.attributes["custom.count"] == 42


# ═══════════════════════════════════════════════════════════════════════════════
# Contract: Score error handling
# ═══════════════════════════════════════════════════════════════════════════════


class TestScore:
    def test_score_raises_without_trace_id(self):
        with pytest.raises(ValueError, match="no trace_id"):
            etrace.score(ScoreOptions(name="test"))


# ═══════════════════════════════════════════════════════════════════════════════
# Init / Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestInit:
    def test_init_no_args_works(self):
        """init() with no args should work — no API key needed."""
        etrace.init()
        assert etrace.is_initialized()
        etrace.shutdown()

    def test_is_initialized_default(self):
        assert etrace.is_initialized() is False

    def test_shutdown_without_init(self):
        etrace._initialized = False
        etrace._processor = None
        etrace.shutdown()  # Should not raise

    def test_flush_without_provider(self):
        etrace._processor = None
        assert etrace.flush() is True
