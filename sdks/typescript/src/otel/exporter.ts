/**
 * OtelExporter — bridges etrace Span → OTel ReadableSpan → standard OTel SpanExporter.
 *
 * Optional dependency: requires @opentelemetry/sdk-trace-base.
 * Install with: npm install etrace @opentelemetry/sdk-trace-base
 */
import { createRequire } from "node:module";
import type { Span, Usage } from "../types.js";
import { MAX_ATTR_LEN } from "../index.js";
import type { SpanExporter } from "../exporter.js";
import { SpanExportResult } from "../exporter.js";

const _require = createRequire(import.meta.url);

function _truncate(s: string): string {
  return s.length > MAX_ATTR_LEN ? s.slice(0, MAX_ATTR_LEN) : s;
}

function hexToInt(hex: string, expectedLen: number): string {
  return hex.slice(0, expectedLen).padEnd(expectedLen, "0");
}

function isoToHrTime(isoStr: string | undefined): [number, number] | undefined {
  if (!isoStr) return undefined;
  try {
    const ms = new Date(isoStr).getTime();
    const sec = Math.floor(ms / 1000);
    const nano = (ms % 1000) * 1_000_000;
    return [sec, nano];
  } catch {
    return undefined;
  }
}

interface OtelStatus {
  code: number;
  message?: string;
}

function statusToOtel(status: string | undefined): OtelStatus {
  const { SpanStatusCode } = _require("@opentelemetry/api");
  if (status === "ok") return { code: SpanStatusCode.OK };
  if (status === "error") return { code: SpanStatusCode.ERROR };
  return { code: SpanStatusCode.UNSET };
}

function spanToAttributes(span: Span): Record<string, unknown> {
  const attrs: Record<string, unknown> = {};
  attrs["etrace.kind"] = span.kind;

  if (span.model) attrs["gen_ai.request.model"] = span.model;
  if (span.provider) attrs["gen_ai.system"] = span.provider;

  if (span.usage) {
    const u: Usage = span.usage;
    attrs["gen_ai.usage.prompt_tokens"] = u.input ?? 0;
    attrs["gen_ai.usage.completion_tokens"] = u.output ?? 0;
    attrs["gen_ai.usage.total_tokens"] = u.total ?? (u.input ?? 0) + (u.output ?? 0);
    if (u.cachedTokens) attrs["gen_ai.usage.cache_read_tokens"] = u.cachedTokens;
    if (u.reasoningTokens) attrs["gen_ai.usage.reasoning_tokens"] = u.reasoningTokens;
    if (u.totalCost) attrs["gen_ai.usage.cost"] = u.totalCost;
  }

  if (span.input != null) attrs["etrace.input"] = _truncate(String(span.input));
  if (span.output != null) attrs["etrace.output"] = _truncate(String(span.output));
  if (span.tags?.length) attrs["etrace.tags"] = span.tags.join(",");
  if (span.userId) attrs["etrace.user_id"] = span.userId;
  if (span.sessionId) attrs["etrace.session_id"] = span.sessionId;
  if (span.conversationId) attrs["etrace.conversation_id"] = span.conversationId;

  if (span.attributes) Object.assign(attrs, span.attributes);
  return attrs;
}

// ── Adapter: wraps etrace Span as OTel ReadableSpan ──────────────────────────

function etraceToOtelSpan(span: Span): unknown {
  const { TraceFlags, SpanKind } = _require("@opentelemetry/api");
  const { resourceFromAttributes } = _require("@opentelemetry/resources");

  const startTime = isoToHrTime(span.startedAt) ?? [0, 0];
  const endTime = isoToHrTime(span.endedAt) ?? [0, 0];
  const ns = span.durationNs ?? 0;
  const duration: [number, number] = [Math.floor(ns / 1e9), ns % 1e9];

  const status = statusToOtel(span.status);
  if (span.error?.message && status.code !== 0) {
    status.message = span.error.message;
  }

  const events = (span.events ?? []).map((e) => ({
    name: e.name,
    time: isoToHrTime(e.timestamp) ?? [0, 0],
    attributes: e.attributes ?? {},
    droppedAttributesCount: 0,
  }));

  const links = (span.links ?? []).map((l) => ({
    context: {
      traceId: hexToInt(l.traceId, 32),
      spanId: hexToInt(l.spanId, 16),
      traceFlags: TraceFlags.SAMPLED,
      isRemote: false,
    },
    attributes: l.attributes ?? {},
    droppedAttributesCount: 0,
  }));

  return {
    name: span.name,
    kind: SpanKind.INTERNAL,
    parentSpanId: span.parentSpanId,
    ended: span.endedAt != null,
    startTime,
    endTime,
    duration,
    status,
    attributes: spanToAttributes(span),
    events,
    links,
    resource: resourceFromAttributes({}),
    instrumentationScope: { name: "etrace", version: "0.2.0" },
    droppedAttributesCount: 0,
    droppedEventsCount: 0,
    droppedLinksCount: 0,
    spanContext: () => ({
      traceId: hexToInt(span.traceId, 32),
      spanId: hexToInt(span.spanId, 16),
      traceFlags: TraceFlags.SAMPLED,
      isRemote: false,
    }),
  };
}

// ── OtelExporter ─────────────────────────────────────────────────────────────

export class OtelExporter implements SpanExporter {
  private readonly _exporter: unknown;

  constructor(otelExporter?: unknown) {
    if (otelExporter) {
      this._exporter = otelExporter;
    } else {
      this._exporter = this._createDefaultOtlpExporter();
    }
  }

  private _createDefaultOtlpExporter(): unknown {
    try {
      const { OTLPTraceExporter } = _require("@opentelemetry/exporter-trace-otlp-http") as {
        OTLPTraceExporter: new () => unknown;
      };
      return new OTLPTraceExporter();
    } catch {
      throw new Error(
        "No OTel exporter provided and @opentelemetry/exporter-trace-otlp-http not installed. " +
          "Install it or pass an OTel SpanExporter to OtelExporter().",
      );
    }
  }

  export(spans: Span[]): SpanExportResult {
    try {
      const otelSpans = spans.map(etraceToOtelSpan);
      const exp = this._exporter as { export(spans: unknown[], cb: (r: unknown) => void): unknown };
      const result = exp.export(otelSpans, () => {});
      // OTel SDK may return { code: number } or invoke callback
      if (typeof result === "object" && result !== null && "code" in result) {
        return (result as { code: number }).code === 0
          ? SpanExportResult.SUCCESS
          : SpanExportResult.FAILED;
      }
      return SpanExportResult.SUCCESS;
    } catch (exc) {
      console.warn(`[etrace] OtelExporter export failed: ${exc}`);
      return SpanExportResult.FAILED;
    }
  }

  shutdown(): void {
    (this._exporter as { shutdown(): void }).shutdown();
  }

  forceFlush(_timeoutMs?: number): boolean {
    const exp = this._exporter as { forceFlush?(...args: unknown[]): unknown };
    if (typeof exp.forceFlush === "function") {
      const result = exp.forceFlush();
      if (result instanceof Promise) {
        result.catch((e: unknown) => {
          console.warn(`[etrace] OtelExporter forceFlush failed: ${e}`);
        });
      }
      return true;
    }
    return true;
  }
}
