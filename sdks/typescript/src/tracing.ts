/**
 * Generic run-based tracing for agent frameworks.
 *
 * RunTracker maps framework run_id / parent_run_id pairs to etrace spans
 * with correct parent-child nesting. Framework adapters translate their
 * callback events into this small generic API.
 */
import type { Span, TraceKind, TraceStatus, Usage } from "./types.js";
import {
  _createSpan,
  _getCalcCosts,
  _getProcessor,
  _setCurrentSpan,
  calculateUsageCost,
  getCurrentSpan,
} from "./index.js";

export interface UsageMap {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cached_tokens?: number;
  reasoning_tokens?: number;
  model?: string;
}

export interface RunStartOptions {
  runId?: string;
  parentRunId?: string | null;
  kind?: TraceKind | string;
  input?: unknown;
  model?: string;
  provider?: string;
  attributes?: Record<string, unknown>;
}

export interface RunEndOptions {
  output?: unknown;
  status?: TraceStatus;
  usage?: UsageMap | null;
  model?: string;
  attributes?: Record<string, unknown>;
}

export class RunTracker {
  private readonly _runs = new Map<string, TrackedRun>();
  private _rootTraceId: string | null = null;
  private _rootParentSpanId: string | null = null;

  constructor() {
    const active = getCurrentSpan();
    if (active) {
      this._rootTraceId = active.traceId;
      this._rootParentSpanId = active.spanId;
    }
  }

  onRunStart(name: string, opts: RunStartOptions = {}): string {
    const rid = opts.runId ?? crypto.randomUUID().replace(/-/g, "");
    const previousSpan = getCurrentSpan();
    const span = _createSpan(
      name,
      coerceKind(opts.kind),
      {
        input: opts.input,
        model: opts.model,
        provider: opts.provider,
        attributes: opts.attributes,
      },
      null,
    );

    const parent = this._resolveParent(opts.parentRunId ?? null);
    if (parent) {
      span.traceId = parent.traceId;
      span.parentSpanId = parent.spanId;
    } else if (this._rootParentSpanId) {
      span.parentSpanId = this._rootParentSpanId;
      if (this._rootTraceId) span.traceId = this._rootTraceId;
    } else if (this._rootTraceId) {
      span.traceId = this._rootTraceId;
    }

    if (this._rootTraceId === null) {
      this._rootTraceId = span.traceId;
    }

    _setCurrentSpan(span);
    this._runs.set(rid, {
      span,
      start: performance.now(),
      parentRunId: opts.parentRunId ?? null,
      previousSpan,
    });

    _getProcessor()?.onStart(span);
    return rid;
  }

  skipRun(runId: string, parentRunId?: string | null): void {
    this._runs.set(runId, {
      span: null,
      start: 0,
      parentRunId: parentRunId ?? null,
      previousSpan: getCurrentSpan(),
    });
  }

  onRunEnd(runId: string, opts: RunEndOptions = {}): void {
    const run = this._runs.get(runId);
    if (!run?.span) return;

    const span = run.span;
    if (opts.output !== undefined) span.output = opts.output;
    if (opts.model) span.model = opts.model;
    span.status = opts.status ?? "ok";
    if (opts.attributes) {
      span.attributes ??= {};
      Object.assign(span.attributes, opts.attributes);
    }
    if (opts.usage) this._applyUsage(span, opts.usage);

    span.endedAt = new Date().toISOString();
    span.durationNs = Math.round((performance.now() - run.start) * 1_000_000);

    _setCurrentSpan(run.previousSpan);
    _getProcessor()?.onEnd(span);
  }

  onRunError(runId: string, error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    this.onRunEnd(runId, {
      output: message.slice(0, 100_000),
      status: "error",
      attributes: {
        "error.message": message.slice(0, 1000),
        "error.type": error instanceof Error ? error.constructor.name : typeof error,
      },
    });
  }

  flush(): void {
    for (const [runId, run] of this._runs) {
      if (run.span?.status === "unset") this.onRunEnd(runId);
    }
  }

  get runs(): Map<string, TrackedRun> {
    return this._runs;
  }

  private _resolveParent(runId: string | null): Span | null {
    const visited = new Set<string>();
    let current = runId;
    while (current && !visited.has(current)) {
      visited.add(current);
      const run = this._runs.get(current);
      if (!run) return null;
      if (run.span) return run.span;
      current = run.parentRunId;
    }
    return null;
  }

  private _applyUsage(span: Span, usage: UsageMap): void {
    const prompt = usage.prompt_tokens ?? 0;
    const completion = usage.completion_tokens ?? 0;
    const total = usage.total_tokens ?? prompt + completion;
    const cached = usage.cached_tokens ?? 0;
    const reasoning = usage.reasoning_tokens ?? 0;

    span.attributes ??= {};
    span.attributes["gen_ai.usage.prompt_tokens"] = prompt;
    span.attributes["gen_ai.usage.completion_tokens"] = completion;
    span.attributes["gen_ai.usage.total_tokens"] = total;
    if (cached) span.attributes["gen_ai.usage.cache_read_tokens"] = cached;
    if (reasoning) span.attributes["gen_ai.usage.reasoning_tokens"] = reasoning;

    const spanUsage: Usage = {
      input: prompt,
      output: completion,
      total,
      cachedTokens: cached,
      reasoningTokens: reasoning,
    };
    const model = usage.model ?? span.model;
    span.usage = _getCalcCosts() && model ? calculateUsageCost(spanUsage, model) : spanUsage;
  }
}

export interface TrackedRun {
  span: Span | null;
  start: number;
  parentRunId: string | null;
  previousSpan: Span | null;
}

function coerceKind(kind: TraceKind | string | undefined): TraceKind {
  const value = (kind ?? "custom").toLowerCase();
  const known: TraceKind[] = [
    "workflow",
    "agent",
    "step",
    "llm",
    "tool",
    "http",
    "retrieval",
    "reranker",
    "embedding",
    "sandbox",
    "handoff",
    "approval",
    "guardrail",
    "eval",
    "scorer",
    "custom",
  ];
  return known.includes(value as TraceKind) ? (value as TraceKind) : "custom";
}
