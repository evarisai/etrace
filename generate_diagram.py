#!/usr/bin/env python3
"""
Evaris Tracing Layer — Architecture Diagram
Generates: trace/architecture-diagram.html (interactive SVG+HTML diagram)
"""

DIAGRAM_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Evaris Tracing Layer — Architecture</title>
<style>
  :root {
    --bg: #0a0c10;
    --surface: #12151c;
    --border: rgba(255,255,255,0.08);
    --text: #e1e8ec;
    --text-dim: #7d8a90;
    --accent-blue: #5b8def;
    --accent-cyan: #4fcae3;
    --accent-green: #4ecb8d;
    --accent-orange: #f0983a;
    --accent-pink: #e35d8a;
    --accent-purple: #a06de3;
    --accent-yellow: #e3d44f;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, sans-serif;
    line-height: 1.5;
    min-height: 100vh;
  }
  .container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 40px 24px;
  }
  h1 {
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -0.03em;
    margin-bottom: 8px;
  }
  .subtitle {
    color: var(--text-dim);
    font-size: 14px;
    margin-bottom: 48px;
  }
  
  /* Layer cards */
  .layer {
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 28px;
    margin-bottom: 20px;
    position: relative;
    overflow: hidden;
  }
  .layer::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 16px 16px 0 0;
  }
  .layer-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 20px;
  }
  .layer-number {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 3px 10px;
    border-radius: 6px;
    background: rgba(255,255,255,0.06);
    color: var(--text-dim);
  }
  .layer-title {
    font-size: 18px;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  .layer-status {
    margin-left: auto;
    font-size: 12px;
    padding: 3px 10px;
    border-radius: 6px;
    font-weight: 500;
  }
  .status-done { background: rgba(78,203,141,0.15); color: #4ecb8d; }
  .status-partial { background: rgba(240,152,58,0.15); color: #f0983a; }
  .status-needed { background: rgba(227,93,138,0.15); color: #e35d8a; }

  /* Color coding per layer */
  .layer-app { background: rgba(227,93,138,0.04); }
  .layer-app::before { background: var(--accent-pink); }
  
  .layer-auto { background: rgba(160,109,227,0.04); }
  .layer-auto::before { background: var(--accent-purple); }
  
  .layer-otel { background: rgba(79,202,227,0.04); }
  .layer-otel::before { background: var(--accent-cyan); }
  
  .layer-ingest { background: rgba(91,141,239,0.04); }
  .layer-ingest::before { background: var(--accent-blue); }
  
  .layer-storage { background: rgba(78,203,141,0.04); }
  .layer-storage::before { background: var(--accent-green); }
  
  .layer-query { background: rgba(227,212,79,0.04); }
  .layer-query::before { background: var(--accent-yellow); }
  
  .layer-ui { background: rgba(240,152,58,0.04); }
  .layer-ui::before { background: var(--accent-orange); }

  /* Sub-boxes within layers */
  .sub-grid {
    display: grid;
    gap: 12px;
  }
  .grid-5 { grid-template-columns: repeat(5, 1fr); }
  .grid-4 { grid-template-columns: repeat(4, 1fr); }
  .grid-3 { grid-template-columns: repeat(3, 1fr); }
  .grid-2 { grid-template-columns: repeat(2, 1fr); }
  .grid-auto { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }

  .sub-box {
    background: rgba(0,0,0,0.25);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px;
  }
  .sub-box-title {
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 6px;
  }
  .sub-box-content {
    font-size: 12px;
    color: var(--text-dim);
    line-height: 1.6;
  }
  .sub-box-content code {
    background: rgba(255,255,255,0.06);
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 11px;
    color: var(--text);
  }

  /* Flow arrows */
  .flow-arrow {
    text-align: center;
    padding: 8px 0;
    color: var(--text-dim);
    font-size: 22px;
    line-height: 1;
  }
  .flow-label {
    font-size: 11px;
    color: var(--text-dim);
    margin-top: 2px;
  }

  /* Adapter chain */
  .adapter-chain {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .adapter-box {
    background: rgba(91,141,239,0.12);
    border: 1px solid rgba(91,141,239,0.25);
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 12px;
    font-weight: 500;
  }
  .adapter-arrow {
    color: var(--accent-blue);
    font-size: 16px;
  }
  .adapter-result {
    background: rgba(78,203,141,0.12);
    border: 1px solid rgba(78,203,141,0.25);
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 12px;
    font-weight: 500;
    color: var(--accent-green);
  }

  /* Legend */
  .legend {
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
    margin-top: 48px;
    padding-top: 24px;
    border-top: 1px solid var(--border);
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--text-dim);
  }
  .legend-dot {
    width: 10px;
    height: 10px;
    border-radius: 3px;
  }

  /* SDK boxes */
  .sdk-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin-top: 16px;
  }
  .sdk-card {
    background: rgba(0,0,0,0.3);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    text-align: center;
  }
  .sdk-card h3 {
    font-size: 15px;
    margin-bottom: 4px;
  }
  .sdk-card .pkg {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px;
    color: var(--text-dim);
    margin-bottom: 10px;
  }
  .sdk-card .api-list {
    text-align: left;
    font-size: 12px;
    color: var(--text-dim);
    line-height: 1.8;
  }

  /* Decorator pills */
  .decorator-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
  }
  .pill {
    background: rgba(160,109,227,0.15);
    border: 1px solid rgba(160,109,227,0.25);
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    color: var(--accent-purple);
  }

  /* Data flow diagram */
  .data-flow {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    padding: 16px 0;
    flex-wrap: wrap;
  }
  .df-node {
    background: rgba(0,0,0,0.3);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 16px;
    text-align: center;
    min-width: 100px;
  }
  .df-node-label {
    font-size: 11px;
    font-weight: 600;
    margin-bottom: 2px;
  }
  .df-node-sub {
    font-size: 10px;
    color: var(--text-dim);
  }
  .df-arrow {
    color: var(--text-dim);
    font-size: 18px;
  }
  .df-label {
    font-size: 10px;
    color: var(--text-dim);
    writing-mode: horizontal-tb;
  }

  /* Timeline */
  .timeline {
    position: relative;
    padding-left: 32px;
    margin-top: 16px;
  }
  .timeline::before {
    content: '';
    position: absolute;
    left: 8px;
    top: 0;
    bottom: 0;
    width: 2px;
    background: var(--border);
  }
  .tl-item {
    position: relative;
    margin-bottom: 24px;
  }
  .tl-item::before {
    content: '';
    position: absolute;
    left: -28px;
    top: 4px;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    border: 2px solid;
  }
  .tl-item.done::before { background: var(--accent-green); border-color: var(--accent-green); }
  .tl-item.partial::before { background: var(--accent-orange); border-color: var(--accent-orange); }
  .tl-item.needed::before { background: transparent; border-color: var(--accent-pink); }
  
  .tl-title {
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 2px;
  }
  .tl-desc {
    font-size: 12px;
    color: var(--text-dim);
  }
  .tl-effort {
    font-size: 11px;
    color: var(--text-dim);
    margin-top: 4px;
    font-style: italic;
  }

  @media (max-width: 768px) {
    .grid-5, .grid-4, .grid-3 { grid-template-columns: repeat(2, 1fr); }
    .sdk-grid { grid-template-columns: 1fr; }
    .data-flow { flex-direction: column; }
  }
</style>
</head>
<body>
<div class="container">

<h1>Evaris Tracing Architecture</h1>
<p class="subtitle">Capturing every agent action — LLM calls, tool executions, retrievals, code execution, search, guardrails — with zero-config auto-instrumentation.</p>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- LAYER 0: Agent Application                                        -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<div class="layer layer-app">
  <div class="layer-header">
    <span class="layer-number">Application</span>
    <span class="layer-title">Agent / Application Code</span>
    <span class="layer-status status-needed">User Code</span>
  </div>
  <div class="sub-grid grid-5">
    <div class="sub-box">
      <div class="sub-box-title">🧠 LLM Calls</div>
      <div class="sub-box-content">OpenAI, Anthropic,<br/>Gemini, Cohere, Bedrock</div>
    </div>
    <div class="sub-box">
      <div class="sub-box-title">🔧 Tool Calls</div>
      <div class="sub-box-content">Web search, DB queries,<br/>API calls, file I/O</div>
    </div>
    <div class="sub-box">
      <div class="sub-box-title">🔍 Retrieval</div>
      <div class="sub-box-content">RAG, vector search,<br/>Chroma, Pinecone</div>
    </div>
    <div class="sub-box">
      <div class="sub-box-title">💻 Code Execution</div>
      <div class="sub-box-content">Python sandbox, Docker,<br/>E2B, subprocess</div>
    </div>
    <div class="sub-box">
      <div class="sub-box-title">🛡️ Guardrails</div>
      <div class="sub-box-content">Safety checks, content<br/>filtering, validation</div>
    </div>
  </div>
</div>

<div class="flow-arrow">
  ↓<br/><span class="flow-label">Each action emits an OpenTelemetry span</span>
</div>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- LAYER 1: Auto-Instrumentation                                     -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<div class="layer layer-auto">
  <div class="layer-header">
    <span class="layer-number">Layer 1</span>
    <span class="layer-title">Auto-Instrumentation Engine</span>
    <span class="layer-status status-done">Python ✅ · TS Partial</span>
  </div>
  
  <div class="sub-grid grid-2" style="margin-bottom:16px;">
    <div class="sub-box">
      <div class="sub-box-title">🤖 Fully Automatic (Monkey-Patching)</div>
      <div class="sub-box-content">
        <strong>Engine: Traceloop OpenLLMetry</strong><br/><br/>
        Patches SDKs at import time. Zero code changes.<br/><br/>
        <div style="display:flex; flex-wrap:wrap; gap:4px;">
          <span class="pill" style="background:rgba(78,203,141,0.15);border-color:rgba(78,203,141,0.25);color:#4ecb8d">OpenAI</span>
          <span class="pill" style="background:rgba(78,203,141,0.15);border-color:rgba(78,203,141,0.25);color:#4ecb8d">Anthropic</span>
          <span class="pill" style="background:rgba(78,203,141,0.15);border-color:rgba(78,203,141,0.25);color:#4ecb8d">Cohere</span>
          <span class="pill" style="background:rgba(78,203,141,0.15);border-color:rgba(78,203,141,0.25);color:#4ecb8d">Gemini</span>
          <span class="pill" style="background:rgba(78,203,141,0.15);border-color:rgba(78,203,141,0.25);color:#4ecb8d">Bedrock</span>
          <span class="pill" style="background:rgba(78,203,141,0.15);border-color:rgba(78,203,141,0.25);color:#4ecb8d">LangChain</span>
          <span class="pill" style="background:rgba(78,203,141,0.15);border-color:rgba(78,203,141,0.25);color:#4ecb8d">LlamaIndex</span>
          <span class="pill" style="background:rgba(78,203,141,0.15);border-color:rgba(78,203,141,0.25);color:#4ecb8d">Vercel AI SDK</span>
        </div>
      </div>
    </div>
    <div class="sub-box">
      <div class="sub-box-title">🏷️ Semi-Automatic (Decorators)</div>
      <div class="sub-box-content">
        <strong>Opt-in via decorators. Auto-captures args → input, return → output.</strong><br/><br/>
        <div class="decorator-pills">
          <span class="pill">@workflow</span>
          <span class="pill">@agent</span>
          <span class="pill">@task</span>
          <span class="pill">@tool</span>
          <span class="pill">@llm</span>
          <span class="pill">@retriever</span>
          <span class="pill">@embedding</span>
          <span class="pill">@chain</span>
          <span class="pill">@guardrail</span>
          <span class="pill">@human</span>
          <span class="pill">@evaluation</span>
          <span class="pill">@observe()</span>
        </div>
      </div>
    </div>
  </div>

  <div class="sub-box">
    <div class="sub-box-title">🔄 Context Propagation</div>
    <div class="sub-box-content">
      <code>contextvars</code> (Python) · <code>AsyncLocalStorage</code> (Node) · <code>context.Context</code> (Go)<br/>
      Automatically propagates: trace_id, session_id, user_id, conversation_id, tags, version across async call chains.
    </div>
  </div>
</div>

<div class="flow-arrow">
  ↓<br/><span class="flow-label">Spans with gen_ai.* + evaris.* semantic attributes</span>
</div>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- LAYER 2: OTel SDK                                                 -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<div class="layer layer-otel">
  <div class="layer-header">
    <span class="layer-number">Layer 2</span>
    <span class="layer-title">OpenTelemetry SDK + OTLP Export</span>
    <span class="layer-status status-done">Standard OTel ✅</span>
  </div>
  <div class="sub-grid grid-3">
    <div class="sub-box">
      <div class="sub-box-title">TracerProvider</div>
      <div class="sub-box-content">
        <code>Resource</code>: service.name, project_id<br/>
        <code>Tracer</code>: creates spans<br/>
        <code>Context</code>: propagation
      </div>
    </div>
    <div class="sub-box">
      <div class="sub-box-title">BatchSpanProcessor</div>
      <div class="sub-box-content">
        Batches spans for efficiency<br/>
        Flushes every 5s or 512 spans<br/>
        Retries on failure
      </div>
    </div>
    <div class="sub-box">
      <div class="sub-box-title">OTLP HTTP Exporter</div>
      <div class="sub-box-content">
        POST <code>/v1/traces</code><br/>
        JSON + Protobuf<br/>
        Headers: Auth + Project
      </div>
    </div>
  </div>
</div>

<div class="flow-arrow">
  ↓<br/><span class="flow-label">OTLP HTTP/JSON or HTTP/Protobuf</span>
</div>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- LAYER 3: Ingestion Gateway                                        -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<div class="layer layer-ingest">
  <div class="layer-header">
    <span class="layer-number">Layer 3</span>
    <span class="layer-title">Ingestion Gateway (Evaris Runtime)</span>
    <span class="layer-status status-done">Complete ✅</span>
  </div>
  <div class="sub-grid grid-3" style="margin-bottom:16px;">
    <div class="sub-box">
      <div class="sub-box-title">🔐 Auth & Security</div>
      <div class="sub-box-content">
        Bearer token → project_id, tenant_id<br/>
        <strong>NEVER from span attrs</strong><br/>
        Remote eval callback tokens
      </div>
    </div>
    <div class="sub-box">
      <div class="sub-box-title">📡 OTLP Receiver</div>
      <div class="sub-box-content">
        <code>otlp_receiver.py</code><br/>
        JSON + Protobuf parsing<br/>
        Correlation ID extraction
      </div>
    </div>
    <div class="sub-box">
      <div class="sub-box-title">⚡ Trigger Hooks</div>
      <div class="sub-box-content">
        <code>on_trace_received()</code><br/>
        Fires eval triggers<br/>
        Updates execution status
      </div>
    </div>
  </div>

  <div class="sub-box">
    <div class="sub-box-title">🔧 Span Normalization (Adapter Chain — first match wins)</div>
    <div class="adapter-chain">
      <div class="adapter-box">Vercel AI SDK</div>
      <span class="adapter-arrow">→</span>
      <div class="adapter-box">Traceloop / OpenLLMetry</div>
      <span class="adapter-arrow">→</span>
      <div class="adapter-box">Claude Agent SDK</div>
      <span class="adapter-arrow">→</span>
      <div class="adapter-box">gen_ai.* SemConv</div>
      <span class="adapter-arrow">→</span>
      <div class="adapter-box">Legacy llm.*</div>
      <span class="adapter-arrow">→</span>
      <div class="adapter-result">NormalizedLLMSpan | NormalizedToolSpan | NormalizedOther</div>
    </div>
  </div>
</div>

<div class="flow-arrow">
  ↓<br/><span class="flow-label">Batch writes (50+ columns per row)</span>
</div>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- LAYER 4: Storage                                                  -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<div class="layer layer-storage">
  <div class="layer-header">
    <span class="layer-number">Layer 4</span>
    <span class="layer-title">Storage (ClickHouse)</span>
    <span class="layer-status status-done">Schema ✅</span>
  </div>
  <div class="sub-grid grid-4">
    <div class="sub-box">
      <div class="sub-box-title" style="color:var(--accent-green)">otel_spans</div>
      <div class="sub-box-content">
        50+ columns<br/>
        Partitioned: <code>toYYYYMM</code><br/>
        Ordered: tenant → project → time
      </div>
    </div>
    <div class="sub-box">
      <div class="sub-box-title" style="color:var(--accent-green)">trace_scores</div>
      <div class="sub-box-content">
        Score/feedback storage<br/>
        Numeric, boolean, categorical<br/>
        Sources: API, eval, annotation
      </div>
    </div>
    <div class="sub-box">
      <div class="sub-box-title" style="color:var(--accent-green)">trace_sessions</div>
      <div class="sub-box-content">
        Session tracking<br/>
        User → session mapping<br/>
        Metadata, environment
      </div>
    </div>
    <div class="sub-box">
      <div class="sub-box-title" style="color:var(--accent-green)">eval_events</div>
      <div class="sub-box-content">
        Eval run telemetry<br/>
        Per-sample events<br/>
        Tokens, cost, status
      </div>
    </div>
  </div>
</div>

<div class="flow-arrow">
  ↓<br/><span class="flow-label">SQL queries for analytics, dashboards, alerts</span>
</div>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- LAYER 5: Query & Analytics                                        -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<div class="layer layer-query">
  <div class="layer-header">
    <span class="layer-number">Layer 5</span>
    <span class="layer-title">Query, Analytics & Monitoring</span>
    <span class="layer-status status-partial">Mostly Done 🟡</span>
  </div>
  <div class="sub-grid grid-3">
    <div class="sub-box">
      <div class="sub-box-title">📊 Trace Explorer</div>
      <div class="sub-box-content">
        Waterfall tree view<br/>
        Span search (payload, name, type)<br/>
        Payload inspection<br/>
        Context-aware navigation
      </div>
    </div>
    <div class="sub-box">
      <div class="sub-box-title">📈 Monitoring</div>
      <div class="sub-box-content">
        Error rate, latency, cost<br/>
        Quality signals (toxicity, PII, etc.)<br/>
        Anomaly detection (z-score)<br/>
        Alert rules → Slack/webhook
      </div>
    </div>
    <div class="sub-box">
      <div class="sub-box-title">🧪 Eval Integration</div>
      <div class="sub-box-content">
        Auto-trigger on trace_received<br/>
        Score traces from evals<br/>
        Compare eval vs production<br/>
        Session timeline
      </div>
    </div>
  </div>
</div>

<div class="flow-arrow">
  ↓<br/><span class="flow-label">REST API + WebSocket for real-time updates</span>
</div>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- LAYER 6: Presentation                                             -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<div class="layer layer-ui">
  <div class="layer-header">
    <span class="layer-number">Layer 6</span>
    <span class="layer-title">Presentation Layer</span>
    <span class="layer-status status-done">Workshop ✅ · Platform ✅</span>
  </div>
  <div class="sub-grid grid-2">
    <div class="sub-box">
      <div class="sub-box-title">🖥️ Workshop (Local Dev)</div>
      <div class="sub-box-content">
        Real-time trace streaming (WebSocket)<br/>
        Span waterfall with live events<br/>
        Agent chat (Claude Code, Codex)<br/>
        Replay engine · Annotations<br/>
        <strong>Storage: SQLite</strong> (local, zero-config)
      </div>
    </div>
    <div class="sub-box">
      <div class="sub-box-title">☁️ Platform (Cloud)</div>
      <div class="sub-box-content">
        Multi-tenant trace explorer<br/>
        Session timeline & conversation view<br/>
        Cost analytics & budget alerts<br/>
        Quality monitoring dashboard<br/>
        <strong>Storage: ClickHouse</strong> (production scale)
      </div>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- SDK Section                                                       -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<h2 style="margin-top:48px; margin-bottom:8px; font-size:20px;">Multi-Language SDKs</h2>
<p class="subtitle" style="margin-bottom:24px;">Same API surface across Python, TypeScript, and Go.</p>

<div class="sdk-grid">
  <div class="sdk-card" style="border-color:rgba(78,203,141,0.25);">
    <h3 style="color:var(--accent-green);">Python SDK</h3>
    <div class="pkg">evaris_sdk</div>
    <div class="api-list">
      ✅ <code>init()</code> — one-line setup<br/>
      ✅ <code>@observe()</code> — decorator<br/>
      ✅ <code>trace()</code> — context manager<br/>
      ✅ <code>.score()</code> / <code>.feedback()</code><br/>
      ✅ <code>.session()</code><br/>
      ✅ Traceloop auto-instrumentation<br/>
      🟡 Custom instrumentors
    </div>
  </div>
  <div class="sdk-card" style="border-color:rgba(240,152,58,0.25);">
    <h3 style="color:var(--accent-orange);">TypeScript SDK</h3>
    <div class="pkg">@evaris/sdk</div>
    <div class="api-list">
      🟡 <code>init()</code> — needs tracing layer<br/>
      🟡 Vercel AI SDK wrapper (in Workshop)<br/>
      ❌ Decorator pattern<br/>
      ❌ <code>trace()</code> context manager<br/>
      ❌ <code>.score()</code> / <code>.session()</code><br/>
      ❌ Traceloop auto-instrumentation<br/>
      ❌ Custom instrumentors
    </div>
  </div>
  <div class="sdk-card" style="border-color:rgba(227,93,138,0.25);">
    <h3 style="color:var(--accent-pink);">Go SDK</h3>
    <div class="pkg">evaris-go</div>
    <div class="api-list">
      ❌ <code>evaris.Init()</code><br/>
      ❌ <code>evaris.Trace()</code><br/>
      ❌ OTel Go bridge<br/>
      ❌ Context propagation<br/>
      ❌ Scoring / sessions<br/>
      ❌ Auto-instrumentation
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- Data Flow: One Span's Journey                                     -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<h2 style="margin-top:48px; margin-bottom:8px; font-size:20px;">Data Flow: One Span's Journey</h2>
<p class="subtitle" style="margin-bottom:24px;">What happens when <code>client.chat.completions.create()</code> is called in a traced agent.</p>

<div class="data-flow">
  <div class="df-node" style="border-color:rgba(227,93,138,0.3);">
    <div class="df-node-label">1. OpenAI Call</div>
    <div class="df-node-sub">Traceloop intercepts</div>
  </div>
  <div class="df-arrow">→</div>
  <div class="df-node" style="border-color:rgba(160,109,227,0.3);">
    <div class="df-node-label">2. Span Created</div>
    <div class="df-node-sub">gen_ai.* attributes set</div>
  </div>
  <div class="df-arrow">→</div>
  <div class="df-node" style="border-color:rgba(79,202,227,0.3);">
    <div class="df-node-label">3. Batched</div>
    <div class="df-node-sub">BatchSpanProcessor</div>
  </div>
  <div class="df-arrow">→</div>
  <div class="df-node" style="border-color:rgba(79,202,227,0.3);">
    <div class="df-node-label">4. OTLP Export</div>
    <div class="df-node-sub">HTTP POST /v1/traces</div>
  </div>
  <div class="df-arrow">→</div>
  <div class="df-node" style="border-color:rgba(91,141,239,0.3);">
    <div class="df-node-label">5. Ingest</div>
    <div class="df-node-sub">Auth + Validate</div>
  </div>
  <div class="df-arrow">→</div>
  <div class="df-node" style="border-color:rgba(91,141,239,0.3);">
    <div class="df-node-label">6. Normalize</div>
    <div class="df-node-sub">Adapter chain</div>
  </div>
  <div class="df-arrow">→</div>
  <div class="df-node" style="border-color:rgba(78,203,141,0.3);">
    <div class="df-node-label">7. Store</div>
    <div class="df-node-sub">ClickHouse write</div>
  </div>
  <div class="df-arrow">→</div>
  <div class="df-node" style="border-color:rgba(240,152,58,0.3);">
    <div class="df-node-label">8. Display</div>
    <div class="df-node-sub">Workshop / Platform UI</div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- Span Model                                                        -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<h2 style="margin-top:48px; margin-bottom:8px; font-size:20px;">Span Data Model (What Gets Captured)</h2>
<p class="subtitle" style="margin-bottom:24px;">Every action produces a span with these fields. This is the canonical Evaris trace model.</p>

<div class="sub-grid grid-3">
  <div class="sub-box" style="border-color:rgba(91,141,239,0.2);">
    <div class="sub-box-title" style="color:var(--accent-blue)">Identity & Hierarchy</div>
    <div class="sub-box-content">
      <code>trace_id</code> — groups all spans in one "turn"<br/>
      <code>span_id</code> — unique per span<br/>
      <code>parent_span_id</code> — forms the tree<br/>
      <code>kind</code> — workflow|agent|task|tool|llm|retrieval|embedding|chain|guardrail|eval|human|custom
    </div>
  </div>
  <div class="sub-box" style="border-color:rgba(78,203,141,0.2);">
    <div class="sub-box-title" style="color:var(--accent-green)">Content & Telemetry</div>
    <div class="sub-box-content">
      <code>input_value</code> — full input payload<br/>
      <code>output_value</code> — full output payload<br/>
      <code>llm_model</code> — gpt-4, claude-3, etc.<br/>
      <code>prompt_tokens / completion_tokens</code><br/>
      <code>input_cost / output_cost</code><br/>
      <code>model_parameters</code> — temperature, etc.
    </div>
  </div>
  <div class="sub-box" style="border-color:rgba(240,152,58,0.2);">
    <div class="sub-box-title" style="color:var(--accent-orange)">Context & Metadata</div>
    <div class="sub-box-content">
      <code>project_id / tenant_id</code><br/>
      <code>user_id / session_id</code><br/>
      <code>conversation_id</code><br/>
      <code>environment</code> — production|staging|dev<br/>
      <code>version / release</code><br/>
      <code>tags[]</code> — user-defined labels
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- Implementation Status                                             -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<h2 style="margin-top:48px; margin-bottom:8px; font-size:20px;">Implementation Status & Roadmap</h2>
<p class="subtitle" style="margin-bottom:24px;">What's done, what's needed, and estimated effort.</p>

<div class="timeline">
  <div class="tl-item done">
    <div class="tl-title">OTLP Ingestion Gateway</div>
    <div class="tl-desc">JSON + Protobuf, auth, ClickHouse writes, trigger hooks</div>
    <div class="tl-effort">✅ Done — otlp_receiver.py</div>
  </div>
  <div class="tl-item done">
    <div class="tl-title">ClickHouse Schema</div>
    <div class="tl-desc">otel_spans (50+ columns), trace_scores, trace_sessions</div>
    <div class="tl-effort">✅ Done — clickhouse_schema.py</div>
  </div>
  <div class="tl-item done">
    <div class="tl-title">Span Normalization Engine</div>
    <div class="tl-desc">Adapter chain: AI SDK → Traceloop → Claude Agent SDK → gen_ai.* SemConv</div>
    <div class="tl-effort">✅ Done — workshop/src/spans/</div>
  </div>
  <div class="tl-item done">
    <div class="tl-title">Python SDK (Core)</div>
    <div class="tl-desc">Types, decorators, OTel bridge, Traceloop integration, context propagation</div>
    <div class="tl-effort">✅ Done — packages/evaris-sdk-py/</div>
  </div>
  <div class="tl-item done">
    <div class="tl-title">Monitoring & Alerting</div>
    <div class="tl-desc">Error rate, latency, cost alerts. Quality signals. Slack notifications.</div>
    <div class="tl-effort">✅ Done — telemetry/monitoring.py</div>
  </div>
  <div class="tl-item done">
    <div class="tl-title">Workshop UI</div>
    <div class="tl-desc">Real-time trace viewer, span waterfall, agent chat, replay engine</div>
    <div class="tl-effort">✅ Done — workshop/</div>
  </div>
  <div class="tl-item partial">
    <div class="tl-title">Scores / Feedback / Sessions APIs</div>
    <div class="tl-desc">Types done. Need REST endpoint implementations on runtime.</div>
    <div class="tl-effort">🟡 ~1 week</div>
  </div>
  <div class="tl-item partial">
    <div class="tl-title">Custom Instrumentors</div>
    <div class="tl-desc">Code execution, web search, RAG, guardrails — beyond what Traceloop covers</div>
    <div class="tl-effort">🟡 ~2-3 weeks</div>
  </div>
  <div class="tl-item needed">
    <div class="tl-title">Node/TypeScript SDK (Tracing)</div>
    <div class="tl-desc">Port types, OTel bridge, Vercel AI SDK wrapper, decorator pattern</div>
    <div class="tl-effort">🔴 ~3-4 weeks</div>
  </div>
  <div class="tl-item needed">
    <div class="tl-title">Go SDK</div>
    <div class="tl-desc">OTel Go bridge, tracing types, context propagation</div>
    <div class="tl-effort">🔴 ~2-3 weeks</div>
  </div>
  <div class="tl-item needed">
    <div class="tl-title">Span Links & Cross-Trace</div>
    <div class="tl-desc">Agent → sub-agent, eval → production trace correlation</div>
    <div class="tl-effort">🔴 ~1 week</div>
  </div>
  <div class="tl-item needed">
    <div class="tl-title">Sampling & Rate Limiting</div>
    <div class="tl-desc">Head-based or tail-based sampling for high-volume agents</div>
    <div class="tl-effort">🔴 ~1-2 weeks</div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════════ -->
<!-- Legend                                                            -->
<!-- ═══════════════════════════════════════════════════════════════════ -->
<div class="legend">
  <div class="legend-item">
    <div class="legend-dot" style="background:var(--accent-green);"></div>
    Done — production ready
  </div>
  <div class="legend-item">
    <div class="legend-dot" style="background:var(--accent-orange);"></div>
    Partial — needs work
  </div>
  <div class="legend-item">
    <div class="legend-dot" style="background:var(--accent-pink);"></div>
    Needed — not started
  </div>
  <div class="legend-item" style="margin-left:auto; font-style:italic;">
    Estimated: ~10-14 weeks for full production tracing across Python + TS + Go (2 engineers)
  </div>
</div>

</div>
</body>
</html>
"""

if __name__ == "__main__":
    import os
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, "architecture-diagram.html")
    with open(out_path, "w") as f:
        f.write(DIAGRAM_HTML)
    print(f"Architecture diagram written to {out_path}")
    print("Open in browser to view the interactive diagram.")
