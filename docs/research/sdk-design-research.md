# SDK Design Research: Langfuse, LangSmith, OpenLLMetry vs etrace

## 1. How Each SDK Works

### 1.1 Langfuse (Python + TypeScript)

**Architecture**: OTel-backed spans under the hood, with a high-level observation API on top.

**Python API**:
```python
from langfuse import observe

# Decorator — auto-nests via contextvars
@observe(name="research_agent", as_type="agent")
def run_agent(query: str):
    results = search(query)    # auto-child
    return synthesize(results)  # auto-child

# Context manager
@observe(as_type="generation")
def call_llm(prompt):
    response = openai.chat.completions.create(...)
    response = openai.chat.completions.create(...)
    return response

# LangChain: Callback handler
from langfuse.langchain import CallbackHandler
handler = CallbackHandler()  # auto-discovers langfuse client
agent.invoke({"messages": [...]}, config={"callbacks": [handler]})

# OpenAI: Wrapper proxy
from langfuse import observeOpenAI
observed_client = observeOpenAI(openai_client)
observed_client.chat.completions.create(...)
```

**Key types**: `LangfuseSpan`, `LangfuseGeneration`, `LangfuseAgent`, `LangfuseTool`, `LangfuseChain`, `LangfuseRetriever`, `LangfuseEmbedding`, `LangfuseGuardrail`, `LangfuseEvaluator`

**`as_type` values**: `"span"` (default), `"generation"`, `"agent"`, `"tool"`, `"chain"`, `"retriever"`, `"embedding"`, `"evaluator"`, `"guardrail"`

**Nesting**: `@observe()` uses OTel context propagation. Child functions decorated with `@observe()` automatically become children. No manual parent passing needed.

**TS API**:
```typescript
import Langfuse from "langfuse";

// Low-level: trace → span/generation
const trace = langfuse.createTrace({ name: "my-trace" });
const span = trace.span({ name: "search", input: {...} });
span.end({ output: {...} });

// OpenAI wrapper
const observed = observeOpenAI(openaiClient, { traceName: "My Trace" });
observed.chat.completions.create({...});

// NO @observe decorator in TS (TS decorators are limited)
// NO LangChain callback handler in TS
```

**LangChain callback handler (Python only)**: `LangchainCallbackHandler` is a `BaseCallbackHandler` that:
- Maps ALL LangChain events → Langfuse observations
- `on_chain_start` → `LangfuseChain` (keeps all chains, no filtering)
- `on_chat_model_start` → `LangfuseGeneration` 
- `on_tool_start` → `LangfuseTool`
- `on_retriever_start` → `LangfuseRetriever`
- Maps `run_id`/`parent_run_id` to OTel parent span context
- Auto-detects agents from serialized class path (`"agent"` in class name)
- Handles LangGraph resume/interrupt flows
- ~1800 lines of code

---

### 1.2 LangSmith (Python + TypeScript)

**Architecture**: Own `RunTree` data model. NOT OTel-based. `RunTree` has `createChild()` and auto-POSTs to LangSmith API.

**Python API**:
```python
from langsmith import traceable, trace, get_current_run_tree

# Decorator — auto-nests via contextvars
@traceable(run_type="tool")
def search(query: str):
    return tavily.search(query)

@traceable(run_type="chain")  # default
def agent(query: str):
    result = search(query)  # auto-child via context
    return result

# Context manager
with trace("my_op", run_type="tool") as run:
    result = do_work()
    run.end(outputs={"result": result})

# LangChain: Built-in tracer (not a callback handler)
# LangChain natively sends to LangSmith via LangChainTracer
# Set LANGSMITH_API_KEY env var → automatic
```

**`run_type` values**: `"chain"` (default), `"llm"`, `"tool"`, `"retriever"`, `"embedding"`, `"prompt"`, `"parser"`

**Nesting**: `@traceable()` uses `_PARENT_RUN_TREE_REF` contextvar (weakref). Child `@traceable` auto-becomes child of parent. No manual parent passing.

**TS API**:
```typescript
import { traceable, getCurrentRunTree, RunTree } from "langsmith";

// Decorator-like: wrap function
const tracedSearch = traceable(search, { name: "search", run_type: "tool" });

// LangChain integration: getLangchainCallbacks()
import { getLangchainCallbacks } from "langsmith/langchain";
const callbacks = await getLangchainCallbacks();
agent.invoke({...}, { callbacks });
```

**LangChain integration**: LangSmith is built INTO LangChain. Setting `LANGSMITH_API_KEY` env var automatically enables tracing. No callback handler needed — `LangChainTracer` is a built-in `BaseTracer` in `langchain_core/tracers/langchain.py` that POSTs to LangSmith.

**Key difference**: LangSmith has first-class LangChain integration because they're the same company. No monkey-patching needed.

---

### 1.3 OpenLLMetry (Python + TypeScript)

**Architecture**: Pure OTel. Uses `tracer.start_as_current_span()` with GenAI semantic conventions. Produces standard OTel spans + metrics + log events.

**Python API**:
```python
from opentelemetry.instrumentation.openai import OpenAIInstrumentor

# Zero-code: just register
OpenAIInstrumentor().instrument()
# All openai calls now produce OTel spans automatically

# Configuration via env vars:
# OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

**No decorator API. No callback handler.** Pure auto-instrumentation. You bring your own OTel exporter.

**TS API**:
```typescript
import { OpenAIInstrumentation } from "@opentelemetry/instrumentation-openai";

const instrumentation = new OpenAIInstrumentation();
instrumentation.setTracerProvider(provider);
instrumentation.setMeterProvider(meterProvider);
// All openai calls now produce OTel spans
```

**What it captures**: Model name, tokens (prompt/completion/total), streaming metrics, tool calls, error types. Emits OTel metrics histograms for token usage and duration.

**No nesting concept** — relies on OTel's built-in parent span propagation.

---

## 2. Comparison Matrix

| Feature | Langfuse | LangSmith | OpenLLMetry | **etrace** |
|---|---|---|---|---|
| **Core primitive** | Observation (span/generation) | RunTree | OTel Span | Span |
| **Nesting mechanism** | OTel contextvars | WeakRef contextvars | OTel context | AsyncLocalStorage / contextvars |
| **Decorator** | `@observe(as_type="tool")` | `@traceable(run_type="tool")` | None | `@etrace.tool` / `observe()` |
| **Context manager** | Via OTel `_AgnosticContextManager` | `with trace(...) as run:` | None | `with etrace.trace(...)` |
| **Run types** | span, generation, agent, tool, chain, retriever, embedding, guardrail, evaluator | chain, llm, tool, retriever, embedding, prompt, parser | (OTel span kinds only) | 16 kinds |
| **LangChain** | CallbackHandler (Python) | Built-in tracer | None | CallbackHandler (Python) |
| **LangChain (TS)** | None | `getLangchainCallbacks()` | None | **None** |
| **Auto-instrument** | `observeOpenAI()` wrapper | None (relies on LangChain) | `OpenAIInstrumentor()` | Monkey-patch |
| **TS callback handler** | None | `getLangchainCallbacks()` | None | **None** |
| **Token capture** | Manual or via callback | Via LangChain | Automatic | Automatic |
| **Cost calculation** | Server-side | Server-side | None | Client-side |
| **Framework support** | LangChain only | LangChain only (native) | None | LangChain only |

---

## 3. Current etrace SDK State

### Python SDK

**User-space API** (in `agent.py`):
```python
etrace.init(service_name=..., exporters=[OtelExporter()], auto_instrument={"llm": False})

from etrace.langchain import EtraceLangChainHandler

with etrace.trace("deep_research_agent", kind="agent") as span:
    span.input = question
    handler = EtraceLangChainHandler()
    result = agent.invoke({"messages": [...]}, config={"callbacks": [handler]})
    span.output = final_answer
    handler.flush()

etrace.shutdown()
```

**What works well**:
- `@etrace.tool` / `@etrace.agent` decorators auto-capture input/output
- `etrace.trace()` context manager with proper nesting via `_current_span`
- `RunTracker` + `EtraceLangChainHandler` for LangGraph/LangChain callback integration
- `_current_span` bridging: callback handler sets `_current_span` so nested `@etrace.tool` works inside LangChain tools
- Auto-instrumentation captures model, tokens, costs
- 317 tests pass

**What's problematic**:
1. **User must know about callback handler + auto-instrument conflict** → `auto_instrument={"llm": False}` is a footgun
2. **Two tracing systems that must be manually coordinated**: `etrace.trace()` vs `RunTracker`
3. **`agent.py` is doing framework plumbing** — creating handler, disabling auto-instrument, calling flush()
4. **TS SDK has NO callback handler, NO RunTracker** — feature parity gap
5. **TS SDK auto-instrumentation doesn't capture tool calls** (only text output)

### TypeScript SDK

**What exists**:
- `trace()` with `AsyncLocalStorage` context propagation
- `observe()` decorator
- 15 convenience decorators
- `init()` with auto-instrumentation (OpenAI, Anthropic)
- `setUsage()`, `setOutput()`, `setAttribute()`, `score()`
- `InMemoryExporter`, `SimpleProcessor`, `BatchProcessor`

**What's missing**:
- **No `RunTracker`** equivalent
- **No LangChain callback handler** 
- **No `_current_span` bridging** from callback to trace context
- **No tool call output capture** in auto-instrumentation (only text)
- **No `OtelExporter`** (exists in `otel/` but not in main package)

---

## 4. Ideal SDK Design for the Deep-Research-Agent Pattern

### 4.1 The User's Mental Model

A user writing a LangChain agent wants:

```python
# What the user EXPECTS to write:
import etrace

etrace.init()  # That's it. Everything auto-captured.

# Their agent code is just:
@etrace.agent
def deep_research(query: str):
    return agent.invoke({"messages": [HumanMessage(content=query)]})
```

**Zero config. No callback handlers. No `auto_instrument={"llm": False}`. No flush().**

### 4.2 The Problem: Two Sources of Truth

Currently we have:
1. **Auto-instrumentation** (monkey-patches OpenAI/Anthropic) → creates LLM spans
2. **Callback handler** (LangChain `BaseCallbackHandler`) → creates LLM + tool + chain spans

When both are active → duplicate LLM spans. The user must disable one.

**LangSmith solves this** by being built into LangChain — no monkey-patching.
**Langfuse solves this** by having the callback handler be the ONLY source (it uses OTel internally to merge).

### 4.3 Proposed Architecture: "Single Source, Auto-Detect"

```
etrace.init()
    ├── Detect langchain installed? → Register callback handler automatically
    │   └── Callback handler produces ALL spans (LLM, tool, chain)
    │   └── Disable auto-instrumentation for LLM (internally)
    ├── No langchain? → Use auto-instrumentation (monkey-patch)
    │   └── Produces LLM spans only
    └── User can force: auto_instrument={"llm": True/False, "langchain": True/False}
```

### 4.4 Proposed User API (Python)

```python
import etrace

# INIT — one line, auto-detects
etrace.init(service_name="my-agent")

# USER CODE — just decorators, zero plumbing
@etrace.agent
def deep_research(query: str):
    result = agent.invoke({"messages": [HumanMessage(content=query)]})
    return result

# For non-LangChain code, same API:
@etrace.agent
async def my_custom_agent(query: str):
    # LLM calls auto-captured via auto-instrumentation
    response = await openai.chat.completions.create(...)
    # Tool calls via decorator:
    result = await my_tool(query)
    return result

@etrace.tool
async def my_tool(query: str):
    return "result"

# Context manager still available:
with etrace.trace("custom_step", kind="step") as span:
    span.output = do_work()
```

**Key principle**: The user NEVER imports or creates a callback handler. `etrace.init()` does it.

### 4.5 Proposed User API (TypeScript)

```typescript
import * as etrace from "etrace";

// INIT — one line
etrace.init({ serviceName: "my-agent" });

// LangChain: auto-detected, callback handler registered
// No user action needed

// Non-LangChain: decorators
const search = etrace.tool(async (query: string) => {
    return tavily.search(query);
});

const agent = etrace.agent(async (query: string) => {
    const results = await search(query);
    return synthesize(results);
});

// Context manager
const result = await etrace.trace("custom", async () => {
    return doWork();
}, { kind: "step" });
```

### 4.6 Implementation Plan

#### Phase 1: TypeScript Feature Parity (TS SDK)
1. **Add `RunTracker`** to TS SDK (`etrace/tracing.ts`)
   - Generic run tracking with `AsyncLocalStorage` for `_currentSpan` bridging
   - Same `on_run_start()`/`on_run_end()`/`on_run_error()` API
   - Walk-up parent resolution for skipped chain runs

2. **Add `EtraceLangChainHandler`** to TS SDK (`etrace/langchain.ts`)
   - Implement `BaseCallbackHandler` from `@langchain/core/callbacks/base`
   - Map `on_chat_model_start/end` → LLM spans with usage
   - Map `on_tool_start/end` → Tool spans, nested under last LLM
   - Skip chain spans (LangGraph noise)
   - Set `_currentSpan` so nested `@etrace.tool` works

3. **Add tool call output capture** to TS auto-instrumentation
   - `openai.ts`: When `msg.toolCalls` exists and `msg.content` is empty, capture as JSON output
   - `anthropic.ts`: When `tool_use` blocks exist and no text, capture as JSON

4. **Add `OtelExporter`** to main package export

#### Phase 2: Auto-Registration in `init()` (Both SDKs)

**Python** (`__init__.py`):
```python
def init(..., auto_instrument=None):
    if auto_instrument is None:
        auto_instrument = {"llm": True, "langchain": True}
    
    # If LangChain detected and not disabled:
    if auto_instrument.get("langchain", True) and _HAS_LANGCHAIN:
        # Register callback handler globally via langchain_core.tracers
        # Disable LLM auto-instrumentation (callback handles it)
        auto_instrument["llm"] = False
    
    if auto_instrument.get("llm", True):
        _instrument_all()
```

**TypeScript** (`index.ts`):
```typescript
export function init(config: InitConfig = {}): void {
    const autoInstrument = config.autoInstrument ?? { llm: true, langchain: true };
    
    // If LangChain detected and not disabled:
    if (autoInstrument.langchain !== false && hasLangChain()) {
        // Auto-register callback handler
        // Disable LLM auto-instrumentation
        autoInstrument.llm = false;
    }
    
    if (autoInstrument.llm !== false) {
        instrumentAll();
    }
}
```

**The problem**: LangChain doesn't have a global callback registration. You must pass `config={"callbacks": [handler]}` to every `.invoke()` call.

**LangSmith's approach**: LangChain has a built-in `LangChainTracer` that's automatically added to the callback manager when `LANGSMITH_API_KEY` is set. We can't replicate this without modifying LangChain.

**Langfuse's approach**: Users still pass `config={"callbacks": [CallbackHandler()]}` manually. There's no auto-registration.

**Pragmatic approach for etrace**: Since we can't auto-inject into LangChain's callback system without being a built-in tracer, we should:
1. **Make the callback handler trivially easy**: `etrace.langchain_handler` property that returns a singleton handler
2. **OR** patch `langchain_core.runnables.Runnable.invoke` to auto-inject our handler when etrace is initialized
3. **OR** provide a `etrace.trace_agent(agent, query)` helper that wraps the invoke

### 4.7 Recommended `agent.py` After Design Changes

```python
import etrace

etrace.init(service_name="deep-research-agent")  # auto-detects langchain, disables LLM auto-instrument

@etrace.agent
def deep_research(query: str):
    handler = etrace.langchain_handler  # singleton, pre-configured
    result = agent.invoke(
        {"messages": [HumanMessage(content=query)]},
        config={"callbacks": [handler]},
    )
    return extract_answer(result)
```

**Still requires one line** (`handler = etrace.langchain_handler`), but:
- No imports from `etrace.langchain`
- No `auto_instrument={"llm": False}`
- No `flush()` (auto-flushed on shutdown)
- The `@etrace.agent` decorator auto-captures input/output

### 4.8 Summary of Changes Needed

| Change | Priority | SDK | Complexity |
|---|---|---|---|
| TS: `RunTracker` + `EtraceLangChainHandler` | High | TS | Medium |
| TS: Tool call output capture in auto-instrumentation | High | TS | Low |
| TS: `OtelExporter` in main export | Medium | TS | Low |
| PY: Auto-detect langchain in `init()`, disable LLM auto-instrument | High | PY | Low |
| PY: `etrace.langchain_handler` singleton | High | PY | Low |
| PY: Auto-flush callback handler on shutdown | Medium | PY | Low |
| Both: Documentation + examples | High | Both | Medium |
