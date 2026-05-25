/**
 * Tests for SpanExporter protocol, InMemoryExporter, ConsoleExporter.
 *
 * Matches Python test_exporter.py (17 tests).
 */
import { describe, it, expect } from "vitest";
import { InMemoryExporter, ConsoleExporter, SpanExportResult } from "../src/exporter.js";
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

describe("SpanExportResult", () => {
  it("has SUCCESS=0 and FAILED=1", () => {
    expect(SpanExportResult.SUCCESS).toBe(0);
    expect(SpanExportResult.FAILED).toBe(1);
  });
});

describe("InMemoryExporter", () => {
  it("exports spans and returns SUCCESS", () => {
    const exp = new InMemoryExporter();
    const span = makeSpan();
    const result = exp.export([span]);
    expect(result).toBe(SpanExportResult.SUCCESS);
  });

  it("stores exported spans", () => {
    const exp = new InMemoryExporter();
    const s1 = makeSpan({ name: "a" });
    const s2 = makeSpan({ name: "b" });
    exp.export([s1, s2]);
    expect(exp.getFinishedSpans()).toHaveLength(2);
    expect(exp.getFinishedSpans()[0].name).toBe("a");
    expect(exp.getFinishedSpans()[1].name).toBe("b");
  });

  it("returns a copy from getFinishedSpans", () => {
    const exp = new InMemoryExporter();
    exp.export([makeSpan()]);
    const copy = exp.getFinishedSpans();
    copy.push(makeSpan({ name: "extra" }));
    expect(exp.getFinishedSpans()).toHaveLength(1);
  });

  it("clear removes all spans", () => {
    const exp = new InMemoryExporter();
    exp.export([makeSpan()]);
    exp.clear();
    expect(exp.getFinishedSpans()).toHaveLength(0);
  });

  it("shutdown clears all spans", () => {
    const exp = new InMemoryExporter();
    exp.export([makeSpan()]);
    exp.shutdown();
    expect(exp.getFinishedSpans()).toHaveLength(0);
  });

  it("forceFlush returns true", () => {
    const exp = new InMemoryExporter();
    expect(exp.forceFlush()).toBe(true);
  });

  it("handles multiple sequential exports", () => {
    const exp = new InMemoryExporter();
    exp.export([makeSpan({ name: "a" })]);
    exp.export([makeSpan({ name: "b" })]);
    exp.export([makeSpan({ name: "c" })]);
    expect(exp.getFinishedSpans()).toHaveLength(3);
  });

  it("handles empty export", () => {
    const exp = new InMemoryExporter();
    const result = exp.export([]);
    expect(result).toBe(SpanExportResult.SUCCESS);
    expect(exp.getFinishedSpans()).toHaveLength(0);
  });
});

describe("ConsoleExporter", () => {
  it("exports spans and returns SUCCESS", () => {
    const exp = new ConsoleExporter();
    const result = exp.export([makeSpan()]);
    expect(result).toBe(SpanExportResult.SUCCESS);
  });

  it("shutdown does not throw", () => {
    const exp = new ConsoleExporter();
    expect(() => exp.shutdown()).not.toThrow();
  });
});
