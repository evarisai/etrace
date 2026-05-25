"""Tests for the pricing module — cost calculation and normalization."""

import os
import sys

import pytest

# Add src to path so we can import without installing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from etrace._pricing import (
    MODEL_COUNT,
    PRICING,
    calculate_cost,
    normalize_model_name,
)

# ── normalize_model_name ─────────────────────────────────────────────────────


class TestNormalizeModelName:
    def test_basic(self):
        assert normalize_model_name("gpt-4o") == "gpt-4o"

    def test_strips_openrouter_prefix(self):
        assert normalize_model_name("openrouter/gpt-4o") == "gpt-4o"

    def test_strips_azure_prefix(self):
        assert normalize_model_name("azure/gpt-4o") == "gpt-4o"

    def test_strips_bedrock_prefix(self):
        assert normalize_model_name("bedrock/anthropic.claude-3") == "anthropic.claude-3"

    def test_case_insensitive(self):
        assert normalize_model_name("OpenRouter/GPT-4o") == "gpt-4o"

    def test_whitespace(self):
        assert normalize_model_name("  gpt-4o  ") == "gpt-4o"

    def test_no_prefix(self):
        assert normalize_model_name("claude-3-opus") == "claude-3-opus"


# ── calculate_cost ────────────────────────────────────────────────────────────


class TestCalculateCost:
    def test_known_model(self):
        """Verify cost calculation for a known model."""
        # Find a model with known pricing
        assert "gpt-4o" in PRICING or any("gpt-4o" in k for k in PRICING)

        # If gpt-4o is available, test it
        if "gpt-4o" in PRICING:
            PRICING["gpt-4o"]
            cost = calculate_cost("gpt-4o", input_tokens=1000, output_tokens=500)
            assert cost["input_cost"] > 0
            assert cost["output_cost"] > 0
            assert cost["total_cost"] == pytest.approx(cost["input_cost"] + cost["output_cost"], abs=1e-10)

    def test_unknown_model_returns_empty(self):
        assert calculate_cost("nonexistent-model-xyz", 100, 100) == {}

    def test_zero_tokens(self):
        """Zero tokens should return zero cost."""
        # Use any model that exists
        model = next(iter(PRICING))
        cost = calculate_cost(model, input_tokens=0, output_tokens=0)
        assert cost["total_cost"] == 0.0

    def test_case_insensitive_lookup(self):
        """Model lookup should be case-insensitive."""
        model = next(iter(PRICING))
        cost_upper = calculate_cost(model.upper(), 100, 100)
        cost_lower = calculate_cost(model.lower(), 100, 100)
        # Both should find the model (or both return empty)
        assert cost_upper == cost_lower

    def test_cached_tokens(self):
        """Cached tokens should use cache_read pricing if available."""
        # Find a model with cache_read pricing
        model = None
        for k, v in PRICING.items():
            if "cache_read" in v and v.get("cache_read", 0) > 0:
                model = k
                break

        if model:
            cost_no_cache = calculate_cost(model, 1000, 100)
            cost_with_cache = calculate_cost(model, 1000, 100, cached_tokens=500)
            # With cache, cost should be different (usually lower)
            assert cost_with_cache["total_cost"] != cost_no_cache["total_cost"]

    def test_reasoning_tokens(self):
        """Reasoning tokens should use reasoning pricing if available."""
        model = None
        for k, v in PRICING.items():
            if "reasoning" in v and v.get("reasoning", 0) > 0:
                model = k
                break

        if model:
            cost_no_reasoning = calculate_cost(model, 1000, 100)
            cost_with_reasoning = calculate_cost(model, 1000, 100, reasoning_tokens=500)
            assert cost_with_reasoning["total_cost"] != cost_no_reasoning["total_cost"]

    def test_result_has_expected_keys(self):
        model = next(iter(PRICING))
        cost = calculate_cost(model, 100, 100)
        assert "input_cost" in cost
        assert "output_cost" in cost
        assert "total_cost" in cost


# ── PRICING catalog ──────────────────────────────────────────────────────────


class TestPricingCatalog:
    def test_catalog_not_empty(self):
        assert len(PRICING) > 0

    def test_model_count_positive(self):
        assert MODEL_COUNT > 0

    def test_all_entries_have_input_or_output(self):
        """Every pricing entry should have at least input or output (may be zero for free models)."""
        for model_id, rates in PRICING.items():
            assert "input" in rates or "output" in rates, f"Model {model_id} has no input or output key"

    def test_rates_are_per_token(self):
        """Per-token rates should be very small numbers (< 0.1 USD per token)."""
        for model_id, rates in PRICING.items():
            for rate_name, value in rates.items():
                assert value < 0.1, f"{model_id}.{rate_name} = {value} seems too high for per-token rate"
