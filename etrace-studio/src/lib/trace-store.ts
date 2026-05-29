import type { Span, Trace } from "./types"

export const TRACES: Trace[] = []

const MAX_TRACES = 500

export function ingestSpans(spans: Span[]): Trace[] {
  for (const span of spans) {
    const trace = TRACES.find((candidate) => candidate.id === span.trace_id)
    if (trace) {
      const index = trace.spans.findIndex(
        (candidate) => candidate.id === span.id
      )
      if (index >= 0) {
        trace.spans[index] = span
      } else {
        trace.spans.push(span)
      }
      refreshTrace(trace)
    } else {
      TRACES.unshift(createTrace(span.trace_id, [span]))
    }
  }

  TRACES.sort((a, b) => b.start_time - a.start_time)
  if (TRACES.length > MAX_TRACES) {
    TRACES.splice(MAX_TRACES)
  }
  return TRACES
}

export function deleteTrace(traceId: string): boolean {
  const index = TRACES.findIndex((trace) => trace.id === traceId)
  if (index < 0) return false
  TRACES.splice(index, 1)
  return true
}

export function clearTraces(): void {
  TRACES.splice(0, TRACES.length)
}

function createTrace(traceId: string, spans: Span[]): Trace {
  const trace: Trace = {
    id: traceId,
    name: "trace",
    status: "UNSET",
    start_time: Date.now(),
    end_time: null,
    duration_ms: null,
    root_span_id: spans[0]?.id ?? traceId,
    spans,
    total_input_tokens: 0,
    total_output_tokens: 0,
    total_cost: 0,
    model: null,
    span_count: 0,
    error_count: 0,
  }
  refreshTrace(trace)
  return trace
}

function refreshTrace(trace: Trace): void {
  trace.spans.sort((a, b) => a.start_time - b.start_time)

  const root =
    trace.spans.find((span) => span.parent_span_id === null) ?? trace.spans[0]
  trace.root_span_id = root?.id ?? trace.id
  trace.name = root?.name ?? "trace"
  trace.start_time = Math.min(...trace.spans.map((span) => span.start_time))

  const endTimes = trace.spans
    .map((span) => span.end_time)
    .filter((value): value is number => value !== null)
  trace.end_time =
    endTimes.length === trace.spans.length ? Math.max(...endTimes) : null
  trace.duration_ms =
    trace.end_time === null
      ? null
      : Math.max(0, trace.end_time - trace.start_time)

  trace.error_count = trace.spans.filter(
    (span) => span.status === "ERROR"
  ).length
  if (trace.error_count > 0) {
    trace.status = "ERROR"
  } else if (trace.spans.some((span) => span.end_time === null)) {
    trace.status = "RUNNING"
  } else if (trace.spans.some((span) => span.status === "OK")) {
    trace.status = "OK"
  } else {
    trace.status = "UNSET"
  }

  trace.total_input_tokens = sumNullable(
    trace.spans.map((span) => span.input_tokens)
  )
  trace.total_output_tokens = sumNullable(
    trace.spans.map((span) => span.output_tokens)
  )
  trace.total_cost = sumNullable(trace.spans.map((span) => span.total_cost))
  trace.model = trace.spans.find((span) => span.model)?.model ?? null
  trace.span_count = trace.spans.length
}

function sumNullable(values: Array<number | null>): number {
  return values.reduce<number>((sum, value) => sum + (value ?? 0), 0)
}
