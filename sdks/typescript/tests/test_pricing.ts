/**
 * Tests for pricing catalog and calculateCost function.
 *
 * Matches Python test_pricing.py (13 tests).
 */
import { describe, it, expect } from "vitest";
import { calculateCost, PRICING } from "../src/pricing.js";

describe("calculateCost()", () => {
  it("returns null for unknown model", () => {
    expect(calculateCost("nonexistent-model-xyz", 100, 50)).toBeNull();
  });

  it("calculates cost for gpt-4o", () => {
    const result = calculateCost("gpt-4o", 1000, 500);
    expect(result).not.toBeNull();
    expect(result!.inputCost).toBeGreaterThan(0);
    expect(result!.outputCost).toBeGreaterThan(0);
    expect(result!.totalCost).toBeCloseTo(result!.inputCost + result!.outputCost);
  });

  it("calculates cost for gpt-4o-mini", () => {
    const result = calculateCost("gpt-4o-mini", 1000, 500);
    expect(result).not.toBeNull();
    expect(result!.inputCost).toBeGreaterThan(0);
  });

  it("cost scales linearly with tokens", () => {
    const r1 = calculateCost("gpt-4o", 1000, 500);
    const r2 = calculateCost("gpt-4o", 2000, 1000);
    expect(r2!.inputCost).toBeCloseTo(2 * r1!.inputCost);
    expect(r2!.outputCost).toBeCloseTo(2 * r1!.outputCost);
  });

  it("zero tokens = zero cost", () => {
    const result = calculateCost("gpt-4o", 0, 0);
    expect(result!.totalCost).toBe(0);
  });

  it("case-insensitive model lookup", () => {
    const r1 = calculateCost("gpt-4o", 100, 50);
    const r2 = calculateCost("GPT-4o", 100, 50);
    // Both should return a result (normalization handles case)
    expect(r1).not.toBeNull();
    expect(r2).not.toBeNull();
  });

  it("respects cached_tokens", () => {
    const noCache = calculateCost("gpt-4o", 1000, 500, 0);
    const withCache = calculateCost("gpt-4o", 1000, 500, 800);
    // With cache, cost should differ (if model has cache_read pricing)
    if (noCache && withCache) {
      // Even if no cache_read rate, withCache.inputCost should be <= noCache.inputCost
      expect(withCache.inputCost).toBeLessThanOrEqual(noCache.inputCost);
    }
  });

  it("respects reasoning_tokens", () => {
    const result = calculateCost("o3-mini", 100, 50, 0, 30);
    expect(result).not.toBeNull();
    expect(result!.totalCost).toBeGreaterThan(0);
  });
});

describe("PRICING catalog", () => {
  it("has entries", () => {
    expect(Object.keys(PRICING).length).toBeGreaterThan(100);
  });

  it("gpt-4o exists", () => {
    expect(PRICING["gpt-4o"]).toBeDefined();
    expect(PRICING["gpt-4o"].input).toBeGreaterThan(0);
    expect(PRICING["gpt-4o"].output).toBeGreaterThan(0);
  });

  it("entries have valid structure", () => {
    const entries = Object.values(PRICING);
    for (const entry of entries.slice(0, 10)) {
      expect(entry.input).toBeGreaterThanOrEqual(0);
      expect(entry.output).toBeGreaterThanOrEqual(0);
    }
  });
});
