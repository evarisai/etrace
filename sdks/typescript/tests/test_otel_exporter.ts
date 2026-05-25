/**
 * Tests for OtelExporter — etrace Span → OTel ReadableSpan bridge.
 *
 * Matches Python test_otel_exporter.py (19 tests).
 */
import { describe, it, expect, afterEach } from "vitest";
import type { Span } from "../src/types.js";
import { init, shutdown, trace, InMemoryExporter } from "../src/index.js";
import { OtelExporter } from "../src/otel/exporter.js";
import { SpanExportResult } from "../src/exporter.js";
import { InMemorySpanExporter } from "@opentelemetry/sdk-trace-base/build/src/export/InMemorySpanExporter.js";

afterEach(() => {
  shutdown();
});

function makeSpan(overrides: Partial<Span> = {}): Span {
  return {
    traceId: "a".repeat(32),
    spanId: "b".repeat(16),
    name: "test_span",
    kind: "tool",
    status: "ok",
    startedAt: new Date().toISOString(),
    endedAt: new Date().toISOString(),
    durationNs: 1_000_000,
    ...overrides,
  };
}

function getAttrs(otelSpan: { attributes: Record<string, unknown> }): Record<string, unknown> {
  // OTel ReadableSpan.attributes may be a Map or plain object
  const a = otelSpan.attributes as Record<string, unknown> & {
    forEach?: (cb: (v: unknown, k: string) => void) => void;
  };
  if (a.forEach) {
    const out: Record<string, unknown> = {};
    a.forEach((v, k) => {
      out[k] = v;
    });
    return out;
  }
  return { ...a };
}

// ── Unit tests: OtelExporter conversion ──────────────────────────────────────

describe("OtelExporter conversion", () => {
  it("converts basic etrace span to OTel format", () => {
    const otelMem = new InMemorySpanExporter();
    const exporter = new OtelExporter(otelMem);

    const span = makeSpan();
    const result = exporter.export([span]);

    expect(result).toBe(SpanExportResult.SUCCESS);
    const otelSpans = otelMem.getFinishedSpans();
    expect(otelSpans).toHaveLength(1);
    expect(otelSpans[0].name).toBe("test_span");
  });

  it("preserves trace and span IDs", () => {
    const otelMem = new InMemorySpanExporter();
    const exporter = new OtelExporter(otelMem);

    const span = makeSpan({
      traceId: "a".repeat(32),
      spanId: "b".repeat(16),
    });
    exporter.export([span]);

    const otelSpan = otelMem.getFinishedSpans()[0];
    expect(otelSpan.spanContext().traceId).toBe("a".repeat(32));
    expect(otelSpan.spanContext().spanId).toBe("b".repeat(16));
  });

  it("links parent span ID", () => {
    const otelMem = new InMemorySpanExporter();
    const exporter = new OtelExporter(otelMem);

    const span = makeSpan({ parentSpanId: "c".repeat(16) });
    exporter.export([span]);

    const otelSpan = otelMem.getFinishedSpans()[0];
    expect(otelSpan.parentSpanId).toBe("c".repeat(16));
  });

  it("maps status ok to OTel OK", () => {
    const otelMem = new InMemorySpanExporter();
    const exporter = new OtelExporter(otelMem);

    exporter.export([makeSpan({ status: "ok" })]);
    const s = otelMem.getFinishedSpans()[0];
    expect(s.status.code).toBe(1); // SpanStatusCode.OK
  });

  it("maps status error with description", () => {
    const otelMem = new InMemorySpanExporter();
    const exporter = new OtelExporter(otelMem);

    const span = makeSpan({ status: "error" });
    span.error = { message: "boom", type: "RuntimeError" };
    exporter.export([span]);

    const s = otelMem.getFinishedSpans()[0];
    expect(s.status.code).toBe(2); // SpanStatusCode.ERROR
    expect(s.status.message).toBe("boom");
  });

  it("maps usage to gen_ai attributes", () => {
    const otelMem = new InMemorySpanExporter();
    const exporter = new OtelExporter(otelMem);

    const span = makeSpan({ model: "gpt-4o", provider: "openai" });
    span.usage = { input: 100, output: 50, total: 150 };
    exporter.export([span]);

    const attrs = getAttrs(otelMem.getFinishedSpans()[0]);
    expect(attrs["gen_ai.usage.prompt_tokens"]).toBe(100);
    expect(attrs["gen_ai.usage.completion_tokens"]).toBe(50);
    expect(attrs["gen_ai.usage.total_tokens"]).toBe(150);
  });

  it("maps model and provider", () => {
    const otelMem = new InMemorySpanExporter();
    const exporter = new OtelExporter(otelMem);

    exporter.export([makeSpan({ model: "gpt-4o", provider: "openai" })]);

    const attrs = getAttrs(otelMem.getFinishedSpans()[0]);
    expect(attrs["gen_ai.request.model"]).toBe("gpt-4o");
    expect(attrs["gen_ai.system"]).toBe("openai");
  });

  it("sets etrace.kind attribute", () => {
    const otelMem = new InMemorySpanExporter();
    const exporter = new OtelExporter(otelMem);

    exporter.export([makeSpan({ kind: "llm" })]);

    const attrs = getAttrs(otelMem.getFinishedSpans()[0]);
    expect(attrs["etrace.kind"]).toBe("llm");
  });

  it("merges custom attributes", () => {
    const otelMem = new InMemorySpanExporter();
    const exporter = new OtelExporter(otelMem);

    exporter.export([makeSpan({ attributes: { custom_key: "custom_val" } })]);

    const attrs = getAttrs(otelMem.getFinishedSpans()[0]);
    expect(attrs["custom_key"]).toBe("custom_val");
  });

  it("captures input and output", () => {
    const otelMem = new InMemorySpanExporter();
    const exporter = new OtelExporter(otelMem);

    exporter.export([makeSpan({ input: "hello", output: "world" })]);

    const attrs = getAttrs(otelMem.getFinishedSpans()[0]);
    expect(attrs["etrace.input"]).toBe("hello");
    expect(attrs["etrace.output"]).toBe("world");
  });

  it("exports multiple spans in batch", () => {
    const otelMem = new InMemorySpanExporter();
    const exporter = new OtelExporter(otelMem);

    const spans = Array.from({ length: 5 }, (_, i) =>
      makeSpan({ name: `span_${i}`, spanId: String(i).padStart(16, "0") }),
    );
    exporter.export(spans);
    expect(otelMem.getFinishedSpans()).toHaveLength(5);
  });

  it("shutdown delegates to OTel exporter", () => {
    const otelMem = new InMemorySpanExporter();
    const exporter = new OtelExporter(otelMem);
    expect(() => exporter.shutdown()).not.toThrow();
  });

  it("forceFlush delegates to OTel exporter", async () => {
    const otelMem = new InMemorySpanExporter();
    const exporter = new OtelExporter(otelMem);
    // OTel InMemorySpanExporter.forceFlush() returns Promise<void>
    // OtelExporter wraps it and returns true
    const result = exporter.forceFlush(5000);
    const val = result instanceof Promise ? await result : result;
    expect(val).toBe(true);
  });
});

// ── Integration: etrace → OtelExporter → OTel InMemorySpanExporter ──────────

describe("OtelExporter integration", () => {
  it("etrace pipeline with OtelExporter produces OTel spans", () => {
    const otelMem = new InMemorySpanExporter();
    const otelExporter = new OtelExporter(otelMem);

    init({
      exporters: [otelExporter],
      autoInstrument: { llm: false },
    });

    trace("my_tool", () => {}, { kind: "tool" });

    // Check before shutdown (shutdown clears OTel InMemorySpanExporter)
    const otelSpans = otelMem.getFinishedSpans();
    expect(otelSpans).toHaveLength(1);
    expect(otelSpans[0].name).toBe("my_tool");

    const attrs = getAttrs(otelSpans[0]);
    expect(attrs["etrace.kind"]).toBe("tool");

    shutdown();
  });

  it("nested etrace spans produce OTel hierarchy", () => {
    const otelMem = new InMemorySpanExporter();
    const otelExporter = new OtelExporter(otelMem);

    init({
      exporters: [otelExporter],
      autoInstrument: { llm: false },
    });

    trace(
      "parent",
      () => {
        trace("child", () => {});
      },
      { kind: "workflow" },
    );

    const otelSpans = otelMem.getFinishedSpans();
    expect(otelSpans).toHaveLength(2);

    const parent = otelSpans.find((s) => s.name === "parent")!;
    const child = otelSpans.find((s) => s.name === "child")!;

    expect(child.parentSpanId).toBe(parent.spanContext().spanId);
    expect(child.spanContext().traceId).toBe(parent.spanContext().traceId);

    shutdown();
  });

  it("dual exporter setup (OtelExporter + InMemoryExporter)", () => {
    const otelMem = new InMemorySpanExporter();
    const etraceMem = new InMemoryExporter();

    const otelExporter = new OtelExporter(otelMem);

    init({
      exporters: [otelExporter, etraceMem],
      autoInstrument: { llm: false },
    });

    trace("dual", () => {});

    expect(otelMem.getFinishedSpans()).toHaveLength(1);
    expect(etraceMem.getFinishedSpans()).toHaveLength(1);

    shutdown();
  });

  it("error span maps to OTel error status", () => {
    const otelMem = new InMemorySpanExporter();
    const otelExporter = new OtelExporter(otelMem);

    init({
      exporters: [otelExporter],
      autoInstrument: { llm: false },
    });

    expect(() =>
      trace(
        "failing",
        () => {
          throw new Error("boom");
        },
        { kind: "tool" },
      ),
    ).toThrow("boom");

    const otelSpans = otelMem.getFinishedSpans();
    expect(otelSpans).toHaveLength(1);
    expect(otelSpans[0].status.code).toBe(2); // SpanStatusCode.ERROR
    expect(otelSpans[0].status.message).toBe("boom");

    shutdown();
  });

  it("observe with OtelExporter creates OTel spans", async () => {
    const otelMem = new InMemorySpanExporter();
    const otelExporter = new OtelExporter(otelMem);

    init({
      exporters: [otelExporter],
      autoInstrument: { llm: false },
    });

    const mod = await import("../src/index.js");
    const fn = mod.observe({ kind: "agent", name: "my_agent" })(function myAgent(x: number) {
      return x * 2;
    });
    const result = fn(5);
    expect(result).toBe(10);

    const otelSpans = otelMem.getFinishedSpans();
    expect(otelSpans).toHaveLength(1);
    expect(otelSpans[0].name).toBe("my_agent");

    shutdown();
  });
});
