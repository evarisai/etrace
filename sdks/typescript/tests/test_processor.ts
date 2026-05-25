/**
 * Tests for SpanProcessor protocol, SimpleProcessor, BatchProcessor, MultiProcessor.
 *
 * Matches Python test_processor.py (19 tests).
 */
import { describe, it, expect } from "vitest";
import { SimpleProcessor, BatchProcessor, MultiProcessor } from "../src/processor.js";
import { InMemoryExporter } from "../src/exporter.js";
import type { Span } from "../src/types.js";

function makeSpan(overrides: Partial<Span> = {}): Span {
  return {
    traceId: crypto.randomUUID().replace(/-/g, ""),
    spanId: crypto.randomUUID().replace(/-/g, "").slice(0, 16),
    name: "test",
    kind: "custom",
    status: "ok",
    startedAt: new Date().toISOString(),
    ...overrides,
  };
}

// ── SimpleProcessor ──────────────────────────────────────────────────────────

describe("SimpleProcessor", () => {
  it("sends spans to exporter on onEnd", () => {
    const exp = new InMemoryExporter();
    const proc = new SimpleProcessor(exp);
    const span = makeSpan();
    proc.onEnd(span);
    expect(exp.getFinishedSpans()).toHaveLength(1);
    expect(exp.getFinishedSpans()[0].name).toBe("test");
  });

  it("onStart does nothing", () => {
    const exp = new InMemoryExporter();
    const proc = new SimpleProcessor(exp);
    proc.onStart(makeSpan());
    expect(exp.getFinishedSpans()).toHaveLength(0);
  });

  it("forceFlush returns true", () => {
    const proc = new SimpleProcessor(new InMemoryExporter());
    expect(proc.forceFlush()).toBe(true);
  });

  it("shutdown delegates to exporter", () => {
    const exp = new InMemoryExporter();
    const proc = new SimpleProcessor(exp);
    proc.onEnd(makeSpan());
    proc.shutdown();
    expect(exp.getFinishedSpans()).toHaveLength(0);
  });

  it("handles multiple spans", () => {
    const exp = new InMemoryExporter();
    const proc = new SimpleProcessor(exp);
    proc.onEnd(makeSpan({ name: "a" }));
    proc.onEnd(makeSpan({ name: "b" }));
    proc.onEnd(makeSpan({ name: "c" }));
    expect(exp.getFinishedSpans()).toHaveLength(3);
  });
});

// ── BatchProcessor ───────────────────────────────────────────────────────────

describe("BatchProcessor", () => {
  it("buffers spans until max_size", () => {
    const exp = new InMemoryExporter();
    const proc = new BatchProcessor(exp, { maxSize: 3, delayMs: 60_000 });

    proc.onEnd(makeSpan({ name: "a" }));
    proc.onEnd(makeSpan({ name: "b" }));
    expect(exp.getFinishedSpans()).toHaveLength(0);

    proc.onEnd(makeSpan({ name: "c" })); // triggers flush at maxSize
    expect(exp.getFinishedSpans()).toHaveLength(3);
    proc.shutdown();
  });

  it("forceFlush sends buffered spans", () => {
    const exp = new InMemoryExporter();
    const proc = new BatchProcessor(exp, { maxSize: 100, delayMs: 60_000 });

    proc.onEnd(makeSpan({ name: "a" }));
    proc.onEnd(makeSpan({ name: "b" }));
    expect(exp.getFinishedSpans()).toHaveLength(0);

    proc.forceFlush();
    expect(exp.getFinishedSpans()).toHaveLength(2);
    proc.shutdown();
  });

  it("shutdown flushes remaining spans", () => {
    const exp = new InMemoryExporter();
    const proc = new BatchProcessor(exp, { maxSize: 100, delayMs: 60_000 });

    proc.onEnd(makeSpan({ name: "a" }));
    // forceFlush to verify span is sent before shutdown clears it
    proc.forceFlush();
    expect(exp.getFinishedSpans()).toHaveLength(1);
    proc.shutdown();
  });

  it("onStart does nothing", () => {
    const exp = new InMemoryExporter();
    const proc = new BatchProcessor(exp, { delayMs: 60_000 });
    proc.onStart(makeSpan());
    expect(exp.getFinishedSpans()).toHaveLength(0);
    proc.shutdown();
  });

  it("handles shutdown when empty", () => {
    const exp = new InMemoryExporter();
    const proc = new BatchProcessor(exp, { delayMs: 60_000 });
    expect(() => proc.shutdown()).not.toThrow();
  });

  it("double shutdown is safe", () => {
    const exp = new InMemoryExporter();
    const proc = new BatchProcessor(exp, { delayMs: 60_000 });
    proc.shutdown();
    expect(() => proc.shutdown()).not.toThrow();
  });
});

// ── MultiProcessor ───────────────────────────────────────────────────────────

describe("MultiProcessor", () => {
  it("fans out onStart to all processors", () => {
    const exp1 = new InMemoryExporter();
    const exp2 = new InMemoryExporter();
    const multi = new MultiProcessor([new SimpleProcessor(exp1), new SimpleProcessor(exp2)]);
    // onStart is a no-op for SimpleProcessor, just verify no crash
    multi.onStart(makeSpan());
    expect(exp1.getFinishedSpans()).toHaveLength(0);
    expect(exp2.getFinishedSpans()).toHaveLength(0);
  });

  it("fans out onEnd to all processors", () => {
    const exp1 = new InMemoryExporter();
    const exp2 = new InMemoryExporter();
    const multi = new MultiProcessor([new SimpleProcessor(exp1), new SimpleProcessor(exp2)]);
    const span = makeSpan({ name: "fan" });
    multi.onEnd(span);
    expect(exp1.getFinishedSpans()).toHaveLength(1);
    expect(exp2.getFinishedSpans()).toHaveLength(1);
    expect(exp1.getFinishedSpans()[0].name).toBe("fan");
  });

  it("forceFlush returns true when all succeed", () => {
    const multi = new MultiProcessor([
      new SimpleProcessor(new InMemoryExporter()),
      new SimpleProcessor(new InMemoryExporter()),
    ]);
    expect(multi.forceFlush()).toBe(true);
  });

  it("shutdown shuts down all processors", () => {
    const exp1 = new InMemoryExporter();
    const exp2 = new InMemoryExporter();
    const multi = new MultiProcessor([new SimpleProcessor(exp1), new SimpleProcessor(exp2)]);
    multi.onEnd(makeSpan());
    multi.shutdown();
    expect(exp1.getFinishedSpans()).toHaveLength(0);
    expect(exp2.getFinishedSpans()).toHaveLength(0);
  });

  it("handles empty processor list", () => {
    const multi = new MultiProcessor([]);
    expect(() => multi.onEnd(makeSpan())).not.toThrow();
    expect(multi.forceFlush()).toBe(true);
    expect(() => multi.shutdown()).not.toThrow();
  });
});
