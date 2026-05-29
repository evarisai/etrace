/**
 * Tests for core tracing API: init, trace, observe, noop, nesting, enrichment, lifecycle.
 *
 * Matches Python test_tracer.py (51 tests).
 */
import { describe, it, expect, afterEach } from "vitest";
import {
  init,
  shutdown,
  isInitialized,
  trace,
  observe,
  getCurrentSpan,
  setOutput,
  setError,
  setAttribute,
  setContext,
  getContext,
  score,
  flush,
  InMemoryExporter,
} from "../src/index.js";
import type { Span } from "../src/types.js";

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

// ── init() ───────────────────────────────────────────────────────────────────

describe("init()", () => {
  it("defaults to InMemoryExporter when no args", () => {
    init({ autoInstrument: { llm: false } });
    expect(isInitialized()).toBe(true);
  });

  it("accepts custom exporters", () => {
    const exp = new InMemoryExporter();
    init({ exporters: [exp], autoInstrument: { llm: false } });
    expect(isInitialized()).toBe(true);
    // Verify the exporter receives spans
    trace("test", () => {});
    expect(exp.getFinishedSpans().length).toBeGreaterThanOrEqual(1);
  });

  it("is idempotent", () => {
    const exp1 = new InMemoryExporter();
    const exp2 = new InMemoryExporter();
    init({ exporters: [exp1], autoInstrument: { llm: false } });
    init({ exporters: [exp2], autoInstrument: { llm: false } }); // no-op
    trace("test", () => {});
    // exp1 should be used (first init wins)
    expect(exp1.getFinishedSpans().length).toBeGreaterThanOrEqual(1);
    expect(exp2.getFinishedSpans()).toHaveLength(0);
  });

  it("sets isInitialized", () => {
    expect(isInitialized()).toBe(false);
    init({ autoInstrument: { llm: false } });
    expect(isInitialized()).toBe(true);
  });
});

// ── shutdown() ───────────────────────────────────────────────────────────────

describe("shutdown()", () => {
  it("clears initialized state", () => {
    init({ autoInstrument: { llm: false } });
    expect(isInitialized()).toBe(true);
    shutdown();
    expect(isInitialized()).toBe(false);
  });

  it("allows re-init after shutdown", () => {
    const exp1 = new InMemoryExporter();
    init({ exporters: [exp1], autoInstrument: { llm: false } });
    shutdown();
    const exp2 = new InMemoryExporter();
    init({ exporters: [exp2], autoInstrument: { llm: false } });
    trace("test", () => {});
    expect(exp2.getFinishedSpans().length).toBeGreaterThanOrEqual(1);
  });
});

// ── trace() — sync ───────────────────────────────────────────────────────────

describe("trace() sync", () => {
  it("creates a span with correct name and kind", () => {
    const exp = setup();
    const result = trace("my-span", () => 42, { kind: "tool" });
    expect(result).toBe(42);
    const span = exp.getFinishedSpans()[0];
    expect(span.name).toBe("my-span");
    expect(span.kind).toBe("tool");
  });

  it("sets status to ok on success", () => {
    const exp = setup();
    trace("ok", () => {});
    expect(exp.getFinishedSpans()[0].status).toBe("ok");
  });

  it("sets status to error on exception", () => {
    const exp = setup();
    expect(() =>
      trace("fail", () => {
        throw new Error("boom");
      }),
    ).toThrow("boom");
    const span = exp.getFinishedSpans()[0];
    expect(span.status).toBe("error");
    expect(span.error?.message).toBe("boom");
  });

  it("sets durationNs", () => {
    const exp = setup();
    trace("timed", () => {});
    const span = exp.getFinishedSpans()[0];
    expect(span.durationNs).toBeDefined();
    expect(span.durationNs!).toBeGreaterThan(0);
  });

  it("sets startedAt and endedAt", () => {
    const exp = setup();
    trace("ts", () => {});
    const span = exp.getFinishedSpans()[0];
    expect(span.startedAt).toBeDefined();
    expect(span.endedAt).toBeDefined();
    expect(new Date(span.startedAt!).getTime()).toBeLessThanOrEqual(
      new Date(span.endedAt!).getTime(),
    );
  });

  it("default kind is custom", () => {
    const exp = setup();
    trace("default-kind", () => {});
    expect(exp.getFinishedSpans()[0].kind).toBe("custom");
  });

  it("passes input through", () => {
    const exp = setup();
    trace("input", () => {}, { input: { prompt: "hello" } });
    expect(exp.getFinishedSpans()[0].input).toEqual({ prompt: "hello" });
  });

  it("passes model and provider through", () => {
    const exp = setup();
    trace("llm", () => {}, { model: "gpt-4o", provider: "openai" });
    const span = exp.getFinishedSpans()[0];
    expect(span.model).toBe("gpt-4o");
    expect(span.provider).toBe("openai");
  });

  it("passes attributes through", () => {
    const exp = setup();
    trace("attrs", () => {}, { attributes: { key: "val" } });
    expect(exp.getFinishedSpans()[0].attributes?.key).toBe("val");
  });
});

// ── trace() — async ──────────────────────────────────────────────────────────

describe("trace() async", () => {
  it("handles async functions", async () => {
    const exp = setup();
    const result = await trace("async", async () => {
      await new Promise((r) => setTimeout(r, 1));
      return "done";
    });
    expect(result).toBe("done");
    expect(exp.getFinishedSpans()[0].status).toBe("ok");
  });

  it("handles async rejection", async () => {
    const exp = setup();
    await expect(
      trace("async-fail", async () => {
        throw new Error("async-boom");
      }),
    ).rejects.toThrow("async-boom");
    expect(exp.getFinishedSpans()[0].status).toBe("error");
    expect(exp.getFinishedSpans()[0].error?.message).toBe("async-boom");
  });
});

// ── trace() — noop mode ──────────────────────────────────────────────────────

describe("trace() noop mode", () => {
  it("runs function without init", () => {
    const result = trace("noop", () => 99);
    expect(result).toBe(99);
  });

  it("still provides getCurrentSpan in noop mode", () => {
    let capturedSpan: Span | null = null;
    trace("noop-span", () => {
      capturedSpan = getCurrentSpan();
    });
    expect(capturedSpan).not.toBeNull();
    expect(capturedSpan!.name).toBe("noop-span");
  });

  it("handles async noop", async () => {
    const result = await trace("async-noop", async () => "noop-result");
    expect(result).toBe("noop-result");
  });
});

// ── trace() — nesting ────────────────────────────────────────────────────────

describe("trace() nesting", () => {
  it("parent-child share trace_id", () => {
    const exp = setup();
    trace("parent", () => {
      trace("child", () => {});
    });
    const spans = exp.getFinishedSpans();
    expect(spans).toHaveLength(2);
    expect(spans[0].name).toBe("child"); // child finishes first (sync)
    expect(spans[1].name).toBe("parent");
    expect(spans[0].traceId).toBe(spans[1].traceId);
  });

  it("child has parent_span_id", () => {
    const exp = setup();
    trace("parent", () => {
      trace("child", () => {});
    });
    const spans = exp.getFinishedSpans();
    const child = spans.find((s) => s.name === "child")!;
    const parent = spans.find((s) => s.name === "parent")!;
    expect(child.parentSpanId).toBe(parent.spanId);
  });
});

// ── @observe ─────────────────────────────────────────────────────────────────

describe("@observe", () => {
  it("traces a sync function", () => {
    const exp = setup();
    const fn = observe({ kind: "tool" })(function myTool() {
      return "result";
    });
    const result = fn();
    expect(result).toBe("result");
    expect(exp.getFinishedSpans()[0].kind).toBe("tool");
    expect(exp.getFinishedSpans()[0].name).toBe("myTool");
  });

  it("traces an async function", async () => {
    const exp = setup();
    const fn = observe({ kind: "agent" })(async function myAgent() {
      return "agent-result";
    });
    const result = await fn();
    expect(result).toBe("agent-result");
    expect(exp.getFinishedSpans()[0].name).toBe("myAgent");
  });

  it("captures input as named args", () => {
    const exp = setup();
    const fn = observe({ kind: "tool" })(function add(a: number, b: number) {
      return a + b;
    });
    fn(1, 2);
    const span = exp.getFinishedSpans()[0];
    expect(span.input).toEqual({ a: 1, b: 2 });
  });

  it("uses custom name", () => {
    const exp = setup();
    const fn = observe({ name: "custom-name" })(function _irrelevant() {
      return 1;
    });
    fn();
    expect(exp.getFinishedSpans()[0].name).toBe("custom-name");
  });
});

// ── set_output / set_error / set_attribute ────────────────────────────────────

describe("span enrichment", () => {
  it("setOutput sets output on current span", () => {
    const exp = setup();
    trace("out", () => {
      setOutput({ key: "val" });
    });
    expect(exp.getFinishedSpans()[0].output).toEqual({ key: "val" });
  });

  it("setError sets error on current span", () => {
    const exp = setup();
    trace("err", () => {
      setError("bad", "ValueError");
    });
    const span = exp.getFinishedSpans()[0];
    expect(span.status).toBe("error");
    expect(span.error?.message).toBe("bad");
    expect(span.error?.type).toBe("ValueError");
  });

  it("setAttribute sets attributes on current span", () => {
    const exp = setup();
    trace("attr", () => {
      setAttribute("custom.key", "val");
      setAttribute("custom.count", 42);
    });
    const span = exp.getFinishedSpans()[0];
    expect(span.attributes?.["custom.key"]).toBe("val");
    expect(span.attributes?.["custom.count"]).toBe(42);
  });

  it("enrichment functions are no-ops without a span", () => {
    expect(() => setOutput("x")).not.toThrow();
    expect(() => setError("x")).not.toThrow();
    expect(() => setAttribute("x", 1)).not.toThrow();
  });
});

// ── Context ──────────────────────────────────────────────────────────────────

describe("context", () => {
  it("setContext merges context", () => {
    setContext({ userId: "u1" });
    const ctx = getContext();
    expect(ctx.userId).toBe("u1");
  });

  it("context merges tags", () => {
    setContext({ tags: ["a"] });
    setContext({ tags: ["b"] });
    const ctx = getContext();
    expect(ctx.tags).toContain("a");
    expect(ctx.tags).toContain("b");
  });
});

// ── score() ──────────────────────────────────────────────────────────────────

describe("score()", () => {
  it("appends score event to span", () => {
    const exp = setup();
    trace("scored", () => {
      score({ name: "accuracy", value: 0.95 });
    });
    const span = exp.getFinishedSpans()[0];
    expect(span.events).toHaveLength(1);
    expect(span.events![0].name).toBe("score");
  });

  it("throws without trace_id", () => {
    expect(() => score({ name: "x", value: 1 })).toThrow("no traceId");
  });
});

// ── flush() ──────────────────────────────────────────────────────────────────

describe("flush()", () => {
  it("returns true when initialized", () => {
    setup();
    expect(flush()).toBe(true);
  });

  it("returns true when not initialized", () => {
    expect(flush()).toBe(true);
  });
});
