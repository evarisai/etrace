"""
Traceloop-style compatibility tests.

Verifies that etrace supports the same patterns as Traceloop's
@workflow / @task decorator patterns using @observe.
"""

from __future__ import annotations

import asyncio

import pytest

import etrace
from etrace._types import TraceKind, TraceStatus
from tests.compat.conftest import assert_parent_child, get_span_by_name


class TestTraceloopWorkflowTaskPattern:
    def test_workflow_task_hierarchy(self, evaris_client, span_exporter):
        @etrace.observe(kind=TraceKind.TOOL, name="something_creator")
        def create():
            return "created"

        @etrace.observe(kind=TraceKind.WORKFLOW, name="joke_generator")
        def workflow():
            return create()

        workflow()
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 2
        task = get_span_by_name(spans, "something_creator")
        wf = get_span_by_name(spans, "joke_generator")
        assert task.kind == TraceKind.TOOL
        assert wf.kind == TraceKind.WORKFLOW
        assert_parent_child(wf, task)

    def test_async_workflow_task(self, evaris_client, span_exporter):
        @etrace.observe(kind=TraceKind.TOOL, name="creator")
        async def create():
            return "created"

        @etrace.observe(kind=TraceKind.WORKFLOW, name="async_workflow")
        async def workflow():
            return await create()

        asyncio.get_event_loop().run_until_complete(workflow())
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 2
        task = get_span_by_name(spans, "creator")
        wf = get_span_by_name(spans, "async_workflow")
        assert_parent_child(wf, task)


class TestTraceloopErrorHandling:
    def test_sync_workflow_error(self, evaris_client, span_exporter):
        @etrace.observe(kind=TraceKind.WORKFLOW, name="failing_workflow")
        def workflow():
            raise RuntimeError("Intentional failure")

        with pytest.raises(RuntimeError):
            workflow()
        span = get_span_by_name(span_exporter.get_finished_spans(), "failing_workflow")
        assert span.status == TraceStatus.ERROR
        assert "Intentional" in span.error.message

    def test_nested_error_propagation(self, evaris_client, span_exporter):
        @etrace.observe(kind=TraceKind.TOOL, name="failing_task")
        def task():
            raise ValueError("task error")

        @etrace.observe(kind=TraceKind.WORKFLOW, name="parent_workflow")
        def workflow():
            with pytest.raises(ValueError):
                task()
            return "recovered"

        workflow()
        spans = span_exporter.get_finished_spans()
        task_span = get_span_by_name(spans, "failing_task")
        assert task_span.status == TraceStatus.ERROR

    def test_async_workflow_error(self, evaris_client, span_exporter):
        @etrace.observe(kind=TraceKind.WORKFLOW, name="failing_async")
        async def workflow():
            raise RuntimeError("async failure")

        with pytest.raises(RuntimeError):
            asyncio.get_event_loop().run_until_complete(workflow())
        span = get_span_by_name(span_exporter.get_finished_spans(), "failing_async")
        assert span.status == TraceStatus.ERROR


class TestTraceloopUnrelatedEntities:
    def test_unrelated_spans_separate_traces(self, evaris_client, span_exporter):
        @etrace.observe(kind=TraceKind.WORKFLOW, name="workflow_1")
        def wf1():
            return "a"

        @etrace.observe(kind=TraceKind.TOOL, name="task_1")
        def t1():
            return "b"

        wf1()
        t1()
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 2
        # Unrelated spans should have different trace_ids
        assert spans[0].trace_id != spans[1].trace_id


class TestTraceloopInputOutputSerialization:
    def test_input_output_captured(self, evaris_client, span_exporter):
        @etrace.observe(kind=TraceKind.TOOL, name="processor", capture_input=True, capture_output=True)
        def process(data: str):
            return data.upper()

        process("hello")
        span = get_span_by_name(span_exporter.get_finished_spans(), "processor")
        assert span.input is not None
        assert span.output == "HELLO"

    def test_no_capture_mode(self, evaris_client, span_exporter):
        @etrace.observe(kind=TraceKind.TOOL, name="private_tool", capture_input=False, capture_output=False)
        def tool_fn(secret):
            return "done"

        tool_fn("sensitive")
        span = get_span_by_name(span_exporter.get_finished_spans(), "private_tool")
        assert span.input is None
        assert span.output is None
