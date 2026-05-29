# etrace

AI agent tracing library. Auto-instruments LLM calls, calculates costs, classifies HTTP traffic, exports via OTLP.

**One line to init. One primitive to trace. Everything else is automatic.**

## Quick Start (Python)

```python
import etrace

etrace.init(api_key="...", project_id="...")

# LLM calls (OpenAI, Anthropic, etc.) are now auto-traced.
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(model="gpt-4o", messages=[...])
# ^ Auto-traced with kind=llm, tokens, cost calculated.

# Trace anything else with decorators.
@etrace.tool
def search(query: str) -> list:
    return web_search(query)

@etrace.retrieval
async def embed(texts: list[str]) -> list:
    return embedding_model.embed(texts)

# Or the trace() context manager.
with etrace.trace("pipeline", kind="workflow") as span:
    result = run_pipeline()
    span.output = result
```

## Quick Start (TypeScript)

```typescript
import { init, trace, tool } from "etrace";

init({ apiKey: "...", projectId: "..." });

// Decorate functions.
@tool()
async function search(query: string) { ... }

// Or trace explicitly.
const result = await trace("pipeline", async () => {
  return runPipeline();
}, { kind: "workflow" });
```

## Cost Tracking

Costs are auto-calculated from a bundled pricing catalog (sourced from [models.dev](https://github.com/anomalyco/models.dev), 1700+ models, 100+ providers).

```python
# Manual cost calculation.
from etrace._pricing import calculate_cost
cost = calculate_cost("gpt-4o", input_tokens=1000, output_tokens=500)
# → {"input_cost": 0.0025, "output_cost": 0.005, "total_cost": 0.0075}

# Auto-calculated when you set usage on a span.
with etrace.trace("llm-call", kind="llm", model="gpt-4o") as span:
    result = call_llm()
    etrace.set_usage(input_tokens=1000, output_tokens=500, model="gpt-4o")
    # Cost is auto-calculated and written to OTel attributes.
```

Update pricing catalog:
```bash
python scripts/sync_pricing.py
```

## Trace Kinds (16)

| Kind | What | Auto-instrumented? |
|---|---|---|
| `workflow` | Top-level pipeline | Manual (`@workflow`) |
| `agent` | Agent loop | Manual (`@agent`) |
| `step` | Discrete step in pipeline | Manual (`@step`) |
| `llm` | LLM API call | Automatic |
| `tool` | Tool/function call | Manual (`@tool`) |
| `http` | Outbound HTTP request | OTel HTTP instrumentors |
| `retrieval` | Vector DB / search | Manual (`@retrieval`) |
| `reranker` | Reranking results | Manual (`@reranker`) |
| `embedding` | Embedding generation | Automatic |
| `sandbox` | Code execution (Docker/E2B) | Manual (`@sandbox`) |
| `handoff` | Agent-to-agent delegation | Manual (`@handoff`) |
| `approval` | Human approval/rejection | Manual (`@approval`) |
| `guardrail` | Safety/validation check | Manual (`@guardrail`) |
| `eval` | Evaluation run | Manual (`@evaluation`) |
| `scorer` | Individual scorer execution | Manual (`@scorer`) |
| `custom` | Catch-all | Manual (`@observe`) |

## Architecture

```
trace/
├── schema/trace-schema.json      # Single source of truth (JSON Schema)
├── codegen.py                     # Schema → Python types + TypeScript types
├── scripts/sync_pricing.py        # models.dev → pricing catalogs
└── sdks/
    ├── python/src/etrace/
    │   ├── __init__.py            # Runtime: init(), trace(), @observe, set_usage()
    │   ├── _types.py              # [codegen'd] TraceKind, Span, Usage, etc.
    │   └── _pricing.py            # [generated] 1700+ model pricing catalog
    └── typescript/src/
        ├── index.ts               # Runtime: init(), trace(), @observe, setUsage()
        ├── types.ts               # [codegen'd] TraceKind, Span, Usage, etc.
        └── pricing.ts             # [generated] 1700+ model pricing catalog
```

**What's codegen'd:** Types (enums, interfaces, dataclasses).
**What's hand-written:** Runtime (context propagation, decorators, cost calculation, OTel bridge).

## The Problem This Solves

Current AI tracing has three gaps:

1. **No cost tracking.** LLM instrumentors capture tokens but never look up pricing. You get token counts but not dollars. We bundle a pricing catalog and auto-calculate.

2. **No classification of non-LLM spans.** OTel HTTP instrumentors emit spans with `SPAN_KIND=CLIENT` but no semantic kind. Tool calls, sandbox executions, and agent handoffs are all just "spans." We give every span a `kind` that means something.

3. **Complex setup.** Most tracing libraries need pages of config. We do `init()` — that's it. LLM calls are auto-traced. Costs are auto-calculated. HTTP calls are auto-classified.

## Install

```bash
# Python
pip install etrace[all]

# TypeScript
npm install etrace
```
