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
import { createRequire } from "node:module";

import type { Span, TraceKind, TraceLevel, Usage, ContextOptions, ScoreOptions } from "./types.js";
import { InMemoryExporter } from "./exporter.js";
import type { SpanExporter } from "./exporter.js";
import type { MaybePromise } from "./exporter.js";
import { SimpleProcessor, MultiProcessor } from "./processor.js";
import type { SpanProcessor } from "./processor.js";
import { instrumentAll, uninstrumentAll } from "./instrumentation/index.js";
import { calculateCost } from "./pricing.js";
import { EtraceLangChainHandler, langchainHandler } from "./langchain.js";

const _require = createRequire(import.meta.url);

// ── Public re-exports ────────────────────────────────────────────────────────

export { SpanExportResult, InMemoryExporter, ConsoleExporter } from "./exporter.js";
export type { SpanExporter } from "./exporter.js";
export { SimpleProcessor, BatchProcessor, MultiProcessor } from "./processor.js";
export type { SpanProcessor } from "./processor.js";
export { RunTracker } from "./tracing.js";
export { EtraceLangChainHandler, langchainHandler };
export type { UsageMap } from "./tracing.js";

// ── Global state ─────────────────────────────────────────────────────────────

let _initialized = false;
let _processor: SpanProcessor | null = null;
let _calcCosts = true;

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
  autoInstrument?: { llm?: boolean; langchain?: boolean };
  debug?: boolean;
  version?: string;
  release?: string;
}

let _exitRegistered = false;

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

  const autoInstrument = config.autoInstrument ?? { llm: true, langchain: true };

  // Prefer callback-based framework tracing when that integration is present.
  if (autoInstrument.langchain !== false && _hasModule("@langchain/core")) {
    if (autoInstrument.llm !== false) {
      if (config.debug) {
        console.info("[etrace] Callback integration detected; disabling LLM auto-instrumentation");
      }
      autoInstrument.llm = false;
    }
  }

  // Auto-instrument LLM providers
  if (autoInstrument.llm !== false) {
    try {
      instrumentAll(_calcCosts);
    } catch (exc) {
      console.warn(`[etrace] Auto-instrumentation failed (non-fatal): ${exc}`);
    }
  }

  _initialized = true;

  // Auto-shutdown on process exit (like Python's atexit)
  if (!_exitRegistered) {
    _exitRegistered = true;
    const onExit = () => {
      try {
        uninstrumentAll();
      } catch {
        /* best-effort */
      }
      try {
        _processor?.forceFlush();
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
    };
    process.on("exit", onExit);
    process.on("SIGINT", () => {
      onExit();
      process.exit(0);
    });
    process.on("SIGTERM", () => {
      onExit();
      process.exit(0);
    });
  }
}

// ── trace() — the ONE primitive ──────────────────────────────────────────────

export interface TraceConfig {
  kind?: TraceKind;
  input?: unknown;
  captureInput?: boolean;
  captureOutput?: boolean;
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
            if (config?.captureOutput !== false && span.output === undefined) {
              span.output = value;
            }
            finalize(span);
            return value;
          },
          (err: unknown) => {
            finalize(span, err);
            throw err;
          },
        ) as T;
      }

      if (config?.captureOutput !== false && span.output === undefined) {
        span.output = result;
      }
      finalize(span);
      return result;
    } catch (err) {
      finalize(span, err);
      throw err;
    }
  });
}

// ── observe — decorator/function wrapper ────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyFn = (...args: any[]) => any;
type ObserveConfig = TraceConfig & { name?: string };
type ObserveDecorator = <T extends AnyFn>(fn: T) => T;

export function observe<T extends AnyFn>(fn: T): T;
export function observe(config?: ObserveConfig): ObserveDecorator;
export function observe(arg?: ObserveConfig | AnyFn): TOrDecorator {
  if (typeof arg === "function") return _wrapObserved(arg, {});
  return <T extends AnyFn>(fn: T) => _wrapObserved(fn, arg ?? {});
}

type TOrDecorator = ((fn: AnyFn) => AnyFn) | AnyFn;

function _wrapObserved(fn: AnyFn, config: ObserveConfig = {}): AnyFn {
  const name = config.name ?? fn.name ?? "anonymous";
  const kind = config.kind ?? "custom";
  const captureInput = config.captureInput !== false;

  return function (this: unknown, ...args: unknown[]) {
    const input = captureInput ? _captureArgs(fn, args) : undefined;
    return trace(name, () => fn.apply(this, args), {
      ...config,
      kind,
      input,
    });
  };
}

function _observeKind(kind: TraceKind, arg: ObserveConfig | AnyFn | undefined): TOrDecorator {
  if (typeof arg === "function") return _wrapObserved(arg, { kind });
  return <T extends AnyFn>(fn: T) => _wrapObserved(fn, { ...arg, kind });
}

// ── Convenience decorators ───────────────────────────────────────────────────

export function workflow<T extends AnyFn>(fn: T): T;
export function workflow(config?: ObserveConfig): ObserveDecorator;
export function workflow(arg?: ObserveConfig | AnyFn): TOrDecorator {
  return _observeKind("workflow", arg);
}

export function agent<T extends AnyFn>(fn: T): T;
export function agent(config?: ObserveConfig): ObserveDecorator;
export function agent(arg?: ObserveConfig | AnyFn): TOrDecorator {
  return _observeKind("agent", arg);
}

export function step<T extends AnyFn>(fn: T): T;
export function step(config?: ObserveConfig): ObserveDecorator;
export function step(arg?: ObserveConfig | AnyFn): TOrDecorator {
  return _observeKind("step", arg);
}

export function tool<T extends AnyFn>(fn: T): T;
export function tool(config?: ObserveConfig): ObserveDecorator;
export function tool(arg?: ObserveConfig | AnyFn): TOrDecorator {
  return _observeKind("tool", arg);
}

export function llm<T extends AnyFn>(fn: T): T;
export function llm(config?: ObserveConfig): ObserveDecorator;
export function llm(arg?: ObserveConfig | AnyFn): TOrDecorator {
  return _observeKind("llm", arg);
}

export function http<T extends AnyFn>(fn: T): T;
export function http(config?: ObserveConfig): ObserveDecorator;
export function http(arg?: ObserveConfig | AnyFn): TOrDecorator {
  return _observeKind("http", arg);
}

export function retrieval<T extends AnyFn>(fn: T): T;
export function retrieval(config?: ObserveConfig): ObserveDecorator;
export function retrieval(arg?: ObserveConfig | AnyFn): TOrDecorator {
  return _observeKind("retrieval", arg);
}

export function reranker<T extends AnyFn>(fn: T): T;
export function reranker(config?: ObserveConfig): ObserveDecorator;
export function reranker(arg?: ObserveConfig | AnyFn): TOrDecorator {
  return _observeKind("reranker", arg);
}

export function embedding<T extends AnyFn>(fn: T): T;
export function embedding(config?: ObserveConfig): ObserveDecorator;
export function embedding(arg?: ObserveConfig | AnyFn): TOrDecorator {
  return _observeKind("embedding", arg);
}

export function sandbox<T extends AnyFn>(fn: T): T;
export function sandbox(config?: ObserveConfig): ObserveDecorator;
export function sandbox(arg?: ObserveConfig | AnyFn): TOrDecorator {
  return _observeKind("sandbox", arg);
}

export function handoff<T extends AnyFn>(fn: T): T;
export function handoff(config?: ObserveConfig): ObserveDecorator;
export function handoff(arg?: ObserveConfig | AnyFn): TOrDecorator {
  return _observeKind("handoff", arg);
}

export function approval<T extends AnyFn>(fn: T): T;
export function approval(config?: ObserveConfig): ObserveDecorator;
export function approval(arg?: ObserveConfig | AnyFn): TOrDecorator {
  return _observeKind("approval", arg);
}

export function guardrail<T extends AnyFn>(fn: T): T;
export function guardrail(config?: ObserveConfig): ObserveDecorator;
export function guardrail(arg?: ObserveConfig | AnyFn): TOrDecorator {
  return _observeKind("guardrail", arg);
}

export function evaluation<T extends AnyFn>(fn: T): T;
export function evaluation(config?: ObserveConfig): ObserveDecorator;
export function evaluation(arg?: ObserveConfig | AnyFn): TOrDecorator {
  return _observeKind("eval", arg);
}

export function scorer<T extends AnyFn>(fn: T): T;
export function scorer(config?: ObserveConfig): ObserveDecorator;
export function scorer(arg?: ObserveConfig | AnyFn): TOrDecorator {
  return _observeKind("scorer", arg);
}

// ── Span enrichment ──────────────────────────────────────────────────────────

export interface UsageInput {
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
  cachedTokens?: number;
  reasoningTokens?: number;
  model?: string;
}

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

export function flush(timeoutMs = 30_000): MaybePromise<boolean> {
  if (_processor) {
    try {
      return _processor.forceFlush(timeoutMs);
    } catch {
      return false;
    }
  }
  return true;
}

export async function shutdown(): Promise<void> {
  const processor = _processor;
  _processor = null;
  _initialized = false;

  try {
    uninstrumentAll();
  } catch {
    /* best-effort */
  }
  try {
    await processor?.shutdown();
  } catch {
    /* best-effort */
  }
}

export function isInitialized(): boolean {
  return _initialized;
}

// ── Internal hooks for framework adapters ───────────────────────────────────

export function _getProcessor(): SpanProcessor | null {
  return _processor;
}

export function _getCalcCosts(): boolean {
  return _calcCosts;
}

export function _setCurrentSpan(span: Span | null): void {
  _spanStore.enterWith(span);
}

// ── Internal helpers ─────────────────────────────────────────────────────────

export function _createSpan(
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
    attributes: { "etrace.kind": kind, ...(config?.attributes ?? {}) },
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

function _hasModule(name: string): boolean {
  try {
    _require.resolve(name);
    return true;
  } catch {
    return false;
  }
}

function _captureArgs(fn: (...args: unknown[]) => unknown, args: unknown[]): unknown {
  const names = _parameterNames(fn);
  if (names.length === 0) return args.length === 1 ? args[0] : args;

  const captured: Record<string, unknown> = {};
  for (let i = 0; i < args.length; i += 1) {
    captured[names[i] ?? `arg${i}`] = _truncateLargeValue(args[i]);
  }
  return captured;
}

function _parameterNames(fn: (...args: unknown[]) => unknown): string[] {
  const source = Function.prototype.toString.call(fn).replace(/\s+/g, " ");
  const match = source.match(/^[^(]*\(([^)]*)\)/) ?? source.match(/^(?:async )?([^=()]+?)\s*=>/);
  if (!match?.[1]) return [];
  return match[1]
    .split(",")
    .map((part) => part.trim().replace(/=.*$/, "").trim())
    .filter((part) => /^[A-Za-z_$][\w$]*$/.test(part) && part !== "this");
}

function _truncateLargeValue(value: unknown): unknown {
  if (typeof value === "string") {
    return value.length > MAX_ATTR_LEN ? value.slice(0, MAX_ATTR_LEN) : value;
  }
  try {
    const serialized = JSON.stringify(value);
    if (serialized && serialized.length > MAX_ATTR_LEN) {
      return serialized.slice(0, MAX_ATTR_LEN);
    }
  } catch {
    return String(value).slice(0, MAX_ATTR_LEN);
  }
  return value;
}
