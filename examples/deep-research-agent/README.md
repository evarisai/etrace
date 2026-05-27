# etrace deep research agent

This example adapts LangChain's Deep Agents deep-research tutorial to use an OpenAI-compatible model endpoint and `etrace` tracing.

The agent:
- plans a research workflow,
- delegates focused web research to a sub-agent,
- uses Tavily search plus full-page fetches,
- calls Z.AI through LangChain's OpenAI-compatible `ChatOpenAI`,
- exports etrace spans through OpenTelemetry to etrace Studio.

## Run

```bash
cd examples/deep-research-agent
uv sync
cp .env.example .env
```

Fill in `ZAI_API_KEY` and `TAVILY_API_KEY`, then run:

```bash
set -a; source .env; set +a
uv run python agent.py "What are the main differences between RAG and fine-tuning for LLM applications?"
```

By default, the example sends OTLP traces to:

```bash
http://localhost:3001/v1/traces
```

Override that with `ETRACE_STUDIO_OTLP_ENDPOINT` if your Studio receiver is on another host or port.

## Notes

`OPENAI_BASE_URL` defaults to Z.AI's OpenAI-compatible base URL. You can also set `OPENAI_API_KEY` directly; otherwise the script copies `ZAI_API_KEY` into `OPENAI_API_KEY` for LangChain/OpenAI compatibility.

Source inspiration: LangChain's Deep Agents deep-research tutorial.
