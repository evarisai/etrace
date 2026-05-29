/**
 * Tests for convenience decorators and noop-mode contracts.
 *
 * Matches Python test_core.py (31 tests).
 */
import { describe, it, expect, afterEach } from "vitest";
import {
  init,
  shutdown,
  trace,
  observe,
  setUsage,
  setOutput,
  setError,
  setAttribute,
  InMemoryExporter,
  workflow,
  agent,
  step,
  tool,
  llm,
  http,
  retrieval,
  reranker,
  embedding,
  sandbox,
  handoff,
  approval,
  guardrail,
  evaluation,
  scorer,
} from "../src/index.js";

afterEach(() => {
  shutdown();
});

function setup() {
  const exporter = new InMemoryExporter();
  init({ exporters: [exporter], calculateCosts: false, autoInstrument: { llm: false } });
  return exporter;
}

// ── Noop decorators ──────────────────────────────────────────────────────────

describe("noop decorators", () => {
  const decorators: Record<string, (c?: Record<string, unknown>) => ReturnType<typeof observe>> = {
    workflow,
    agent,
    step,
    tool,
    llm,
    http,
    retrieval,
    reranker,
    embedding,
    sandbox,
    handoff,
    approval,
    guardrail,
    evaluation,
    scorer,
  };

  for (const [name, dec] of Object.entries(decorators)) {
    it(`${name}() works without init`, () => {
      const fn = dec()(function () {
        return 42;
      });
      expect(fn()).toBe(42);
    });

    it(`${name}() sets correct kind`, () => {
      const exp = setup();
      const fn = dec()(function () {
        return 1;
      });
      fn();
      const span = exp.getFinishedSpans()[0];
      // Map decorator name to expected kind
      const kindMap: Record<string, string> = {
        workflow: "workflow",
        agent: "agent",
        step: "step",
        tool: "tool",
        llm: "llm",
        http: "http",
        retrieval: "retrieval",
        reranker: "reranker",
        embedding: "embedding",
        sandbox: "sandbox",
        handoff: "handoff",
        approval: "approval",
        guardrail: "guardrail",
        evaluation: "eval",
        scorer: "scorer",
      };
      expect(span.kind).toBe(kindMap[name] ?? name);
    });
  }
});

// ── observe() contracts ──────────────────────────────────────────────────────

describe("observe() contracts", () => {
  it("captures input as named args by default", () => {
    const exp = setup();
    const fn = observe()(function add(a: number, b: number) {
      return a + b;
    });
    fn(3, 4);
    const span = exp.getFinishedSpans()[0];
    expect(span.input).toEqual({ a: 3, b: 4 });
  });

  it("respects custom name", () => {
    const exp = setup();
    const fn = observe({ name: "custom" })(function _ignored() {
      return 1;
    });
    fn();
    expect(exp.getFinishedSpans()[0].name).toBe("custom");
  });

  it("works with async functions", async () => {
    const exp = setup();
    const fn = observe()(async function asyncFn() {
      return "async-result";
    });
    const result = await fn();
    expect(result).toBe("async-result");
    expect(exp.getFinishedSpans()[0].name).toBe("asyncFn");
  });

  it("captures error on exception", () => {
    const exp = setup();
    const fn = observe()(function badFn() {
      throw new Error("oops");
    });
    expect(() => fn()).toThrow("oops");
    const span = exp.getFinishedSpans()[0];
    expect(span.status).toBe("error");
    expect(span.error?.message).toBe("oops");
  });
});

// ── setUsage contracts ───────────────────────────────────────────────────────

describe("setUsage() contracts", () => {
  it("basic token tracking", () => {
    trace(
      "test",
      () => {
        const usage = setUsage({ inputTokens: 100, outputTokens: 50 });
        expect(usage.input).toBe(100);
        expect(usage.output).toBe(50);
        expect(usage.total).toBe(150);
      },
      { kind: "llm", model: "gpt-4o" },
    );
  });

  it("no span returns empty", () => {
    const usage = setUsage({ inputTokens: 100 });
    expect(usage.input).toBeUndefined();
  });
});

// ── Enrichment contracts ─────────────────────────────────────────────────────

describe("enrichment contracts", () => {
  it("setOutput", () => {
    const exp = setup();
    trace("test", () => {
      setOutput({ key: "val" });
    });
    expect(exp.getFinishedSpans()[0].output).toEqual({ key: "val" });
  });

  it("setError", () => {
    const exp = setup();
    trace("test", () => {
      setError("bad", "ValueError");
    });
    const span = exp.getFinishedSpans()[0];
    expect(span.status).toBe("error");
    expect(span.error?.message).toBe("bad");
    expect(span.error?.type).toBe("ValueError");
  });

  it("setAttribute", () => {
    const exp = setup();
    trace("test", () => {
      setAttribute("custom.key", "val");
      setAttribute("custom.count", 42);
    });
    const span = exp.getFinishedSpans()[0];
    expect(span.attributes?.["custom.key"]).toBe("val");
    expect(span.attributes?.["custom.count"]).toBe(42);
  });
});
