# etrace

AI agent tracing library. One primitive — `trace`. Everything else is automatic.

## Quick Start

### Python

```python
import etrace

etrace.init()  # In-memory (local dev)

# Trace anything.
with etrace.trace("agent", kind="agent", input={"q": "weather today"}) as span:
    result = run_agent()
    span.output = result

# Decorate functions — auto-captures input/output.
@etrace.agent
def my_agent(query: str) -> str:
    return llm_call(query)

@etrace.tool
def search(query: str) -> list:
    return web_search(query)

# Or use @observe as the universal decorator.
@etrace.observe(kind="custom")
def my_step(x: int) -> int:
    return x * 2
```

### TypeScript

```typescript
import { init, trace, agent, tool, observe } from "etrace";

init(); // In-memory (local dev)

// Trace anything.
const result = await trace("agent", async () => runAgent(), {
  kind: "agent",
  input: { q: "weather today" },
});

// Decorate functions.
const search = tool((query: string) => webSearch(query));
const myAgent = agent(async (query: string) => llmCall(query));

// Universal decorator.
const myStep = observe((x: number) => x * 2);
```

## Sending to Studio

Install the OTel extra, set the endpoint, and init with the OTel exporter:

```python
# Python
pip install "etrace[otel]"

import os
os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = "http://localhost:3001/v1/traces"

import etrace
from etrace.otel import OtelExporter
etrace.init(exporters=[OtelExporter()])
```

```typescript
// TypeScript
npm install etrace

process.env.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT = "http://localhost:3001/v1/traces";

import { init } from "etrace";
import { OtelExporter } from "etrace/otel";
init({ exporters: [new OtelExporter()] });
```

## Cost Tracking

Costs are auto-calculated from a bundled pricing catalog (1700+ models, 100+ providers).

```python
# Manual cost calculation.
cost = etrace.calculate_usage_cost(
    etrace.Usage(input=1000, output=500),
    model="gpt-4o",
)
# → input_cost=0.0025, output_cost=0.005, total_cost=0.0075

# Auto-calculated when usage is set on a span.
with etrace.trace("llm-call", kind="llm", model="gpt-4o") as span:
    result = call_llm()
    etrace.set_usage(input_tokens=1000, output_tokens=500)
    # Cost auto-populated on span.usage
```

Update pricing catalog:
```bash
python scripts/sync_pricing.py
```

## Auto-Instrumentation

When provider packages are installed, LLM calls are automatically traced:

```python
etrace.init()  # auto_instrument={"llm": True} by default

# OpenAI / Anthropic calls are now auto-traced.
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(model="gpt-4o", messages=[...])
# → Auto-traced with kind=llm, tokens, cost calculated
```

Disable with `etrace.init(auto_instrument={"llm": False})`.

## Span Kinds (16)

| Kind | Decorator | Description |
|---|---|---|
| `workflow` | `@etrace.workflow` | Top-level pipeline |
| `agent` | `@etrace.agent` | Agent loop |
| `step` | `@etrace.step` | Discrete step in pipeline |
| `llm` | `@etrace.llm` | LLM API call (auto-instrumented) |
| `tool` | `@etrace.tool` | Tool/function call |
| `http` | `@etrace.http` | Outbound HTTP request |
| `retrieval` | `@etrace.retrieval` | Vector DB / search |
| `reranker` | `@etrace.reranker` | Reranking results |
| `embedding` | `@etrace.embedding` | Embedding generation |
| `sandbox` | `@etrace.sandbox` | Code execution (Docker/E2B) |
| `handoff` | `@etrace.handoff` | Agent-to-agent delegation |
| `approval` | `@etrace.approval` | Human approval/rejection |
| `guardrail` | `@etrace.guardrail` | Safety/validation check |
| `eval` | `@etrace.evaluation` | Evaluation run |
| `scorer` | `@etrace.scorer` | Individual scorer execution |
| `custom` | `@etrace.observe` | Catch-all |

## Install

```bash
# Python (zero-dep core)
pip install etrace

# Python (with OTLP export)
pip install "etrace[otel]"

# TypeScript
npm install etrace
```

## What Makes This Different

- **Semantic classification.** Every span gets a `kind` that means something in AI workloads.
- **Zero-config local dev.** `init()` — that's it. In-memory exporter by default.
- **Cost tracking.** Token counts + pricing catalog = dollars. Auto-calculated.
- **Framework adapters.** LangChain callback handler out of the box.
- **CodeGen'd types.** JSON Schema → Python dataclasses + TypeScript
interfaces. Easily expanded to other languages.

## License

MIT
