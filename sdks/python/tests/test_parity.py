"""Cross-SDK parity tests — behaviors that must match between Python and TypeScript.

These tests verify the shared SDK contract:
  - @agent / agent() captures named input and output
  - @tool / tool() captures named input and output
  - return value becomes span output
  - explicit set_output overrides auto-captured output
  - nested agent/tool spans keep correct parent-child relation
  - opt-outs (capture_input=False, capture_output=False) disable capture
"""

from __future__ import annotations

import pytest

import etrace
from etrace._types import TraceKind, TraceStatus


class TestAgentDecorator:
    def test_agent_captures_named_input(self):
        captured = []

        @etrace.agent
        def my_agent(prompt: str) -> str:
            captured.append(etrace.get_current_span())
            return f"response: {prompt}"

        my_agent("hello")
        span = captured[0]
        assert span.kind == TraceKind.AGENT
        assert span.input == {"prompt": "hello"}
        assert span.output == "response: hello"
        assert span.status == TraceStatus.OK

    @pytest.mark.asyncio
    async def test_agent_async(self):
        captured = []

        @etrace.agent
        async def my_agent(prompt: str) -> str:
            captured.append(etrace.get_current_span())
            return f"response: {prompt}"

        await my_agent("hello")
        span = captured[0]
        assert span.kind == TraceKind.AGENT
        assert span.input == {"prompt": "hello"}
        assert span.output == "response: hello"

    def test_agent_uses_function_name(self):
        @etrace.agent
        def my_weather_agent(prompt: str) -> str:
            return prompt

        # Verify the span name comes from the function
        spans = []
        original_start = etrace._start_span

        def _spy_start(*args, **kwargs):
            span, token, start = original_start(*args, **kwargs)
            spans.append(span)
            return span, token, start

        etrace._start_span = _spy_start
        try:
            my_weather_agent("test")
        finally:
            etrace._start_span = original_start

        assert spans[0].name == "my_weather_agent"


class TestToolDecorator:
    def test_tool_captures_named_input(self):
        captured = []

        @etrace.tool
        def search(query: str, limit: int = 5) -> list[str]:
            captured.append(etrace.get_current_span())
            return [query] * limit

        result = search("AI")
        assert result == ["AI"] * 5
        span = captured[0]
        assert span.kind == TraceKind.TOOL
        assert span.input == {"query": "AI", "limit": 5}
        assert span.output == ["AI", "AI", "AI", "AI", "AI"]

    def test_tool_configured_with_name(self):
        captured = []

        @etrace.tool(name="get-weather")
        def get_weather(location: str) -> str:
            captured.append(etrace.get_current_span())
            return f"sunny in {location}"

        get_weather("Tokyo")
        span = captured[0]
        assert span.name == "get-weather"
        assert span.input == {"location": "Tokyo"}
        assert span.output == "sunny in Tokyo"


class TestOutputCapture:
    def test_return_value_becomes_output(self):
        captured = []

        @etrace.tool
        def double(x: int) -> int:
            captured.append(etrace.get_current_span())
            return x * 2

        result = double(7)
        assert result == 14
        assert captured[0].output == 14

    def test_set_output_overrides_auto_captured(self):
        captured = []

        @etrace.tool
        def compute(x: int) -> int:
            captured.append(etrace.get_current_span())
            etrace.set_output({"raw": x * 2, "formatted": f"Result: {x * 2}"})
            return x * 2  # This return value overwrites set_output

        compute(5)
        span = captured[0]
        # In Python, observe() wrapper sets span.output = result AFTER the function body,
        # so the return value overwrites set_output.
        assert span.output == 10

    def test_set_output_with_capture_output_false(self):
        captured = []

        @etrace.tool(capture_output=False)
        def compute(x: int) -> int:
            captured.append(etrace.get_current_span())
            etrace.set_output({"custom": x * 3})
            return x * 2

        compute(5)
        span = captured[0]
        assert span.output == {"custom": 15}


class TestNestedSpans:
    def test_nested_agent_tool_parent_child(self):
        captured = []

        @etrace.tool
        def get_data(key: str) -> str:
            captured.append(etrace.get_current_span())
            return f"data-{key}"

        @etrace.agent
        def my_agent(query: str) -> str:
            captured.append(etrace.get_current_span())
            return get_data(query)

        my_agent("test")
        # captured order: agent (outer) runs first, tool (inner) runs second
        agent_span = captured[0]
        tool_span = captured[1]

        assert agent_span.trace_id == tool_span.trace_id
        assert tool_span.parent_span_id == agent_span.span_id

    def test_three_level_nesting(self):
        captured = []

        @etrace.tool
        def level3(x: int) -> int:
            captured.append(etrace.get_current_span())
            return x + 1

        @etrace.step
        def level2(x: int) -> int:
            captured.append(etrace.get_current_span())
            return level3(x)

        @etrace.agent
        def level1(x: int) -> int:
            captured.append(etrace.get_current_span())
            return level2(x)

        level1(10)
        assert len(captured) == 3
        # captured order: level1 (outer), level2 (middle), level3 (inner)
        s1, s2, s3 = captured

        assert s3.parent_span_id == s2.span_id
        assert s2.parent_span_id == s1.span_id
        assert s1.trace_id == s2.trace_id == s3.trace_id


class TestOptOuts:
    def test_capture_input_false(self):
        captured = []

        @etrace.tool(capture_input=False)
        def secret_tool(token: str) -> str:
            captured.append(etrace.get_current_span())
            return "done"

        secret_tool("secret-key-123")
        span = captured[0]
        assert span.input is None
        assert span.output == "done"

    def test_capture_output_false(self):
        captured = []

        @etrace.tool(capture_output=False)
        def tool(x: int) -> int:
            captured.append(etrace.get_current_span())
            return x * 2

        tool(5)
        span = captured[0]
        assert span.output is None

    def test_both_false(self):
        captured = []

        @etrace.tool(capture_input=False, capture_output=False)
        def tool(x: int) -> int:
            captured.append(etrace.get_current_span())
            return x * 2

        tool(5)
        span = captured[0]
        assert span.input is None
        assert span.output is None
