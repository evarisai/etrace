/**
 * Tests for EvarisExporter and init()/score() one-liners.
 *
 * Matches Python test_evaris.py (15 tests).
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { EvarisExporter, DEFAULT_ENDPOINT } from "../src/evaris/exporter.js";
import { shutdown, trace } from "../src/index.js";
import { SpanExportResult } from "../src/exporter.js";
import type { Span } from "../src/types.js";
import * as evarisClient from "../src/evaris/client.js";

afterEach(() => {
  vi.restoreAllMocks();
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

// ── EvarisExporter ───────────────────────────────────────────────────────────

describe("EvarisExporter", () => {
  it("POSTs spans to Evaris backend", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
    });
    vi.stubGlobal("fetch", mockFetch);

    const exporter = new EvarisExporter({ apiKey: "test-key", projectId: "proj-1" });
    const result = await exporter.export([makeSpan()]);

    expect(result).toBe(SpanExportResult.SUCCESS);
    expect(mockFetch).toHaveBeenCalledOnce();
    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toContain("runtime.evaris.ai");
  });

  it("includes authorization header", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, status: 200, statusText: "OK" });
    vi.stubGlobal("fetch", mockFetch);

    const exporter = new EvarisExporter({ apiKey: "sk-test-123", projectId: "proj-1" });
    await exporter.export([makeSpan()]);

    const opts = mockFetch.mock.calls[0][1] as RequestInit;
    const headers = opts.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer sk-test-123");
  });

  it("includes project ID header", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, status: 200, statusText: "OK" });
    vi.stubGlobal("fetch", mockFetch);

    const exporter = new EvarisExporter({ apiKey: "key", projectId: "proj-42" });
    await exporter.export([makeSpan()]);

    const opts = mockFetch.mock.calls[0][1] as RequestInit;
    const headers = opts.headers as Record<string, string>;
    expect(headers["X-Evaris-Project-ID"]).toBe("proj-42");
  });

  it("serializes span as JSON in request body", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, status: 200, statusText: "OK" });
    vi.stubGlobal("fetch", mockFetch);

    const exporter = new EvarisExporter({ apiKey: "key", projectId: "proj-1" });
    const span = makeSpan({ name: "my_span", kind: "llm" });
    await exporter.export([span]);

    const opts = mockFetch.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(opts.body as string);
    expect(Array.isArray(body)).toBe(true);
    expect(body[0].name).toBe("my_span");
    expect(body[0].kind).toBe("llm");
  });

  it("returns FAILURE on network error", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("network error"));
    vi.stubGlobal("fetch", mockFetch);

    const exporter = new EvarisExporter({ apiKey: "key", projectId: "proj-1" });
    const result = await exporter.export([makeSpan()]);
    expect(result).toBe(SpanExportResult.FAILED);
  });

  it("returns FAILURE on HTTP error", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
    });
    vi.stubGlobal("fetch", mockFetch);

    const exporter = new EvarisExporter({ apiKey: "key", projectId: "proj-1" });
    const result = await exporter.export([makeSpan()]);
    expect(result).toBe(SpanExportResult.FAILED);
  });

  it("uses custom endpoint", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, status: 200, statusText: "OK" });
    vi.stubGlobal("fetch", mockFetch);

    const exporter = new EvarisExporter({
      apiKey: "key",
      projectId: "proj-1",
      endpoint: "https://custom.example.com/v1/traces",
    });
    await exporter.export([makeSpan()]);

    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toBe("https://custom.example.com/v1/traces");
  });

  it("serializes usage in span body", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, status: 200, statusText: "OK" });
    vi.stubGlobal("fetch", mockFetch);

    const exporter = new EvarisExporter({ apiKey: "key", projectId: "proj-1" });
    const span = makeSpan();
    span.usage = { input: 100, output: 50, total: 150, totalCost: 0.005 };
    await exporter.export([span]);

    const opts = mockFetch.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(opts.body as string);
    expect(body[0].usage.input).toBe(100);
    expect(body[0].usage.total_cost).toBe(0.005);
  });

  it("serializes error in span body", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, status: 200, statusText: "OK" });
    vi.stubGlobal("fetch", mockFetch);

    const exporter = new EvarisExporter({ apiKey: "key", projectId: "proj-1" });
    const span = makeSpan({ status: "error" });
    span.error = { message: "boom", type: "ValueError" };
    await exporter.export([span]);

    const opts = mockFetch.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(opts.body as string);
    expect(body[0].error.message).toBe("boom");
    expect(body[0].error.type).toBe("ValueError");
  });

  it("shutdown is a safe no-op", () => {
    const exporter = new EvarisExporter({ apiKey: "key", projectId: "proj-1" });
    expect(() => exporter.shutdown()).not.toThrow();
  });

  it("forceFlush returns true", () => {
    const exporter = new EvarisExporter({ apiKey: "key", projectId: "proj-1" });
    expect(exporter.forceFlush()).toBe(true);
  });
});

// ── DEFAULT_ENDPOINT ─────────────────────────────────────────────────────────

describe("DEFAULT_ENDPOINT", () => {
  it("points to runtime.evaris.ai", () => {
    expect(DEFAULT_ENDPOINT).toBe("https://runtime.evaris.ai/v1/traces");
  });
});

// ── evaris.init() ────────────────────────────────────────────────────────────

describe("evaris.init()", () => {
  it("configures etrace with EvarisExporter", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, status: 200, statusText: "OK" });
    vi.stubGlobal("fetch", mockFetch);

    evarisClient.init({
      apiKey: "test-key",
      projectId: "proj-1",
      autoInstrument: { llm: false },
    });

    trace("test", () => {});

    // Allow async export to complete
    await new Promise((r) => setTimeout(r, 10));
    shutdown();

    expect(mockFetch).toHaveBeenCalled();
  });
});

// ── evaris.score() ───────────────────────────────────────────────────────────

describe("evaris.score()", () => {
  it("POSTs score to Evaris backend", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ id: "score-1" }),
    });
    vi.stubGlobal("fetch", mockFetch);

    await evarisClient.score({
      apiKey: "key",
      projectId: "proj-1",
      traceId: "abc123",
      name: "relevance",
      value: 0.9,
    });

    expect(mockFetch).toHaveBeenCalledOnce();
    const opts = mockFetch.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(opts.body as string);
    expect(body.trace_id).toBe("abc123");
    expect(body.name).toBe("relevance");
    expect(body.value).toBe(0.9);
  });

  it("includes auth headers in score request", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ id: "score-1" }),
    });
    vi.stubGlobal("fetch", mockFetch);

    await evarisClient.score({
      apiKey: "sk-test",
      projectId: "proj-1",
      traceId: "trace-abc",
      name: "accuracy",
      value: 1.0,
    });

    const opts = mockFetch.mock.calls[0][1] as RequestInit;
    const headers = opts.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer sk-test");
    expect(headers["X-Evaris-Project-ID"]).toBe("proj-1");
  });
});
