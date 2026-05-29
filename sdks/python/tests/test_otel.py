"""
Tests that etrace produces correct spans via the processor → exporter pipeline.

Replaces the old test_otel.py which tested OTel span attributes directly.
The new architecture uses etrace's own Span model; OTel is just one export target.
"""

from __future__ import annotations

import asyncio

import pytest

import etrace
from etrace._exporter import InMemoryExporter
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
    etrace.init(exporters=[exporter])
    yield etrace
    etrace.shutdown()


# ── Span Identity ─────────────────────────────────────────────────────────────


class TestSpanIdentity:
    def test_trace_creates_span(self, client, exporter):
        with etrace.trace("my_span", kind=TraceKind.TOOL):
            pass
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "my_span"

    def test_span_has_trace_id(self, client, exporter):
        with etrace.trace("test") as span:
            assert len(span.trace_id) == 32
        s = exporter.get_finished_spans()[0]
        assert len(s.trace_id) == 32

    def test_span_has_start_and_end_time(self, client, exporter):
        with etrace.trace("timed"):
            pass
        s = exporter.get_finished_spans()[0]
        assert s.started_at is not None
        assert s.ended_at is not None
        assert s.duration_ns > 0


# ── Span Attributes ──────────────────────────────────────────────────────────


class TestSpanAttributes:
    def test_kind_attribute(self, client, exporter):
        with etrace.trace("test", kind=TraceKind.LLM):
            pass
        assert exporter.get_finished_spans()[0].kind == TraceKind.LLM

    def test_input_attribute(self, client, exporter):
        with etrace.trace("test", kind=TraceKind.TOOL, input="hello"):
            pass
        assert exporter.get_finished_spans()[0].input == "hello"

    def test_output_attribute(self, client, exporter):
        with etrace.trace("test", kind=TraceKind.TOOL) as span:
            span.output = "world"
        assert exporter.get_finished_spans()[0].output == "world"

    def test_model_attribute(self, client, exporter):
        with etrace.trace("test", kind=TraceKind.LLM, model="gpt-4o"):
            pass
        assert exporter.get_finished_spans()[0].model == "gpt-4o"

    def test_provider_attribute(self, client, exporter):
        with etrace.trace("test", kind=TraceKind.LLM, provider="openai"):
            pass
        assert exporter.get_finished_spans()[0].provider == "openai"

    def test_custom_attributes(self, client, exporter):
        with etrace.trace("test", kind=TraceKind.TOOL, attributes={"custom.key": "val"}):
            pass
        s = exporter.get_finished_spans()[0]
        assert s.attributes["custom.key"] == "val"

    def test_usage_attributes(self, client, exporter):
        with etrace.trace("test", kind=TraceKind.LLM, model="gpt-4o"):
            etrace.set_usage(input_tokens=100, output_tokens=50, model="gpt-4o")
        s = exporter.get_finished_spans()[0]
        assert s.usage is not None
        assert s.usage.input == 100
        assert s.usage.output == 50

    def test_error_attribute(self, client, exporter):
        with pytest.raises(ValueError), etrace.trace("test", kind=TraceKind.TOOL):
            raise ValueError("boom")
        s = exporter.get_finished_spans()[0]
        assert s.error is not None
        assert "boom" in s.error.message
        assert s.error.type == "ValueError"

    def test_tags_attribute(self, client, exporter):
        with etrace.trace("test", kind=TraceKind.TOOL, tags=["tag1", "tag2"]):
            pass
        assert exporter.get_finished_spans()[0].tags == ["tag1", "tag2"]


# ── Span Status ──────────────────────────────────────────────────────────────


class TestSpanStatus:
    def test_ok_status(self, client, exporter):
        with etrace.trace("test", kind=TraceKind.TOOL):
            pass
        assert exporter.get_finished_spans()[0].status == TraceStatus.OK

    def test_error_status_on_exception(self, client, exporter):
        with pytest.raises(RuntimeError), etrace.trace("test", kind=TraceKind.TOOL):
            raise RuntimeError("fail")
        assert exporter.get_finished_spans()[0].status == TraceStatus.ERROR

    def test_error_records_exception_event(self, client, exporter):
        with pytest.raises(TypeError), etrace.trace("test", kind=TraceKind.TOOL):
            raise TypeError("bad type")
        s = exporter.get_finished_spans()[0]
        assert s.error is not None
        assert s.error.type == "TypeError"

    def test_set_error_sets_status(self, client, exporter):
        with etrace.trace("test", kind=TraceKind.TOOL):
            etrace.set_error("manual error", error_type="RuntimeError")
        s = exporter.get_finished_spans()[0]
        assert s.status == TraceStatus.ERROR
        assert s.error.message == "manual error"


# ── Span Hierarchy ───────────────────────────────────────────────────────────


class TestSpanHierarchy:
    def test_nested_traces_share_trace_id(self, client, exporter):
        with (
            etrace.trace("parent", kind=TraceKind.WORKFLOW) as p,
            etrace.trace("child", kind=TraceKind.TOOL) as c,
        ):
            assert c.trace_id == p.trace_id
        spans = exporter.get_finished_spans()
        assert spans[0].trace_id == spans[1].trace_id

    def test_nested_traces_have_parent_child_link(self, client, exporter, assert_span_hierarchy):
        with etrace.trace("parent", kind=TraceKind.WORKFLOW), etrace.trace("child", kind=TraceKind.TOOL):
            pass
        assert_span_hierarchy("parent", "child")

    def test_unrelated_traces_have_different_trace_ids(self, client, exporter):
        with etrace.trace("first", kind=TraceKind.TOOL):
            pass
        with etrace.trace("second", kind=TraceKind.TOOL):
            pass
        spans = exporter.get_finished_spans()
        assert spans[0].trace_id != spans[1].trace_id

    def test_deeply_nested_hierarchy(self, client, exporter):
        with (
            etrace.trace("workflow", kind=TraceKind.WORKFLOW),
            etrace.trace("agent", kind=TraceKind.AGENT),
            etrace.trace("tool", kind=TraceKind.TOOL),
        ):
            pass
        spans = exporter.get_finished_spans()
        assert len(spans) == 3
        # All share trace_id
        trace_ids = {s.trace_id for s in spans}
        assert len(trace_ids) == 1
        # tool parent is agent, agent parent is workflow
        tool = next(s for s in spans if s.name == "tool")
        agent = next(s for s in spans if s.name == "agent")
        wf = next(s for s in spans if s.name == "workflow")
        assert tool.parent_span_id == agent.span_id
        assert agent.parent_span_id == wf.span_id
        assert wf.parent_span_id is None

    def test_observe_creates_hierarchical_spans(self, client, exporter):
        @etrace.observe(kind=TraceKind.TOOL, name="child_fn")
        def child():
            return 42

        @etrace.observe(kind=TraceKind.WORKFLOW, name="parent_fn")
        def parent():
            return child()

        parent()
        spans = exporter.get_finished_spans()
        assert len(spans) == 2
        c = next(s for s in spans if s.name == "child_fn")
        p = next(s for s in spans if s.name == "parent_fn")
        assert c.parent_span_id == p.span_id


# ── Context on Spans ─────────────────────────────────────────────────────────


class TestContextOnSpans:
    def test_user_id_on_span(self, client, exporter):
        etrace.set_context(ContextOptions(user_id="user-123"))
        with etrace.trace("test", kind=TraceKind.TOOL):
            pass
        assert exporter.get_finished_spans()[0].user_id == "user-123"

    def test_session_id_on_span(self, client, exporter):
        etrace.set_context(ContextOptions(session_id="sess-456"))
        with etrace.trace("test", kind=TraceKind.TOOL):
            pass
        assert exporter.get_finished_spans()[0].session_id == "sess-456"

    def test_conversation_id_on_span(self, client, exporter):
        etrace.set_context(ContextOptions(conversation_id="conv-789"))
        with etrace.trace("test", kind=TraceKind.TOOL):
            pass
        assert exporter.get_finished_spans()[0].conversation_id == "conv-789"

    def test_all_context_fields(self, client, exporter):
        etrace.set_context(
            ContextOptions(
                user_id="u1",
                session_id="s1",
                conversation_id="c1",
                tags=["production"],
            )
        )
        with etrace.trace("test", kind=TraceKind.TOOL):
            pass
        s = exporter.get_finished_spans()[0]
        assert s.user_id == "u1"
        assert s.session_id == "s1"
        assert s.conversation_id == "c1"


# ── Async ─────────────────────────────────────────────────────────────────────


class TestAsync:
    def test_async_observe_creates_span(self, client, exporter):
        @etrace.observe(kind=TraceKind.TOOL, name="async_tool")
        async def do_work():
            return "done"

        asyncio.run(do_work())
        assert len(exporter.get_finished_spans()) == 1
        assert exporter.get_finished_spans()[0].name == "async_tool"

    def test_async_nested_hierarchy(self, client, exporter):
        @etrace.observe(kind=TraceKind.TOOL, name="child_fn")
        async def child():
            return 42

        @etrace.observe(kind=TraceKind.WORKFLOW, name="parent_fn")
        async def parent():
            return await child()

        asyncio.run(parent())
        spans = exporter.get_finished_spans()
        assert len(spans) == 2
        c = next(s for s in spans if s.name == "child_fn")
        p = next(s for s in spans if s.name == "parent_fn")
        assert c.parent_span_id == p.span_id


# ── Edge Cases ────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_multiple_spans_in_sequence(self, client, exporter):
        for i in range(10):
            with etrace.trace(f"span_{i}", kind=TraceKind.TOOL):
                pass
        assert len(exporter.get_finished_spans()) == 10

    def test_span_with_large_input(self, client, exporter):
        large_input = "x" * 200_000
        with etrace.trace("test", kind=TraceKind.TOOL, input=large_input):
            pass
        assert exporter.get_finished_spans()[0].input == large_input

    def test_span_with_none_input(self, client, exporter):
        with etrace.trace("test", kind=TraceKind.TOOL, input=None):
            pass
        assert exporter.get_finished_spans()[0].input is None

    def test_span_with_dict_input(self, client, exporter):
        data = {"messages": [{"role": "user", "content": "hi"}]}
        with etrace.trace("test", kind=TraceKind.TOOL, input=data):
            pass
        assert exporter.get_finished_spans()[0].input == data
