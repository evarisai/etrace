import type { Trace, Span } from "./types"

const NOW = Date.now()

function span(
  overrides: Partial<Span> & { id: string; name: string; trace_id: string }
): Span {
  const start = overrides.start_time ?? NOW - 5000
  const end = overrides.end_time ?? start + (overrides.duration_ms ?? 100)
  return {
    parent_span_id: null,
    kind: "INTERNAL",
    status: "OK",
    start_time: start,
    end_time: end,
    duration_ms: end - start,
    attributes: {},
    events: [],
    model: null,
    provider: null,
    input_tokens: null,
    output_tokens: null,
    total_cost: null,
    input_payload: null,
    output_payload: null,
    ...overrides,
  }
}

function tid(id: string) {
  return `trace-${id}`
}

function sid(trace: string, id: string) {
  return `${tid(trace)}-span-${id}`
}

// ── Trace 1: Agent run with tool calls ──────────────────────────

const trace1Spans: Span[] = [
  span({
    id: sid("1", "root"),
    trace_id: tid("1"),
    name: "research_agent",
    start_time: NOW - 5200,
    end_time: NOW - 200,
    duration_ms: 5000,
    attributes: { "etrace.kind": "trace" },
  }),
  span({
    id: sid("1", "llm1"),
    trace_id: tid("1"),
    parent_span_id: sid("1", "root"),
    name: "chat.completion",
    kind: "CLIENT",
    start_time: NOW - 5100,
    end_time: NOW - 3800,
    duration_ms: 1300,
    model: "gpt-4o",
    provider: "openai",
    input_tokens: 1247,
    output_tokens: 89,
    total_cost: 0.0082,
    attributes: {
      "gen_ai.system": "openai",
      "gen_ai.request.model": "gpt-4o",
    },
    input_payload: "Research the latest developments in quantum computing",
    output_payload:
      'I\'ll search for recent quantum computing news. Let me use the search tool.\n\n{"tool": "web_search", "query": "quantum computing 2025 developments"}',
  }),
  span({
    id: sid("1", "tool1"),
    trace_id: tid("1"),
    parent_span_id: sid("1", "root"),
    name: "web_search",
    kind: "CLIENT",
    start_time: NOW - 3700,
    end_time: NOW - 2900,
    duration_ms: 800,
    attributes: { tool: true },
    input_payload: '{"query": "quantum computing 2025 developments"}',
    output_payload:
      '{"results": ["IBM announces 1000-qubit processor", "Google achieves quantum error correction milestone", "New topological qubit design shows promise"]}',
  }),
  span({
    id: sid("1", "llm2"),
    trace_id: tid("1"),
    parent_span_id: sid("1", "root"),
    name: "chat.completion",
    kind: "CLIENT",
    start_time: NOW - 2800,
    end_time: NOW - 900,
    duration_ms: 1900,
    model: "gpt-4o",
    provider: "openai",
    input_tokens: 3421,
    output_tokens: 567,
    total_cost: 0.0213,
    attributes: {
      "gen_ai.system": "openai",
      "gen_ai.request.model": "gpt-4o",
    },
    input_payload:
      "Based on the search results, write a summary of quantum computing developments",
    output_payload:
      "## Quantum Computing Developments in 2025\n\n**IBM's 1000-Qubit Processor**\nIBM has achieved a major milestone with their latest processor, crossing the 1000-qubit threshold...\n\n**Google's Error Correction**\nGoogle's quantum team demonstrated a significant advance in quantum error correction...\n\n**Topological Qubits**\nResearchers have developed a new topological qubit design that shows promise for more stable quantum computation...",
  }),
  span({
    id: sid("1", "embed1"),
    trace_id: tid("1"),
    parent_span_id: sid("1", "root"),
    name: "embeddings.create",
    kind: "CLIENT",
    start_time: NOW - 800,
    end_time: NOW - 300,
    duration_ms: 500,
    model: "text-embedding-3-small",
    provider: "openai",
    input_tokens: 567,
    output_tokens: 0,
    total_cost: 0.0001,
    attributes: {
      "gen_ai.system": "openai",
      "gen_ai.request.model": "text-embedding-3-small",
    },
    input_payload: "Quantum Computing Developments in 2025...",
  }),
]

// ── Trace 2: Multi-step agent with error ────────────────────────

const trace2Spans: Span[] = [
  span({
    id: sid("2", "root"),
    trace_id: tid("2"),
    name: "code_agent",
    start_time: NOW - 12000,
    end_time: NOW - 1500,
    duration_ms: 10500,
    attributes: { "etrace.kind": "trace" },
  }),
  span({
    id: sid("2", "llm1"),
    trace_id: tid("2"),
    parent_span_id: sid("2", "root"),
    name: "chat.completion",
    kind: "CLIENT",
    start_time: NOW - 11900,
    end_time: NOW - 10200,
    duration_ms: 1700,
    model: "claude-sonnet-4-20250514",
    provider: "anthropic",
    input_tokens: 2100,
    output_tokens: 156,
    total_cost: 0.0147,
    attributes: {
      "gen_ai.system": "anthropic",
      "gen_ai.request.model": "claude-sonnet-4-20250514",
    },
    input_payload: "Fix the failing tests in the authentication module",
    output_payload:
      'I\'ll analyze the test failures. Let me first read the test file.\n\n{"tool": "read_file", "path": "tests/test_auth.py"}',
  }),
  span({
    id: sid("2", "tool1"),
    trace_id: tid("2"),
    parent_span_id: sid("2", "root"),
    name: "read_file",
    kind: "CLIENT",
    start_time: NOW - 10100,
    end_time: NOW - 9900,
    duration_ms: 200,
    attributes: { tool: true },
    input_payload: '{"path": "tests/test_auth.py"}',
    output_payload:
      "def test_login(): ...\ndef test_token_refresh(): ...\ndef test_password_reset(): ...",
  }),
  span({
    id: sid("2", "tool2"),
    trace_id: tid("2"),
    parent_span_id: sid("2", "root"),
    name: "write_file",
    kind: "CLIENT",
    start_time: NOW - 9800,
    end_time: NOW - 9500,
    duration_ms: 300,
    attributes: { tool: true },
    input_payload: '{"path": "src/auth.py", "content": "..."}',
    output_payload: "File written successfully",
  }),
  span({
    id: sid("2", "tool3"),
    trace_id: tid("2"),
    parent_span_id: sid("2", "root"),
    name: "run_command",
    kind: "CLIENT",
    start_time: NOW - 9400,
    end_time: NOW - 6500,
    duration_ms: 2900,
    attributes: { tool: true },
    input_payload: '{"command": "pytest tests/test_auth.py -v"}',
    output_payload:
      "FAILED test_auth.py::test_login - AssertionError\n2 passed, 1 failed",
  }),
  span({
    id: sid("2", "llm2"),
    trace_id: tid("2"),
    parent_span_id: sid("2", "root"),
    name: "chat.completion",
    kind: "CLIENT",
    start_time: NOW - 6400,
    end_time: NOW - 4200,
    duration_ms: 2200,
    model: "claude-sonnet-4-20250514",
    provider: "anthropic",
    input_tokens: 4500,
    output_tokens: 312,
    total_cost: 0.0312,
    attributes: {
      "gen_ai.system": "anthropic",
      "gen_ai.request.model": "claude-sonnet-4-20250514",
    },
    input_payload: "The test_login test is still failing. Fix the issue.",
    output_payload:
      "I see the issue — the login function needs to hash the password before comparing. Let me fix it.",
  }),
  span({
    id: sid("2", "tool4"),
    trace_id: tid("2"),
    parent_span_id: sid("2", "root"),
    name: "write_file",
    kind: "CLIENT",
    start_time: NOW - 4100,
    end_time: NOW - 3800,
    duration_ms: 300,
    status: "ERROR",
    attributes: { tool: true },
    input_payload: '{"path": "src/auth.py", "content": "..."}',
    output_payload: "Error: Permission denied — src/auth.py is read-only",
  }),
  span({
    id: sid("2", "llm3"),
    trace_id: tid("2"),
    parent_span_id: sid("2", "root"),
    name: "chat.completion",
    kind: "CLIENT",
    start_time: NOW - 3700,
    end_time: NOW - 1600,
    duration_ms: 2100,
    model: "claude-sonnet-4-20250514",
    provider: "anthropic",
    input_tokens: 5200,
    output_tokens: 445,
    total_cost: 0.0389,
    attributes: {
      "gen_ai.system": "anthropic",
      "gen_ai.request.model": "claude-sonnet-4-20250514",
    },
    input_payload:
      "The file is read-only. Try a different approach to fix the test.",
    output_payload:
      "I understand. Let me try fixing the test file instead to match the current implementation.\n\nActually, the issue is that the test expects plain text comparison but the implementation uses hashing. I'll update the test.",
  }),
]

// ── Trace 3: Simple LLM call ────────────────────────────────────

const trace3Spans: Span[] = [
  span({
    id: sid("3", "root"),
    trace_id: tid("3"),
    name: "summarize_text",
    start_time: NOW - 2500,
    end_time: NOW - 400,
    duration_ms: 2100,
    attributes: { "etrace.kind": "trace" },
  }),
  span({
    id: sid("3", "llm1"),
    trace_id: tid("3"),
    parent_span_id: sid("3", "root"),
    name: "chat.completion",
    kind: "CLIENT",
    start_time: NOW - 2400,
    end_time: NOW - 500,
    duration_ms: 1900,
    model: "gpt-4o-mini",
    provider: "openai",
    input_tokens: 8200,
    output_tokens: 340,
    total_cost: 0.0025,
    attributes: {
      "gen_ai.system": "openai",
      "gen_ai.request.model": "gpt-4o-mini",
    },
    input_payload: "Summarize the following document...",
    output_payload:
      "The document discusses the implementation of distributed tracing in microservices architectures. Key points include...",
  }),
]

// ── Trace 4: Running trace ──────────────────────────────────────

const trace4Spans: Span[] = [
  span({
    id: sid("4", "root"),
    trace_id: tid("4"),
    name: "data_pipeline",
    start_time: NOW - 3000,
    end_time: null,
    duration_ms: null,
    status: "RUNNING",
    attributes: { "etrace.kind": "trace" },
  }),
  span({
    id: sid("4", "llm1"),
    trace_id: tid("4"),
    parent_span_id: sid("4", "root"),
    name: "chat.completion",
    kind: "CLIENT",
    start_time: NOW - 2900,
    end_time: NOW - 1200,
    duration_ms: 1700,
    model: "glm-5.1",
    provider: "zhipu",
    input_tokens: 1500,
    output_tokens: 230,
    total_cost: 0.0031,
    attributes: {
      "gen_ai.system": "zhipu",
      "gen_ai.request.model": "glm-5.1",
    },
    input_payload: "Analyze the data schema...",
    output_payload:
      "The schema has 12 tables with foreign key relationships...",
  }),
  span({
    id: sid("4", "tool1"),
    trace_id: tid("4"),
    parent_span_id: sid("4", "root"),
    name: "execute_query",
    kind: "CLIENT",
    start_time: NOW - 1100,
    end_time: null,
    duration_ms: null,
    status: "RUNNING",
    attributes: { tool: true },
    input_payload: '{"sql": "SELECT * FROM users WHERE active = true"}',
  }),
]

// ── Build Trace objects ──────────────────────────────────────────

function buildTrace(
  id: string,
  name: string,
  spans: Span[],
  status?: "OK" | "ERROR" | "RUNNING"
): Trace {
  const rootSpan = spans.find((s) => s.parent_span_id === null)
  const totalInput = spans.reduce((sum, s) => sum + (s.input_tokens ?? 0), 0)
  const totalOutput = spans.reduce((sum, s) => sum + (s.output_tokens ?? 0), 0)
  const totalCost = spans.reduce((sum, s) => sum + (s.total_cost ?? 0), 0)
  const errorCount = spans.filter((s) => s.status === "ERROR").length
  const models = [...new Set(spans.map((s) => s.model).filter(Boolean))]

  return {
    id: tid(id),
    name,
    status:
      status ??
      (errorCount > 0
        ? "ERROR"
        : spans.some((s) => s.end_time === null)
          ? "RUNNING"
          : "OK"),
    start_time: rootSpan?.start_time ?? NOW,
    end_time: rootSpan?.end_time ?? null,
    duration_ms: rootSpan?.duration_ms ?? null,
    root_span_id: rootSpan?.id ?? "",
    spans,
    total_input_tokens: totalInput,
    total_output_tokens: totalOutput,
    total_cost: totalCost,
    model: models[0] ?? null,
    span_count: spans.length,
    error_count: errorCount,
  }
}

export const SEED_TRACES: Trace[] = [
  buildTrace("1", "Research Agent — Quantum Computing", trace1Spans),
  buildTrace("2", "Code Agent — Fix Auth Tests", trace2Spans),
  buildTrace("3", "Summarize Document", trace3Spans),
  buildTrace("4", "Data Pipeline", trace4Spans, "RUNNING"),
]
