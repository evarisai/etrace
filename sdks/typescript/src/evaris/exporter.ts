/**
 * EvarisExporter — sends etrace spans to the Evaris backend via HTTP.
 *
 * Zero-dep (uses Node 18+ built-in fetch).
 */
import type { Span, Usage } from "../types.js";
import { SpanExportResult } from "../exporter.js";
import { MAX_ATTR_LEN } from "../index.js";

export const DEFAULT_ENDPOINT = "https://runtime.evaris.ai/v1/traces";

function _truncate(value: unknown): unknown {
  if (typeof value === "string" && value.length > MAX_ATTR_LEN) return value.slice(0, MAX_ATTR_LEN);
  return value;
}

function spanToDict(span: Span): Record<string, unknown> {
  const data: Record<string, unknown> = {
    trace_id: span.traceId,
    span_id: span.spanId,
    name: span.name,
    kind: span.kind,
    status: span.status,
    started_at: span.startedAt,
    ended_at: span.endedAt,
    duration_ns: span.durationNs,
  };

  if (span.parentSpanId) data.parent_span_id = span.parentSpanId;
  if (span.input != null) data.input = _truncate(span.input);
  if (span.output != null) data.output = _truncate(span.output);
  if (span.model) data.model = span.model;
  if (span.provider) data.provider = span.provider;
  if (span.tags?.length) data.tags = span.tags;
  if (span.attributes) data.attributes = span.attributes;
  if (span.usage) data.usage = usageToDict(span.usage);
  if (span.error) data.error = { message: span.error.message, type: span.error.type };
  if (span.userId) data.user_id = span.userId;
  if (span.sessionId) data.session_id = span.sessionId;
  if (span.conversationId) data.conversation_id = span.conversationId;
  if (span.modelParameters) data.model_parameters = span.modelParameters;

  return data;
}

function usageToDict(u: Usage): Record<string, unknown> {
  const d: Record<string, unknown> = {
    input: u.input,
    output: u.output,
    total: u.total,
  };
  if (u.inputCost != null) d.input_cost = u.inputCost;
  if (u.outputCost != null) d.output_cost = u.outputCost;
  if (u.totalCost != null) d.total_cost = u.totalCost;
  return d;
}

export class EvarisExporter {
  private readonly _apiKey: string;
  private readonly _projectId: string;
  private readonly _endpoint: string;

  constructor(opts: { apiKey: string; projectId: string; endpoint?: string }) {
    this._apiKey = opts.apiKey;
    this._projectId = opts.projectId;
    this._endpoint = opts.endpoint ?? DEFAULT_ENDPOINT;
  }

  async export(spans: Span[]): Promise<SpanExportResult> {
    try {
      const payload = spans.map(spanToDict);
      const resp = await fetch(this._endpoint, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this._apiKey}`,
          "X-Evaris-Project-ID": this._projectId,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        console.warn(`[etrace] EvarisExporter got ${resp.status}: ${resp.statusText}`);
        return SpanExportResult.FAILED;
      }
      return SpanExportResult.SUCCESS;
    } catch (exc) {
      console.warn(`[etrace] EvarisExporter export failed: ${exc}`);
      return SpanExportResult.FAILED;
    }
  }

  shutdown(): void {}

  forceFlush(): boolean {
    return true;
  }
}
