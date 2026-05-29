/**
 * Cross-SDK parity tests — behaviors that must match between TypeScript and Python.
 *
 * These tests verify the shared SDK contract:
 *   - agent(fn) captures named input and output
 *   - tool(fn) captures named input and output
 *   - return value becomes span output
 *   - explicit setOutput overrides auto-captured output
 *   - nested agent/tool spans keep correct parent-child relation
 *   - opt-outs (captureInput: false, captureOutput: false) disable capture
 *
 * Overload tests:
 *   - agent(fn) — direct function wrap
 *   - agent({ name })(fn) — configured wrap
 *   - observe(fn)
 *   - observe({ name, kind })(fn)
 */
import { describe, it, expect, afterEach } from "vitest";
import {
  init,
  shutdown,
  agent,
  tool,
  step,
  observe,
  setOutput,
  InMemoryExporter,
} from "../src/index.js";

afterEach(() => {
  shutdown();
});

function setup() {
  const exporter = new InMemoryExporter();
  init({ exporters: [exporter], calculateCosts: false, autoInstrument: { llm: false } });
  return exporter;
}

// ── agent() decorator ───────────────────────────────────────────────────────

describe("agent() decorator", () => {
  it("captures named input and output", () => {
    const exp = setup();
    const fn = agent()(function myAgent(prompt: string) {
      return `response: ${prompt}`;
    });
    const result = fn("hello");
    expect(result).toBe("response: hello");

    const span = exp.getFinishedSpans()[0];
    expect(span.kind).toBe("agent");
    expect(span.input).toEqual({ prompt: "hello" });
    expect(span.output).toBe("response: hello");
    expect(span.status).toBe("ok");
  });

  it("works with async functions", async () => {
    const exp = setup();
    const fn = agent()(async function myAgent(prompt: string) {
      return `response: ${prompt}`;
    });
    const result = await fn("hello");
    expect(result).toBe("response: hello");

    const span = exp.getFinishedSpans()[0];
    expect(span.kind).toBe("agent");
    expect(span.input).toEqual({ prompt: "hello" });
    expect(span.output).toBe("response: hello");
  });

  it("direct function wrap overload: agent(fn)", () => {
    const exp = setup();
    const fn = agent(function directAgent(prompt: string) {
      return `response: ${prompt}`;
    });
    fn("test");

    const span = exp.getFinishedSpans()[0];
    expect(span.kind).toBe("agent");
    expect(span.name).toBe("directAgent");
  });

  it("configured overload: agent({ name })(fn)", () => {
    const exp = setup();
    const fn = agent({ name: "weatherAgent" })(function irrelevant(prompt: string) {
      return prompt;
    });
    fn("test");

    const span = exp.getFinishedSpans()[0];
    expect(span.name).toBe("weatherAgent");
    expect(span.kind).toBe("agent");
  });
});

// ── tool() decorator ───────────────────────────────────────────────────────

describe("tool() decorator", () => {
  it("captures named input and output", () => {
    const exp = setup();
    const fn = tool()(function search(query: string, limit: number) {
      return Array(limit).fill(query);
    });
    const result = fn("AI", 5);
    expect(result).toEqual(["AI", "AI", "AI", "AI", "AI"]);

    const span = exp.getFinishedSpans()[0];
    expect(span.kind).toBe("tool");
    expect(span.input).toEqual({ query: "AI", limit: 5 });
    expect(span.output).toEqual(["AI", "AI", "AI", "AI", "AI"]);
  });

  it("configured overload: tool({ name })(fn)", () => {
    const exp = setup();
    const fn = tool({ name: "get-weather" })(function getWeather(location: string) {
      return `sunny in ${location}`;
    });
    fn("Tokyo");

    const span = exp.getFinishedSpans()[0];
    expect(span.name).toBe("get-weather");
    expect(span.input).toEqual({ location: "Tokyo" });
    expect(span.output).toBe("sunny in Tokyo");
  });
});

// ── output capture ────────────────────────────────────────────────────────

describe("output capture", () => {
  it("return value becomes span output", () => {
    const exp = setup();
    const fn = tool()(function double(x: number) {
      return x * 2;
    });
    const result = fn(7);
    expect(result).toBe(14);
    expect(exp.getFinishedSpans()[0].output).toBe(14);
  });

  it("setOutput inside function wins over auto-capture", () => {
    // In TS, trace() checks span.output === undefined before auto-capturing.
    // setOutput inside the function body sets output first, so auto-capture skips.
    const exp = setup();
    const fn = tool()(function compute(x: number) {
      setOutput({ raw: x * 2, formatted: `Result: ${x * 2}` });
      return x * 2;
    });
    fn(5);
    const span = exp.getFinishedSpans()[0];
    expect(span.output).toEqual({ raw: 10, formatted: "Result: 10" });
  });

  it("setOutput with captureOutput:false overrides properly", () => {
    const exp = setup();
    const fn = tool({ captureOutput: false })(function compute(x: number) {
      setOutput({ custom: x * 3 });
      return x * 2; // This should NOT become the output
    });
    fn(5);
    expect(exp.getFinishedSpans()[0].output).toEqual({ custom: 15 });
  });
});

// ── nested spans ────────────────────────────────────────────────────────────

describe("nested agent/tool spans", () => {
  it("parent-child share trace_id and parent_span_id", () => {
    const exp = setup();
    const getData = tool()(function getData(key: string) {
      return `data-${key}`;
    });
    const myAgent = agent()(function myAgent(query: string) {
      return getData(query);
    });

    myAgent("test");
    const spans = exp.getFinishedSpans();
    expect(spans).toHaveLength(2);

    const toolSpan = spans.find((s) => s.kind === "tool")!;
    const agentSpan = spans.find((s) => s.kind === "agent")!;

    expect(agentSpan.traceId).toBe(toolSpan.traceId);
    expect(toolSpan.parentSpanId).toBe(agentSpan.spanId);
  });

  it("three-level nesting", () => {
    const exp = setup();
    const t3 = tool()(function nestTool(x: number) {
      return x + 1;
    });
    const t2 = step()(function nestStep(x: number) {
      return t3(x);
    });
    const t1 = agent()(function nestAgent(x: number) {
      return t2(x);
    });

    t1(10);
    const spans = exp.getFinishedSpans();
    expect(spans).toHaveLength(3);

    const toolSpan = spans.find((s) => s.name === "nestTool")!;
    const stepSpan = spans.find((s) => s.name === "nestStep")!;
    const agentSpan = spans.find((s) => s.name === "nestAgent")!;

    expect(toolSpan.parentSpanId).toBe(stepSpan.spanId);
    expect(stepSpan.parentSpanId).toBe(agentSpan.spanId);
    expect(agentSpan.traceId).toBe(stepSpan.traceId).toBe(toolSpan.traceId);
  });
});

// ── opt-outs ────────────────────────────────────────────────────────────────

describe("opt-outs", () => {
  it("captureInput: false disables input capture", () => {
    const exp = setup();
    const fn = tool({ captureInput: false })(function secretTool(_token: string) {
      return "done";
    });
    fn("secret-key-123");

    const span = exp.getFinishedSpans()[0];
    expect(span.input).toBeUndefined();
    expect(span.output).toBe("done");
  });

  it("captureOutput: false disables output capture", () => {
    const exp = setup();
    const fn = tool({ captureOutput: false })(function toolFn(x: number) {
      return x * 2;
    });
    fn(5);

    const span = exp.getFinishedSpans()[0];
    expect(span.output).toBeUndefined();
  });

  it("both false disables both", () => {
    const exp = setup();
    const fn = tool({ captureInput: false, captureOutput: false })(function toolFn(x: number) {
      return x * 2;
    });
    fn(5);

    const span = exp.getFinishedSpans()[0];
    expect(span.input).toBeUndefined();
    expect(span.output).toBeUndefined();
  });
});

// ── observe() overload tests ───────────────────────────────────────────────

describe("observe() overloads", () => {
  it("observe(fn) — direct function wrap", () => {
    const exp = setup();
    const fn = observe(function directFn(x: number) {
      return x + 1;
    });
    fn(10);

    const span = exp.getFinishedSpans()[0];
    expect(span.name).toBe("directFn");
    expect(span.kind).toBe("custom");
    expect(span.input).toEqual({ x: 10 });
    expect(span.output).toBe(11);
  });

  it("observe({ name, kind })(fn) — configured wrap", () => {
    const exp = setup();
    const fn = observe({ name: "custom-name", kind: "retrieval" })(function ignored(q: string) {
      return q;
    });
    fn("test");

    const span = exp.getFinishedSpans()[0];
    expect(span.name).toBe("custom-name");
    expect(span.kind).toBe("retrieval");
    expect(span.input).toEqual({ q: "test" });
    expect(span.output).toBe("test");
  });
});
