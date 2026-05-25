"""Tests for the refactored etrace core — init(), trace(), @observe, set_*().

These tests verify the new pipeline-based architecture:
  - init() accepts exporters/processors, not api_key/project_id
  - trace() creates spans through the processor → exporter pipeline
  - No OTel dependency required for basic tracing
"""

from __future__ import annotations

import asyncio

import pytest

import etrace
from etrace._exporter import InMemoryExporter
from etrace._processor import BatchProcessor, SimpleProcessor
from etrace._types import ContextOptions, TraceKind, TraceStatus

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    if etrace.is_initialized():
        etrace.shutdown()


@pytest.fixture
def exporter():
    return InMemoryExporter()


@pytest.fixture
def client(exporter):
    """etrace initialized with InMemoryExporter."""
    etrace.init(exporters=[exporter])
    yield etrace
    etrace.shutdown()


# ── init() ────────────────────────────────────────────────────────────────────


class TestInit:
    def test_init_no_args(self):
        """init() with no args works — defaults to InMemoryExporter."""
        etrace.init()
        assert etrace.is_initialized()
        etrace.shutdown()

    def test_init_with_exporters(self, exporter):
        etrace.init(exporters=[exporter])
        assert etrace.is_initialized()
        etrace.shutdown()

    def test_init_with_processors(self, exporter):
        proc = SimpleProcessor(exporter)
        etrace.init(processors=[proc])
        assert etrace.is_initialized()
        etrace.shutdown()

    def test_init_idempotent(self):
        etrace.init()
        etrace.init()  # should not raise
        etrace.shutdown()

    def test_init_with_service_name(self, exporter):
        etrace.init(exporters=[exporter], service_name="my-service")
        assert etrace.is_initialized()
        etrace.shutdown()

    def test_init_with_calculate_costs_false(self, exporter):
        etrace.init(exporters=[exporter], calculate_costs=False)
        assert etrace.is_initialized()
        etrace.shutdown()

    def test_init_with_debug(self, exporter):
        etrace.init(exporters=[exporter], debug=True)
        etrace.shutdown()


# ── trace() ───────────────────────────────────────────────────────────────────


class TestTrace:
    def test_basic_trace(self, client, exporter):
        with etrace.trace("my_span", kind=TraceKind.TOOL):
            pass
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "my_span"
        assert spans[0].kind == TraceKind.TOOL
        assert spans[0].status == TraceStatus.OK

    def test_trace_sets_timing(self, client, exporter):
        with etrace.trace("timed"):
            pass
        s = exporter.get_finished_spans()[0]
        assert s.started_at is not None
        assert s.ended_at is not None
        assert s.duration_ns > 0

    def test_trace_with_input(self, client, exporter):
        with etrace.trace("in", kind=TraceKind.TOOL, input="hello"):
            pass
        assert exporter.get_finished_spans()[0].input == "hello"

    def test_trace_with_model(self, client, exporter):
        with etrace.trace("llm", kind=TraceKind.LLM, model="gpt-4o"):
            pass
        assert exporter.get_finished_spans()[0].model == "gpt-4o"

    def test_trace_with_provider(self, client, exporter):
        with etrace.trace("llm", kind=TraceKind.LLM, provider="openai"):
            pass
        assert exporter.get_finished_spans()[0].provider == "openai"

    def test_trace_with_attributes(self, client, exporter):
        with etrace.trace("attr", kind=TraceKind.TOOL, attributes={"key": "val"}):
            pass
        s = exporter.get_finished_spans()[0]
        assert s.attributes["key"] == "val"

    def test_trace_with_tags(self, client, exporter):
        with etrace.trace("tagged", kind=TraceKind.TOOL, tags=["a", "b"]):
            pass
        assert exporter.get_finished_spans()[0].tags == ["a", "b"]

    def test_trace_span_has_ids(self, client, exporter):
        with etrace.trace("ids") as span:
            assert span.trace_id
            assert span.span_id
        s = exporter.get_finished_spans()[0]
        assert len(s.trace_id) == 32
        assert len(s.span_id) == 16

    def test_trace_error_captures_exception(self, client, exporter):
        with pytest.raises(RuntimeError, match="boom"), etrace.trace("fail", kind=TraceKind.TOOL):
            raise RuntimeError("boom")
        s = exporter.get_finished_spans()[0]
        assert s.status == TraceStatus.ERROR
        assert s.error is not None
        assert "boom" in s.error.message

    def test_trace_sets_output_on_span(self, client, exporter):
        with etrace.trace("out") as span:
            span.output = {"result": 42}
        assert exporter.get_finished_spans()[0].output == {"result": 42}

    def test_nested_traces_share_trace_id(self, client, exporter):
        with etrace.trace("parent", kind=TraceKind.WORKFLOW) as p:
            with etrace.trace("child", kind=TraceKind.TOOL) as c:
                assert c.trace_id == p.trace_id
        spans = exporter.get_finished_spans()
        assert len(spans) == 2
        assert spans[0].trace_id == spans[1].trace_id

    def test_nested_trace_sets_parent(self, client, exporter):
        with etrace.trace("parent", kind=TraceKind.WORKFLOW) as p, etrace.trace("child", kind=TraceKind.TOOL):
            pass
        spans = exporter.get_finished_spans()
        child = next(s for s in spans if s.name == "child")
        assert child.parent_span_id == p.span_id

    def test_sequential_traces_have_different_trace_ids(self, client, exporter):
        with etrace.trace("first"):
            pass
        with etrace.trace("second"):
            pass
        spans = exporter.get_finished_spans()
        assert spans[0].trace_id != spans[1].trace_id


# ── trace() noop mode ────────────────────────────────────────────────────────


class TestTraceNoop:
    def test_trace_without_init_works(self):
        """trace() yields a lightweight span when not initialized."""
        with etrace.trace("noop", kind=TraceKind.TOOL) as span:
            assert span is not None
            assert span.name == "noop"
        # No exporter → no crash

    def test_observe_without_init_works(self):
        @etrace.observe(kind=TraceKind.TOOL)
        def my_func(x):
            return x * 2

        assert my_func(5) == 10

    def test_set_usage_without_init_no_crash(self):
        etrace.set_usage(input_tokens=100)

    def test_set_output_without_init_no_crash(self):
        etrace.set_output("hello")

    def test_set_error_without_init_no_crash(self):
        etrace.set_error("oops")


# ── @observe ──────────────────────────────────────────────────────────────────


class TestObserve:
    def test_sync_observe(self, client, exporter):
        @etrace.observe(kind=TraceKind.TOOL, name="my_tool")
        def add(a, b):
            return a + b

        assert add(1, 2) == 3
        assert len(exporter.get_finished_spans()) == 1
        assert exporter.get_finished_spans()[0].name == "my_tool"

    def test_async_observe(self, client, exporter):
        @etrace.observe(kind=TraceKind.TOOL, name="async_tool")
        async def fetch(url):
            return url

        result = asyncio.get_event_loop().run_until_complete(fetch("http://test"))
        assert result == "http://test"
        assert len(exporter.get_finished_spans()) == 1

    def test_observe_captures_input(self, client, exporter):
        @etrace.observe(kind=TraceKind.TOOL, capture_input=True)
        def greet(name):
            return f"hello {name}"

        greet("world")
        s = exporter.get_finished_spans()[0]
        assert s.input is not None

    def test_observe_captures_output(self, client, exporter):
        @etrace.observe(kind=TraceKind.TOOL, capture_output=True)
        def compute():
            return 42

        compute()
        assert exporter.get_finished_spans()[0].output == 42

    def test_observe_no_capture_output(self, client, exporter):
        @etrace.observe(kind=TraceKind.TOOL, capture_output=False)
        def compute():
            return 42

        compute()
        assert exporter.get_finished_spans()[0].output is None

    def test_observe_error_captured(self, client, exporter):
        @etrace.observe(kind=TraceKind.TOOL)
        def boom():
            raise ValueError("kaboom")

        with pytest.raises(ValueError):
            boom()
        s = exporter.get_finished_spans()[0]
        assert s.status == TraceStatus.ERROR
        assert s.error is not None


# ── Convenience decorators ────────────────────────────────────────────────────


class TestConvenienceDecorators:
    @pytest.mark.parametrize(
        "decorator,kind",
        [
            (etrace.tool, TraceKind.TOOL),
            (etrace.agent, TraceKind.AGENT),
            (etrace.workflow, TraceKind.WORKFLOW),
            (etrace.llm, TraceKind.LLM),
            (etrace.retrieval, TraceKind.RETRIEVAL),
            (etrace.embedding, TraceKind.EMBEDDING),
        ],
    )
    def test_decorator_sets_kind(self, client, exporter, decorator, kind):
        @decorator
        def my_fn():
            return 1

        my_fn()
        assert exporter.get_finished_spans()[0].kind == kind


# ── set_usage() ───────────────────────────────────────────────────────────────


class TestSetUsage:
    def test_set_usage_on_current_span(self, client, exporter):
        with etrace.trace("llm", kind=TraceKind.LLM, model="gpt-4o"):
            usage = etrace.set_usage(input_tokens=100, output_tokens=50, model="gpt-4o")
        assert usage.input == 100
        assert usage.output == 50
        assert usage.total == 150
        s = exporter.get_finished_spans()[0]
        assert s.usage is not None
        assert s.usage.input == 100

    def test_set_usage_calculates_cost(self, client, exporter):
        etrace.init(exporters=[exporter], calculate_costs=True)
        with etrace.trace("llm", kind=TraceKind.LLM, model="gpt-4o"):
            usage = etrace.set_usage(input_tokens=1000, output_tokens=500, model="gpt-4o")
        assert usage.total_cost > 0
        etrace.shutdown()

    def test_set_usage_no_cost_when_disabled(self, exporter):
        etrace.init(exporters=[exporter], calculate_costs=False)
        with etrace.trace("llm", kind=TraceKind.LLM, model="gpt-4o"):
            usage = etrace.set_usage(input_tokens=1000, output_tokens=500, model="gpt-4o")
        assert usage.total_cost == 0
        etrace.shutdown()


# ── set_output(), set_error(), set_attribute() ────────────────────────────────


class TestSpanEnrichment:
    def test_set_output(self, client, exporter):
        with etrace.trace("test"):
            etrace.set_output({"key": "val"})
        assert exporter.get_finished_spans()[0].output == {"key": "val"}

    def test_set_error(self, client, exporter):
        with etrace.trace("test"):
            etrace.set_error("bad", error_type="ValueError")
        s = exporter.get_finished_spans()[0]
        assert s.status == TraceStatus.ERROR
        assert s.error.message == "bad"
        assert s.error.type == "ValueError"

    def test_set_attribute(self, client, exporter):
        with etrace.trace("test"):
            etrace.set_attribute("custom.key", "val")
            etrace.set_attribute("custom.count", 42)
        s = exporter.get_finished_spans()[0]
        assert s.attributes["custom.key"] == "val"
        assert s.attributes["custom.count"] == 42


# ── Context ───────────────────────────────────────────────────────────────────


class TestContext:
    def test_set_and_get_context(self):
        etrace.set_context(ContextOptions(user_id="u1", session_id="s1"))
        ctx = etrace.get_context()
        assert ctx.user_id == "u1"
        assert ctx.session_id == "s1"
        etrace._context_opts.set(None)  # cleanup

    def test_context_merges(self):
        etrace.set_context(ContextOptions(user_id="u1", tags=["a"]))
        etrace.set_context(ContextOptions(user_id="u2", tags=["b"]))
        ctx = etrace.get_context()
        assert ctx.user_id == "u2"
        assert set(ctx.tags) == {"a", "b"}
        etrace._context_opts.set(None)

    def test_context_propagates_to_span(self, client, exporter):
        etrace.set_context(ContextOptions(user_id="u1"))
        with etrace.trace("test"):
            pass
        s = exporter.get_finished_spans()[0]
        assert s.user_id == "u1"
        etrace._context_opts.set(None)

    def test_get_current_span(self, client, exporter):
        assert etrace.get_current_span() is None
        with etrace.trace("test") as span:
            assert etrace.get_current_span() is span
        assert etrace.get_current_span() is None


# ── flush / shutdown ──────────────────────────────────────────────────────────


class TestLifecycle:
    def test_flush_returns_true(self, client):
        assert etrace.flush() is True

    def test_flush_without_init(self):
        etrace.shutdown()  # ensure clean state
        assert etrace.flush() is True

    def test_shutdown_cleans_up(self, exporter):
        etrace.init(exporters=[exporter])
        assert etrace.is_initialized()
        etrace.shutdown()
        assert not etrace.is_initialized()

    def test_batch_processor_on_init(self, exporter):
        """init() with a BatchProcessor works."""
        proc = BatchProcessor(exporter, schedule_delay_ms=60000)
        etrace.init(processors=[proc])
        with etrace.trace("batched"):
            pass
        etrace.shutdown()  # forces flush
        assert len(exporter.get_finished_spans()) == 1
