"""
Langfuse-style compatibility tests.

Verifies that etrace supports the same patterns as Langfuse's
nested decorator, context propagation, and multi-span trace patterns.
"""

from __future__ import annotations

import asyncio

import pytest

import etrace
from etrace._types import ContextOptions, TraceKind, TraceStatus
from tests.compat.conftest import assert_parent_child, get_span_by_name


class TestLangfuseNestedDecorators:
    def test_three_level_nesting(self, evaris_client, span_exporter):
        @etrace.observe(kind=TraceKind.TOOL, name="level_3")
        def level_3():
            return "deepest"

        @etrace.observe(kind=TraceKind.AGENT, name="level_2")
        def level_2():
            return level_3()

        @etrace.observe(kind=TraceKind.WORKFLOW, name="level_1")
        def level_1():
            return level_2()

        level_1()
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 3
        # All share trace_id
        trace_ids = {s.trace_id for s in spans}
        assert len(trace_ids) == 1

    def test_decorator_output_capture(self, evaris_client, span_exporter):
        @etrace.observe(kind=TraceKind.TOOL, name="my_func", capture_output=True)
        def my_func():
            return "hello"

        my_func()
        span = get_span_by_name(span_exporter.get_finished_spans(), "my_func")
        assert span.output == "hello"


class TestLangfuseContextPropagation:
    def test_context_propagates_to_all_children(self, evaris_client, span_exporter):
        etrace.set_context(ContextOptions(user_id="user-abc", session_id="session-xyz"))

        @etrace.observe(kind=TraceKind.TOOL, name="child_a")
        def child_a():
            return "a"

        @etrace.observe(kind=TraceKind.TOOL, name="child_b")
        def child_b():
            return "b"

        @etrace.observe(kind=TraceKind.WORKFLOW, name="parent")
        def parent():
            child_a()
            child_b()

        parent()
        spans = span_exporter.get_finished_spans()
        for span in spans:
            assert span.user_id == "user-abc", f"Span {span.name!r} missing user_id"
            assert span.session_id == "session-xyz", f"Span {span.name!r} missing session_id"


class TestLangfuseSpanStatus:
    def test_error_in_child_sets_error_status(self, evaris_client, span_exporter):
        @etrace.observe(kind=TraceKind.TOOL, name="failing_tool")
        def failing_tool():
            raise ValueError("tool error")

        @etrace.observe(kind=TraceKind.WORKFLOW, name="workflow")
        def workflow():
            with pytest.raises(ValueError):
                failing_tool()
            return "recovered"

        workflow()
        spans = span_exporter.get_finished_spans()
        tool_span = get_span_by_name(spans, "failing_tool")
        assert tool_span.status == TraceStatus.ERROR
        # Workflow recovered, so it's OK
        wf_span = get_span_by_name(spans, "workflow")
        assert wf_span.status == TraceStatus.OK


class TestLangfuseMultiSpanTrace:
    def test_multiple_children_share_trace(self, evaris_client, span_exporter):
        @etrace.observe(kind=TraceKind.TOOL, name="tool_a")
        def tool_a():
            return "a"

        @etrace.observe(kind=TraceKind.TOOL, name="tool_b")
        def tool_b():
            return "b"

        @etrace.observe(kind=TraceKind.WORKFLOW, name="orchestrator")
        def orchestrator():
            a = tool_a()
            b = tool_b()
            return a + b

        result = orchestrator()
        assert result == "ab"
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 3
        # All share trace_id
        trace_ids = {s.trace_id for s in spans}
        assert len(trace_ids) == 1
        # Both tools are children of orchestrator
        orch = get_span_by_name(spans, "orchestrator")
        tool_a_span = get_span_by_name(spans, "tool_a")
        tool_b_span = get_span_by_name(spans, "tool_b")
        assert_parent_child(orch, tool_a_span)
        assert_parent_child(orch, tool_b_span)


class TestLangfuseAsync:
    def test_async_workflow(self, evaris_client, span_exporter):
        @etrace.observe(kind=TraceKind.TOOL, name="async_tool")
        async def async_tool():
            return "done"

        @etrace.observe(kind=TraceKind.WORKFLOW, name="async_workflow")
        async def async_workflow():
            return await async_tool()

        asyncio.get_event_loop().run_until_complete(async_workflow())
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 2
        tool = get_span_by_name(spans, "async_tool")
        wf = get_span_by_name(spans, "async_workflow")
        assert_parent_child(wf, tool)
