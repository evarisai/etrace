/**
 * AUTO-GENERATED from trace-schema.json. Do not edit by hand.
 * Run: python codegen.py --typescript
 */

export type TraceKind =
  | "workflow"
  | "agent"
  | "step"
  | "llm"
  | "tool"
  | "http"
  | "retrieval"
  | "reranker"
  | "embedding"
  | "sandbox"
  | "handoff"
  | "approval"
  | "guardrail"
  | "eval"
  | "scorer"
  | "custom";

export type TraceStatus = "unset" | "ok" | "error";

export type TraceLevel = "debug" | "default" | "warning" | "error";

export type ScoreDataType = "numeric" | "boolean" | "categorical";

export type ScoreSource = "annotation" | "api" | "eval";

export type UsageUnit = "tokens" | "characters" | "images" | "steps";

export interface TraceError {
  message: string;
  type?: string;
  stack?: string;
}

export interface TraceEvent {
  name: string;
  timestamp: string;
  attributes?: Record<string, unknown>;
}

export interface TraceLink {
  traceId: string;
  spanId: string;
  attributes?: Record<string, unknown>;
}

/** Token usage with split cost tracking. */
export interface Usage {
  input?: number;
  output?: number;
  total?: number;
  unit?: UsageUnit;
  inputCost?: number;
  outputCost?: number;
  totalCost?: number;
  calculatedInputCost?: number;
  calculatedOutputCost?: number;
  calculatedTotalCost?: number;
  cachedTokens?: number;
  reasoningTokens?: number;
}

/** Streaming LLM performance metrics. */
export interface StreamingMetrics {
  completionStartTime?: string;
  tokensPerSecond?: number;
  timeToFirstTokenMs?: number;
}

/** A single traced operation. The ONE primitive. Everything is a span with a kind. */
export interface Span {
  traceId: string;
  spanId: string;
  parentSpanId?: string;
  name: string;
  kind: TraceKind;
  status?: TraceStatus;
  level?: TraceLevel;
  startedAt: string;
  endedAt?: string;
  durationNs?: number;
  input?: unknown;
  output?: unknown;
  error?: TraceError;
  attributes?: Record<string, unknown>;
  events?: TraceEvent[];
  links?: TraceLink[];
  tags?: string[];
  model?: string;
  provider?: string;
  modelParameters?: Record<string, unknown>;
  usage?: Usage;
  streaming?: StreamingMetrics;
  promptId?: string;
  userId?: string;
  sessionId?: string;
  conversationId?: string;
  version?: string;
  release?: string;
  environment?: "production" | "staging" | "development";
}

/** Options when creating a span. */
export interface SpanOptions {
  kind?: TraceKind;
  input?: unknown;
  attributes?: Record<string, unknown>;
  tags?: string[];
  level?: TraceLevel;
  model?: string;
  provider?: string;
  modelParameters?: Record<string, unknown>;
  promptId?: string;
  version?: string;
  release?: string;
  captureInput?: boolean;
  captureOutput?: boolean;
}

/** Context that propagates across all spans in a call chain. */
export interface ContextOptions {
  userId?: string;
  sessionId?: string;
  conversationId?: string;
  evalRunId?: string;
  tags?: string[];
  version?: string;
  release?: string;
}

export interface ScoreOptions {
  traceId?: string;
  spanId?: string;
  name: string;
  value?: unknown;
  dataType?: ScoreDataType;
  source?: ScoreSource;
  comment?: string;
  metadata?: Record<string, unknown>;
}

/** Options for initializing the tracing library. */
export interface InitOptions {
  apiKey?: string;
  projectId?: string;
  endpoint?: string;
  serviceName?: string;
  environment?: "production" | "staging" | "development";
  autoInstrument?: Record<string, unknown>;
  debug?: boolean;
  version?: string;
  release?: string;
}
