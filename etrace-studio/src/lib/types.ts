export interface Span {
  id: string
  trace_id: string
  parent_span_id: string | null
  name: string
  kind: "INTERNAL" | "CLIENT" | "SERVER" | "PRODUCER" | "CONSUMER"
  status: "OK" | "ERROR" | "UNSET" | "RUNNING"
  start_time: number // unix ms
  end_time: number | null
  attributes: Record<string, unknown>
  events: SpanEvent[]
  // Computed
  duration_ms: number | null
  // LLM fields (from attributes)
  model: string | null
  provider: string | null
  input_tokens: number | null
  output_tokens: number | null
  total_cost: number | null
  input_payload: string | null
  output_payload: string | null
}

export interface SpanEvent {
  name: string
  timestamp: number
  attributes: Record<string, unknown>
}

export interface Trace {
  id: string
  name: string
  status: "OK" | "ERROR" | "RUNNING" | "UNSET"
  start_time: number
  end_time: number | null
  duration_ms: number | null
  root_span_id: string
  spans: Span[]
  // Aggregate stats
  total_input_tokens: number
  total_output_tokens: number
  total_cost: number
  model: string | null
  span_count: number
  error_count: number
}

export function spanKind(span: Span): "trace" | "llm" | "tool" | "other" {
  const name = span.name.toLowerCase()
  const attrs = span.attributes
  const etraceKind = attrs["etrace.kind"]
  if (
    etraceKind === "trace" ||
    (attrs["gen_ai.system"] === undefined && span.parent_span_id === null)
  ) {
    return "trace"
  }
  if (
    etraceKind === "llm" ||
    attrs["gen_ai.system"] ||
    attrs["llm"] ||
    name.includes("chat.completion") ||
    name.includes("generate") ||
    name.includes("embed")
  ) {
    return "llm"
  }
  if (
    etraceKind === "tool" ||
    attrs["tool"] ||
    name.includes("tool") ||
    name.includes("function")
  ) {
    return "tool"
  }
  return "other"
}
