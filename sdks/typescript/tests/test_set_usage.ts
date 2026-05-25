/**
 * Tests for setUsage() / calculateUsageCost() separation of concerns.
 *
 * Matches Python test_set_usage.py (23 tests).
 */
import { describe, it, expect, afterEach } from "vitest";
import {
  init,
  shutdown,
  trace,
  setUsage,
  calculateUsageCost,
  calcSpanCost,
  getCurrentSpan,
  InMemoryExporter,
} from "../src/index.js";
import type { Usage } from "../src/types.js";

afterEach(() => {
  shutdown();
});

function setup(opts?: { calculateCosts?: boolean }) {
  const exporter = new InMemoryExporter();
  init({
    exporters: [exporter],
    calculateCosts: opts?.calculateCosts ?? false,
    autoInstrument: { llm: false },
  });
  return exporter;
}

// ── calculateUsageCost() — pure function ──────────────────────────────────────

describe("calculateUsageCost()", () => {
  it("calculates cost for a known model", () => {
    const usage: Usage = { input: 1000, output: 500, total: 1500 };
    const result = calculateUsageCost(usage, "gpt-4o");
    expect(result.calculatedInputCost).toBeDefined();
    expect(result.calculatedInputCost!).toBeGreaterThan(0);
    expect(result.calculatedOutputCost).toBeDefined();
    expect(result.calculatedOutputCost!).toBeGreaterThan(0);
    expect(result.calculatedTotalCost).toBeCloseTo(
      result.calculatedInputCost! + result.calculatedOutputCost!,
    );
  });

  it("populates final costs", () => {
    const usage: Usage = { input: 1000, output: 500, total: 1500 };
    const result = calculateUsageCost(usage, "gpt-4o");
    expect(result.inputCost).toBe(result.calculatedInputCost);
    expect(result.outputCost).toBe(result.calculatedOutputCost);
    expect(result.totalCost).toBeCloseTo(result.inputCost! + result.outputCost!);
  });

  it("returns zero costs for unknown model", () => {
    const usage: Usage = { input: 100, output: 50, total: 150 };
    const result = calculateUsageCost(usage, "totally-unknown-model-xyz");
    expect(result.inputCost).toBeFalsy();
    expect(result.outputCost).toBeFalsy();
    expect(result.totalCost).toBeFalsy();
    expect(result.calculatedInputCost).toBeUndefined();
  });

  it("does not mutate the input", () => {
    const usage: Usage = { input: 1000, output: 500, total: 1500 };
    expect(usage.inputCost).toBeUndefined();
    expect(usage.calculatedInputCost).toBeUndefined();

    const result = calculateUsageCost(usage, "gpt-4o");

    // Original untouched
    expect(usage.inputCost).toBeUndefined();
    expect(usage.calculatedInputCost).toBeUndefined();
    // Result is a new object with costs
    expect(result.calculatedInputCost!).toBeGreaterThan(0);
    expect(result).not.toBe(usage);
  });

  it("respects cached tokens", () => {
    const noCache: Usage = { input: 1000, output: 500, total: 1500 };
    const withCache: Usage = { input: 1000, output: 500, total: 1500, cachedTokens: 800 };

    const r1 = calculateUsageCost(noCache, "gpt-4o");
    const r2 = calculateUsageCost(withCache, "gpt-4o");

    expect(r2.calculatedInputCost!).toBeLessThan(r1.calculatedInputCost!);
  });

  it("returns unchanged tokens for null model", () => {
    const usage: Usage = { input: 100, output: 50, total: 150 };
    const result = calculateUsageCost(usage, null);
    expect(result.input).toBe(100);
    expect(result.output).toBe(50);
    expect(result.totalCost).toBeFalsy();
  });

  it("preserves all token fields", () => {
    const usage: Usage = {
      input: 100,
      output: 50,
      total: 150,
      cachedTokens: 20,
      reasoningTokens: 10,
    };
    const result = calculateUsageCost(usage, "gpt-4o");
    expect(result.input).toBe(100);
    expect(result.output).toBe(50);
    expect(result.total).toBe(150);
    expect(result.cachedTokens).toBe(20);
    expect(result.reasoningTokens).toBe(10);
  });
});

// ── setUsage() — mutation layer ──────────────────────────────────────────────

describe("setUsage() mutation", () => {
  it("creates usage on span", () => {
    const exp = setup();
    trace(
      "llm",
      () => {
        const usage = setUsage({ inputTokens: 100, outputTokens: 50 });
        expect(usage.input).toBe(100);
        expect(usage.output).toBe(50);
        expect(usage.total).toBe(150);
      },
      { kind: "llm", model: "gpt-4o" },
    );
    const span = exp.getFinishedSpans()[0];
    expect(span.usage).toBeDefined();
    expect(span.usage!.input).toBe(100);
  });

  it("sets model on span", () => {
    const exp = setup();
    trace(
      "llm",
      () => {
        setUsage({ inputTokens: 10, model: "gpt-4o-mini" });
      },
      { kind: "llm" },
    );
    expect(exp.getFinishedSpans()[0].model).toBe("gpt-4o-mini");
  });

  it("total auto-computed", () => {
    trace("test", () => {
      const usage = setUsage({ inputTokens: 30, outputTokens: 20 });
      expect(usage.total).toBe(50);
    });
  });

  it("total explicit overrides", () => {
    trace("test", () => {
      const usage = setUsage({ inputTokens: 30, outputTokens: 20, totalTokens: 99 });
      expect(usage.total).toBe(99);
    });
  });

  it("cached and reasoning tokens", () => {
    trace("test", () => {
      const usage = setUsage({
        inputTokens: 100,
        outputTokens: 50,
        cachedTokens: 30,
        reasoningTokens: 10,
      });
      expect(usage.cachedTokens).toBe(30);
      expect(usage.reasoningTokens).toBe(10);
    });
  });

  it("returns empty without active span", () => {
    const usage = setUsage({ inputTokens: 100 });
    expect(usage.input).toBeUndefined();
  });

  it("preserves existing model if not overridden", () => {
    const exp = setup();
    trace(
      "llm",
      () => {
        setUsage({ inputTokens: 10 }); // no model arg
      },
      { kind: "llm", model: "gpt-4o" },
    );
    expect(exp.getFinishedSpans()[0].model).toBe("gpt-4o");
  });
});

// ── setUsage() auto-cost delegation ──────────────────────────────────────────

describe("setUsage() auto-cost", () => {
  it("auto-calculates cost when enabled", () => {
    setup({ calculateCosts: true });
    trace(
      "llm",
      () => {
        const usage = setUsage({ inputTokens: 1000, outputTokens: 500 });
        expect(usage.totalCost).toBeGreaterThan(0);
        expect(usage.calculatedInputCost).toBeDefined();
      },
      { kind: "llm", model: "gpt-4o" },
    );
  });

  it("no cost when disabled", () => {
    setup({ calculateCosts: false });
    trace(
      "llm",
      () => {
        const usage = setUsage({ inputTokens: 1000, outputTokens: 500 });
        expect(usage.totalCost).toBeFalsy();
        expect(usage.calculatedInputCost).toBeUndefined();
      },
      { kind: "llm", model: "gpt-4o" },
    );
  });

  it("uses span model when model arg not given", () => {
    setup({ calculateCosts: true });
    trace(
      "llm",
      () => {
        const usage = setUsage({ inputTokens: 1000, outputTokens: 500 });
        expect(usage.totalCost).toBeGreaterThan(0);
      },
      { kind: "llm", model: "gpt-4o" },
    );
  });

  it("no crash on unknown model", () => {
    trace(
      "test",
      () => {
        const usage = setUsage({ inputTokens: 100, outputTokens: 50 });
        expect(usage.totalCost).toBeFalsy();
      },
      { kind: "llm", model: "unknown-xyz" },
    );
  });
});

// ── calcSpanCost() convenience ───────────────────────────────────────────────

describe("calcSpanCost()", () => {
  it("populates usage cost", () => {
    setup({ calculateCosts: false });
    trace(
      "llm",
      () => {
        setUsage({ inputTokens: 1000, outputTokens: 500 });
        const span = getCurrentSpan()!;
        expect(span.usage!.totalCost).toBeFalsy();

        calcSpanCost(span);
        expect(span.usage!.totalCost).toBeGreaterThan(0);
        expect(span.usage!.calculatedInputCost).toBeGreaterThan(0);
      },
      { kind: "llm", model: "gpt-4o" },
    );
  });

  it("noop when no usage", () => {
    trace(
      "test",
      () => {
        const span = getCurrentSpan()!;
        calcSpanCost(span);
        expect(span.usage).toBeUndefined();
      },
      { model: "gpt-4o" },
    );
  });

  it("noop when no model", () => {
    trace("test", () => {
      setUsage({ inputTokens: 100 });
      const span = getCurrentSpan()!;
      calcSpanCost(span);
      expect(span.usage!.totalCost).toBeFalsy();
    });
  });
});
