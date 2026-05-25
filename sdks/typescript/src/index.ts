/**
 * etrace — AI agent tracing library (TypeScript).
 *
 * Zero-dep core. Everything is a span with a kind.
 * Pipeline: SpanProcessor.on_end(span) → SpanExporter.export([span])
 *
 * Usage:
 *   import * as etrace from "etrace";
 *   etrace.init();                       // In-memory (local dev)
 *   etrace.init({ exporters: [...] });   // Custom exporters
 *   etrace.init({ processors: [...] });  // Custom processors
 *
 *   const result = await etrace.trace("agent", async () => {
 *     return doWork();
 *   }, { kind: "agent" });
 */
import { AsyncLocalStorage } from "node:async_hooks";

import type { Span, TraceKind, TraceLevel, Usage, ContextOptions, ScoreOptions } from "./types.js";
import { InMemoryExporter } from "./exporter.js";
import type { SpanExporter } from "./exporter.js";
import { SimpleProcessor, MultiProcessor } from "./processor.js";
import type { SpanProcessor } from "./processor.js";
import { instrumentAll, uninstrumentAll } from "./instrumentation/index.js";
import { calculateCost } from "./pricing.js";

// ── Public re-exports ────────────────────────────────────────────────────────

export { SpanExportResult, InMemoryExporter, ConsoleExporter } from "./exporter.js";
export type { SpanExporter } from "./exporter.js";
export { SimpleProcessor, BatchProcessor, MultiProcessor } from "./processor.js";
export type { SpanProcessor } from "./processor.js";

// ── Global state ─────────────────────────────────────────────────────────────

let _initialized = false;
let _processor: SpanProcessor | null = null;
let _calcCosts = true;

/** Maximum attribute value length. Shared constant. */
export const MAX_ATTR_LEN = 100_000;

// ── Context propagation (AsyncLocalStorage) ──────────────────────────────────

const _spanStore = new AsyncLocalStorage<Span | null>();
const _ctxStore = new AsyncLocalStorage<ContextOptions>();

function _defaultCtx(): ContextOptions {
  return {
    userId: undefined,
    sessionId: undefined,
    conversationId: undefined,
    evalRunId: undefined,
    tags: undefined,
    version: undefined,
    release: undefined,
  };
}

export function setContext(options: ContextOptions): void {
  const cur = _ctxStore.getStore() ?? _defaultCtx();
  _ctxStore.enterWith({
    userId: options.userId ?? cur.userId,
    sessionId: options.sessionId ?? cur.sessionId,
    conversationId: options.conversationId ?? cur.conversationId,
    evalRunId: options.evalRunId ?? cur.evalRunId,
    tags: [...new Set([...(cur.tags ?? []), ...(options.tags ?? [])])],
    version: options.version ?? cur.version,
    release: options.release ?? cur.release,
  });
}

export function getContext(): ContextOptions {
  return _ctxStore.getStore() ?? _defaultCtx();
}

export function getCurrentSpan(): Span | null {
  return _spanStore.getStore() ?? null;
}

// ── init() ───────────────────────────────────────────────────────────────────

export interface InitConfig {
  exporters?: SpanExporter[];
  processors?: SpanProcessor[];
  calculateCosts?: boolean;
  autoInstrument?: { llm?: boolean };
  debug?: boolean;
  version?: string;
  release?: string;
}

export function init(config: InitConfig = {}): void {
  if (_initialized) return;

  _calcCosts = config.calculateCosts ?? true;

  // Build processor pipeline
  if (config.processors && config.processors.length > 0) {
    _processor =
      config.processors.length > 1 ? new MultiProcessor(config.processors) : config.processors[0];
  } else if (config.exporters && config.exporters.length > 0) {
    const procs = config.exporters.map((e) => new SimpleProcessor(e));
    _processor = procs.length > 1 ? new MultiProcessor(procs) : procs[0];
  } else {
    const mem = new InMemoryExporter();
    _processor = new SimpleProcessor(mem);
  }

  // Auto-instrument LLM providers
  if (config.autoInstrument?.llm !== false) {
    try {
      instrumentAll(_calcCosts);
    } catch (exc) {
      console.warn(`[etrace] Auto-instrumentation failed (non-fatal): ${exc}`);
    }
  }

  _initialized = true;
}

// ── trace() — the ONE primitive ──────────────────────────────────────────────

export interface TraceConfig {
  kind?: TraceKind;
  input?: unknown;
  model?: string;
  provider?: string;
  attributes?: Record<string, unknown>;
  tags?: string[];
  level?: TraceLevel;
  version?: string;
  release?: string;
  modelParameters?: Record<string, unknown>;
  promptId?: string;
}

// Overloads for sync vs async
export function trace<T>(name: string, fn: () => Promise<T>, config?: TraceConfig): Promise<T>;
export function trace<T>(name: string, fn: () => T, config?: TraceConfig): T;
export function trace<T>(
  name: string,
  fn: () => T | Promise<T>,
  config?: TraceConfig,
): T | Promise<T> {
  const kind = config?.kind ?? "custom";
  const parent = _spanStore.getStore() ?? null;
  const span = _createSpan(name, kind, config, parent);

  if (!_initialized || !_processor) {
    // Noop mode — still set up AsyncLocalStorage so getCurrentSpan() works
    return _spanStore.run(span, () => fn());
  }

  _processor.onStart(span);
  const start = performance.now();

  const finalize = (s: Span, err?: unknown): void => {
    if (err != null) _failSpan(s, err);
    else if (s.status === "unset") s.status = "ok";
    _finalizeSpan(s, start);
    _processor!.onEnd(s);
  };

  return _spanStore.run(span, () => {
    try {
      const result = fn();

      if (_isPromise(result)) {
        return result.then(
          (value) => {
            finalize(span);
            return value;
          },
          (err: unknown) => {
            finalize(span, err);
            throw err;
          },
        ) as T;
      }

      finalize(span);
      return result;
    } catch (err) {
      finalize(span, err);
      throw err;
    }
  });
}

// ── observe — decorator wrapper ──────────────────────────────────────────────

export function observe(config?: TraceConfig & { name?: string }) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return function <T extends (...args: any[]) => any>(
    fn: T,
    _context?: ClassMethodDecoratorContext,
  ): T {
    const traceName = config?.name ?? fn.name ?? config?.kind ?? "custom";
    const wrapped = function (this: unknown, ...args: unknown[]) {
      return trace(traceName, () => fn.apply(this, args), {
        ...config,
        input: config?.input ?? args,
      });
    };
    Object.defineProperty(wrapped, "name", { value: fn.name });
    return wrapped as T;
  };
}

// ── Convenience decorators ───────────────────────────────────────────────────

export const workflow = (c?: TraceConfig & { name?: string }) =>
  observe({ ...c, kind: "workflow" });
export const agent = (c?: TraceConfig & { name?: string }) => observe({ ...c, kind: "agent" });
export const step = (c?: TraceConfig & { name?: string }) => observe({ ...c, kind: "step" });
export const tool = (c?: TraceConfig & { name?: string }) => observe({ ...c, kind: "tool" });
export const llm = (c?: TraceConfig & { name?: string }) => observe({ ...c, kind: "llm" });
export const http = (c?: TraceConfig & { name?: string }) => observe({ ...c, kind: "http" });
export const retrieval = (c?: TraceConfig & { name?: string }) =>
  observe({ ...c, kind: "retrieval" });
export const reranker = (c?: TraceConfig & { name?: string }) =>
  observe({ ...c, kind: "reranker" });
export const embedding = (c?: TraceConfig & { name?: string }) =>
  observe({ ...c, kind: "embedding" });
export const sandbox = (c?: TraceConfig & { name?: string }) => observe({ ...c, kind: "sandbox" });
export const handoff = (c?: TraceConfig & { name?: string }) => observe({ ...c, kind: "handoff" });
export const approval = (c?: TraceConfig & { name?: string }) =>
  observe({ ...c, kind: "approval" });
export const guardrail = (c?: TraceConfig & { name?: string }) =>
  observe({ ...c, kind: "guardrail" });
export const evaluation = (c?: TraceConfig & { name?: string }) => observe({ ...c, kind: "eval" });
export const scorer = (c?: TraceConfig & { name?: string }) => observe({ ...c, kind: "scorer" });

// ── Span enrichment ──────────────────────────────────────────────────────────

export interface UsageInput {
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
  cachedTokens?: number;
  reasoningTokens?: number;
  model?: string;
}

/**
 * Calculate cost for a Usage object. Pure function — no span mutation.
 * Returns a NEW Usage with calculated_* and input/output/totalCost populated.
 */
export function calculateUsageCost(usage: Usage, model?: string | null): Usage {
  if (!model) return { ...usage };

  try {
    const costs = calculateCost(
      model,
      usage.input ?? 0,
      usage.output ?? 0,
      usage.cachedTokens ?? 0,
      usage.reasoningTokens ?? 0,
    );
    if (!costs) return { ...usage };

    return {
      ...usage,
      calculatedInputCost: costs.inputCost,
      calculatedOutputCost: costs.outputCost,
      calculatedTotalCost: costs.totalCost,
      inputCost: costs.inputCost,
      outputCost: costs.outputCost,
      totalCost: costs.totalCost,
    };
  } catch {
    return { ...usage };
  }
}

/**
 * Set token usage on the current span.
 *
 * When calculateCosts=true (default in init()), costs are auto-populated
 * by delegating to calculateUsageCost().
 */
export function setUsage(input: UsageInput = {}): Usage {
  const span = _spanStore.getStore();
  if (!span) return {};

  const inputTokens = input.inputTokens ?? 0;
  const outputTokens = input.outputTokens ?? 0;
  const totalTokens = input.totalTokens ?? inputTokens + outputTokens;

  const usage: Usage = {
    input: inputTokens,
    output: outputTokens,
    total: totalTokens,
    cachedTokens: input.cachedTokens,
    reasoningTokens: input.reasoningTokens,
  };

  span.usage = usage;
  if (input.model) span.model = input.model;

  // Auto-calculate cost when enabled
  if (_calcCosts) {
    const model = input.model ?? span.model;
    if (model) {
      span.usage = calculateUsageCost(usage, model);
    }
  }

  return span.usage;
}

/** Convenience: calculate cost on a span's existing usage, in place. */
export function calcSpanCost(span: Span): void {
  if (span.usage && span.model) {
    span.usage = calculateUsageCost(span.usage, span.model);
  }
}

export function setOutput(value: unknown): void {
  const span = _spanStore.getStore();
  if (span) span.output = value;
}

export function setError(message: string, errorType?: string): void {
  const span = _spanStore.getStore();
  if (span) {
    span.error = { message, type: errorType };
    span.status = "error";
  }
}

export function setAttribute(key: string, value: unknown): void {
  const span = _spanStore.getStore();
  if (span) {
    if (!span.attributes) span.attributes = {};
    span.attributes[key] = value;
  }
}

export function score(options: ScoreOptions): Record<string, unknown> {
  const span = _spanStore.getStore();
  const traceId = options.traceId ?? span?.traceId;
  if (!traceId) {
    throw new Error(
      "Cannot score: no traceId. Pass traceId to score() or call score() within a trace context.",
    );
  }

  if (span?.events) {
    span.events.push({
      name: "score",
      timestamp: new Date().toISOString(),
      attributes: { score_name: options.name, score_value: String(options.value) },
    });
  }

  return { traceId, name: options.name, value: options.value };
}

// ── Lifecycle ────────────────────────────────────────────────────────────────

export function flush(timeoutMs = 30_000): boolean {
  if (_processor) {
    try {
      return _processor.forceFlush(timeoutMs);
    } catch {
      return false;
    }
  }
  return true;
}

export function shutdown(): void {
  try {
    uninstrumentAll();
  } catch {
    /* best-effort */
  }
  try {
    _processor?.shutdown();
  } catch {
    /* best-effort */
  }
  _processor = null;
  _initialized = false;
}

export function isInitialized(): boolean {
  return _initialized;
}

// ── Internal helpers ─────────────────────────────────────────────────────────

function _createSpan(
  name: string,
  kind: TraceKind,
  config: TraceConfig | undefined,
  parent: Span | null,
): Span {
  const span: Span = {
    traceId: crypto.randomUUID().replace(/-/g, ""),
    spanId: crypto.randomUUID().replace(/-/g, "").slice(0, 16),
    name,
    kind,
    status: "unset",
    startedAt: new Date().toISOString(),
    model: config?.model,
    provider: config?.provider,
    input: config?.input,
    attributes: { ...(config?.attributes ?? {}) },
    events: [],
    tags: config?.tags ?? [],
  };

  if (parent) {
    span.traceId = parent.traceId;
    span.parentSpanId = parent.spanId;
  }

  // Context propagation
  const ctx = _ctxStore.getStore();
  if (ctx) {
    span.userId = ctx.userId;
    span.sessionId = ctx.sessionId;
    span.conversationId = ctx.conversationId;
    span.version = config?.version ?? ctx.version;
    span.release = config?.release ?? ctx.release;
  }

  if (config?.modelParameters) span.modelParameters = config.modelParameters;
  if (config?.promptId) span.promptId = config.promptId;
  if (config?.level) span.level = config.level;

  return span;
}

function _finalizeSpan(span: Span, startHr: number): void {
  span.endedAt = new Date().toISOString();
  span.durationNs = Math.round((performance.now() - startHr) * 1_000_000);
}

function _failSpan(span: Span, err: unknown): void {
  span.status = "error";
  span.error = {
    message: err instanceof Error ? err.message : String(err),
    type: (err as Error)?.constructor?.name,
  };
}

function _isPromise(v: unknown): v is Promise<unknown> {
  return (
    v !== null && typeof v === "object" && typeof (v as { then?: unknown }).then === "function"
  );
}
