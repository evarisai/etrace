"""Tests for set_usage() / calculate_usage_cost() separation of concerns.

set_usage()           — mutation: creates Usage, assigns to span.
                        When calculate_costs=True (default), auto-delegates to calculate_usage_cost().
calculate_usage_cost() — pure function: Usage + model → cost-populated Usage.
"""

from __future__ import annotations

import pytest

import etrace
from etrace import calculate_usage_cost
from etrace._exporter import InMemoryExporter
from etrace._types import TraceKind, Usage

# ── calculate_usage_cost() — pure function ────────────────────────────────────


class TestCalculateUsageCost:
    """Pure function: takes Usage + model, returns new Usage with costs. No span mutation."""

    def test_calculates_cost_for_known_model(self):
        usage = Usage(input=1000, output=500, total=1500)
        result = calculate_usage_cost(usage, model="gpt-4o")
        assert result.calculated_input_cost is not None
        assert result.calculated_input_cost > 0
        assert result.calculated_output_cost is not None
        assert result.calculated_output_cost > 0
        assert result.calculated_total_cost == pytest.approx(
            result.calculated_input_cost + result.calculated_output_cost
        )

    def test_populates_final_costs(self):
        usage = Usage(input=1000, output=500, total=1500)
        result = calculate_usage_cost(usage, model="gpt-4o")
        assert result.input_cost == result.calculated_input_cost
        assert result.output_cost == result.calculated_output_cost
        assert result.total_cost == pytest.approx(result.input_cost + result.output_cost)

    def test_unknown_model_returns_zero_costs(self):
        usage = Usage(input=100, output=50, total=150)
        result = calculate_usage_cost(usage, model="totally-unknown-model-xyz")
        assert result.input_cost == 0
        assert result.output_cost == 0
        assert result.total_cost == 0
        assert result.calculated_input_cost is None

    def test_does_not_mutate_input(self):
        """Must return a NEW Usage, not mutate the original."""
        usage = Usage(input=1000, output=500, total=1500)
        assert usage.input_cost == 0
        assert usage.calculated_input_cost is None

        result = calculate_usage_cost(usage, model="gpt-4o")

        # Original untouched
        assert usage.input_cost == 0
        assert usage.calculated_input_cost is None
        # Result is new object with costs
        assert result.calculated_input_cost > 0
        assert result is not usage

    def test_respects_cached_tokens(self):
        usage_no_cache = Usage(input=1000, output=500, total=1500)
        usage_with_cache = Usage(input=1000, output=500, total=1500, cached_tokens=800)

        result_no_cache = calculate_usage_cost(usage_no_cache, model="gpt-4o")
        result_with_cache = calculate_usage_cost(usage_with_cache, model="gpt-4o")

        assert result_with_cache.calculated_input_cost < result_no_cache.calculated_input_cost

    def test_respects_reasoning_tokens(self):
        usage = Usage(input=100, output=50, total=150, reasoning_tokens=30)
        result = calculate_usage_cost(usage, model="o3-mini")
        assert result.calculated_total_cost is not None

    def test_none_model_returns_unchanged_tokens_no_costs(self):
        usage = Usage(input=100, output=50, total=150)
        result = calculate_usage_cost(usage, model=None)
        assert result.input == 100
        assert result.output == 50
        assert result.total_cost == 0

    def test_preserves_all_token_fields(self):
        usage = Usage(
            input=100,
            output=50,
            total=150,
            cached_tokens=20,
            reasoning_tokens=10,
        )
        result = calculate_usage_cost(usage, model="gpt-4o")
        assert result.input == 100
        assert result.output == 50
        assert result.total == 150
        assert result.cached_tokens == 20
        assert result.reasoning_tokens == 10


# ── set_usage() — mutation layer ──────────────────────────────────────────────


class TestSetUsageMutation:
    """set_usage() creates Usage and assigns it to the current span."""

    def test_creates_usage_on_span(self):
        exporter = InMemoryExporter()
        etrace.init(exporters=[exporter], calculate_costs=False, auto_instrument={"llm": False})
        try:
            with etrace.trace("llm", kind=TraceKind.LLM, model="gpt-4o"):
                usage = etrace.set_usage(input_tokens=100, output_tokens=50)
                assert usage.input == 100
                assert usage.output == 50
                assert usage.total == 150
            span = exporter.get_finished_spans()[0]
            assert span.usage is not None
            assert span.usage.input == 100
        finally:
            etrace.shutdown()

    def test_sets_model_on_span(self):
        exporter = InMemoryExporter()
        etrace.init(exporters=[exporter], calculate_costs=False, auto_instrument={"llm": False})
        try:
            with etrace.trace("llm", kind=TraceKind.LLM):
                etrace.set_usage(input_tokens=10, model="gpt-4o-mini")
            span = exporter.get_finished_spans()[0]
            assert span.model == "gpt-4o-mini"
        finally:
            etrace.shutdown()

    def test_total_auto_computed(self):
        """total defaults to input + output when not explicitly given."""
        with etrace.trace("test"):
            usage = etrace.set_usage(input_tokens=30, output_tokens=20)
            assert usage.total == 50

    def test_total_explicit_overrides(self):
        with etrace.trace("test"):
            usage = etrace.set_usage(input_tokens=30, output_tokens=20, total_tokens=99)
            assert usage.total == 99

    def test_cached_and_reasoning_tokens(self):
        with etrace.trace("test"):
            usage = etrace.set_usage(
                input_tokens=100,
                output_tokens=50,
                cached_tokens=30,
                reasoning_tokens=10,
            )
            assert usage.cached_tokens == 30
            assert usage.reasoning_tokens == 10

    def test_no_active_span_returns_empty_usage(self):
        usage = etrace.set_usage(input_tokens=100)
        assert usage.input == 0  # no span → empty Usage, not mutated

    def test_preserves_existing_model_if_not_overridden(self):
        exporter = InMemoryExporter()
        etrace.init(exporters=[exporter], calculate_costs=False, auto_instrument={"llm": False})
        try:
            with etrace.trace("llm", kind=TraceKind.LLM, model="gpt-4o"):
                etrace.set_usage(input_tokens=10)  # no model arg
            span = exporter.get_finished_spans()[0]
            assert span.model == "gpt-4o"
        finally:
            etrace.shutdown()


# ── set_usage() auto-cost delegation ──────────────────────────────────────────


class TestSetUsageAutoCost:
    """When calculate_costs=True (default), set_usage() delegates to calculate_usage_cost()."""

    def test_auto_calculates_cost_when_enabled(self):
        exporter = InMemoryExporter()
        etrace.init(exporters=[exporter], calculate_costs=True, auto_instrument={"llm": False})
        try:
            with etrace.trace("llm", kind=TraceKind.LLM, model="gpt-4o"):
                usage = etrace.set_usage(input_tokens=1000, output_tokens=500)
            assert usage.total_cost > 0
            assert usage.calculated_input_cost is not None
        finally:
            etrace.shutdown()

    def test_no_cost_when_disabled(self):
        exporter = InMemoryExporter()
        etrace.init(exporters=[exporter], calculate_costs=False, auto_instrument={"llm": False})
        try:
            with etrace.trace("llm", kind=TraceKind.LLM, model="gpt-4o"):
                usage = etrace.set_usage(input_tokens=1000, output_tokens=500)
            assert usage.total_cost == 0
            assert usage.calculated_input_cost is None
        finally:
            etrace.shutdown()

    def test_uses_span_model_when_model_arg_not_given(self):
        """If set_usage() doesn't receive model=, it should use span.model for costing."""
        exporter = InMemoryExporter()
        etrace.init(exporters=[exporter], calculate_costs=True, auto_instrument={"llm": False})
        try:
            with etrace.trace("llm", kind=TraceKind.LLM, model="gpt-4o"):
                usage = etrace.set_usage(input_tokens=1000, output_tokens=500)
            assert usage.total_cost > 0
        finally:
            etrace.shutdown()

    def test_model_arg_overrides_span_model(self):
        exporter = InMemoryExporter()
        etrace.init(exporters=[exporter], calculate_costs=True, auto_instrument={"llm": False})
        try:
            with etrace.trace("llm", kind=TraceKind.LLM, model="gpt-4o"):
                etrace.set_usage(input_tokens=1000, output_tokens=500, model="gpt-4o-mini")
            # gpt-4o-mini has different pricing than gpt-4o
            span = exporter.get_finished_spans()[0]
            assert span.model == "gpt-4o-mini"
        finally:
            etrace.shutdown()

    def test_no_crash_on_unknown_model(self):
        with etrace.trace("test", model="unknown-model-xyz"):
            usage = etrace.set_usage(input_tokens=100, output_tokens=50)
            assert usage.total_cost == 0


# ── Span.calc_cost() convenience ──────────────────────────────────────────────


class TestSpanCalcCost:
    """Span.calc_cost() is a convenience that calls calculate_usage_cost() in place."""

    def test_calc_cost_populates_usage(self):
        exporter = InMemoryExporter()
        etrace.init(exporters=[exporter], calculate_costs=False, auto_instrument={"llm": False})
        try:
            with etrace.trace("llm", kind=TraceKind.LLM, model="gpt-4o") as span:
                etrace.set_usage(input_tokens=1000, output_tokens=500)
                assert span.usage.total_cost == 0  # no auto-calc

                span.calc_cost()
                assert span.usage.total_cost > 0
                assert span.usage.calculated_input_cost > 0
        finally:
            etrace.shutdown()

    def test_calc_cost_noop_when_no_usage(self):
        with etrace.trace("test", model="gpt-4o") as span:
            span.calc_cost()  # should not crash
            assert span.usage is None

    def test_calc_cost_noop_when_no_model(self):
        with etrace.trace("test") as span:
            etrace.set_usage(input_tokens=100)
            span.calc_cost()
            assert span.usage.total_cost == 0
