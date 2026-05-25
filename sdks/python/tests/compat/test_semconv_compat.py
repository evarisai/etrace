"""
Semantic convention compatibility tests.

Verifies that etrace produces spans with fields that map correctly
to the gen_ai.* OTel semantic conventions when exported.
"""

from __future__ import annotations

import pytest

import etrace
from etrace._types import TraceKind, TraceStatus
from tests.compat.conftest import get_span_by_name


class TestGenAISemanticConventions:
    """Tests that etrace spans carry the right fields for gen_ai.* mapping."""

    def test_llm_span_has_provider(self, evaris_client, span_exporter):
        with etrace.trace("openai.chat", kind=TraceKind.LLM, provider="openai"):
            pass
        span = span_exporter.get_finished_spans()[0]
        assert span.provider == "openai"

    def test_llm_span_has_model(self, evaris_client, span_exporter):
        with etrace.trace("openai.chat", kind=TraceKind.LLM, model="gpt-4o"):
            pass
        span = span_exporter.get_finished_spans()[0]
        assert span.model == "gpt-4o"

    def test_usage_on_span(self, evaris_client, span_exporter):
        with etrace.trace("test", kind=TraceKind.LLM, model="gpt-4o"):
            etrace.set_usage(input_tokens=100, output_tokens=50, model="gpt-4o")
        span = span_exporter.get_finished_spans()[0]
        assert span.usage is not None
        assert span.usage.input == 100
        assert span.usage.output == 50
        assert span.usage.total == 150

    def test_llm_kind(self, evaris_client, span_exporter):
        with etrace.trace("test", kind=TraceKind.LLM):
            pass
        assert span_exporter.get_finished_spans()[0].kind == TraceKind.LLM

    def test_tool_kind(self, evaris_client, span_exporter):
        with etrace.trace("test", kind=TraceKind.TOOL):
            pass
        assert span_exporter.get_finished_spans()[0].kind == TraceKind.TOOL

    def test_workflow_kind(self, evaris_client, span_exporter):
        with etrace.trace("test", kind=TraceKind.WORKFLOW):
            pass
        assert span_exporter.get_finished_spans()[0].kind == TraceKind.WORKFLOW

    def test_all_trace_kinds(self, evaris_client, span_exporter):
        for kind in TraceKind:
            if kind == TraceKind.CUSTOM:
                continue
            with etrace.trace(f"test_{kind.value}", kind=kind):
                pass
        spans = span_exporter.get_finished_spans()
        assert len(spans) == len(TraceKind) - 1


class TestGenAIExceptionHandling:
    def test_exception_sets_error_status(self, evaris_client, span_exporter):
        with pytest.raises(ValueError), etrace.trace("openai.chat", kind=TraceKind.LLM, provider="openai"):
            raise ValueError("invalid_api_key")
        span = span_exporter.get_finished_spans()[0]
        assert span.status == TraceStatus.ERROR
        assert span.error is not None
        assert "invalid_api_key" in span.error.message

    def test_exception_has_type(self, evaris_client, span_exporter):
        with pytest.raises(TypeError), etrace.trace("test", kind=TraceKind.LLM):
            raise TypeError("bad type")
        span = span_exporter.get_finished_spans()[0]
        assert span.error.type == "TypeError"

    def test_success_has_no_error(self, evaris_client, span_exporter):
        with etrace.trace("test", kind=TraceKind.LLM, provider="openai"):
            pass
        span = span_exporter.get_finished_spans()[0]
        assert span.status == TraceStatus.OK
        assert span.error is None


class TestGenAISpanNaming:
    def test_openai_chat_span_name(self, evaris_client, span_exporter):
        with etrace.trace("openai.chat", kind=TraceKind.LLM, provider="openai"):
            pass
        spans = span_exporter.get_finished_spans()
        assert any(s.name == "openai.chat" for s in spans)

    def test_anthropic_messages_span_name(self, evaris_client, span_exporter):
        with etrace.trace("anthropic.messages", kind=TraceKind.LLM, provider="anthropic"):
            pass
        spans = span_exporter.get_finished_spans()
        assert any(s.name == "anthropic.messages" for s in spans)

    def test_openai_embeddings_span_name(self, evaris_client, span_exporter):
        with etrace.trace("openai.embeddings", kind=TraceKind.EMBEDDING, provider="openai"):
            pass
        spans = span_exporter.get_finished_spans()
        assert any(s.name == "openai.embeddings" for s in spans)


class TestGenAIUsageAttributes:
    def test_usage_prompt_tokens_exact(self, evaris_client, span_exporter):
        with etrace.trace("test", kind=TraceKind.LLM, model="gpt-4o"):
            etrace.set_usage(input_tokens=42, output_tokens=7, model="gpt-4o")
        span = span_exporter.get_finished_spans()[0]
        assert span.usage.input == 42
        assert span.usage.output == 7
        assert span.usage.total == 49

    def test_usage_zero_tokens(self, evaris_client, span_exporter):
        with etrace.trace("test", kind=TraceKind.LLM, model="gpt-4o"):
            etrace.set_usage(input_tokens=0, output_tokens=0, model="gpt-4o")
        span = span_exporter.get_finished_spans()[0]
        assert span.usage.input == 0
        assert span.usage.output == 0

    def test_usage_with_cached_tokens(self, evaris_client, span_exporter):
        with etrace.trace("test", kind=TraceKind.LLM, model="gpt-4o"):
            etrace.set_usage(
                input_tokens=100,
                output_tokens=50,
                model="gpt-4o",
                cached_tokens=500,
            )
        span = span_exporter.get_finished_spans()[0]
        assert span.usage.cached_tokens == 500

    def test_usage_with_reasoning_tokens(self, evaris_client, span_exporter):
        with etrace.trace("test", kind=TraceKind.LLM, model="gpt-4o"):
            etrace.set_usage(
                input_tokens=100,
                output_tokens=50,
                model="gpt-4o",
                reasoning_tokens=200,
            )
        span = span_exporter.get_finished_spans()[0]
        assert span.usage.reasoning_tokens == 200

    def test_usage_total_calculated_automatically(self, evaris_client, span_exporter):
        with etrace.trace("test", kind=TraceKind.LLM, model="gpt-4o"):
            usage = etrace.set_usage(input_tokens=100, output_tokens=50, model="gpt-4o")
        assert usage.total == 150


class TestSpanHierarchyCompliance:
    def test_nested_spans_share_trace_context(self, evaris_client, span_exporter):
        with etrace.trace("workflow", kind=TraceKind.WORKFLOW) as wf:
            with etrace.trace("task", kind=TraceKind.TOOL) as task:
                with etrace.trace("openai.chat", kind=TraceKind.LLM, provider="openai"):
                    pass
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 3
        # All share trace_id
        trace_ids = {s.trace_id for s in spans}
        assert len(trace_ids) == 1
        # Hierarchy
        chat = get_span_by_name(spans, "openai.chat")
        task = get_span_by_name(spans, "task")
        wf = get_span_by_name(spans, "workflow")
        assert chat.parent_span_id == task.span_id
        assert task.parent_span_id == wf.span_id
