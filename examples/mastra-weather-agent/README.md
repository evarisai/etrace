# etrace Mastra weather agent

TypeScript Mastra weather agent adapted from Mastra's `weather-agent` template.

This version:

- uses Z.AI's OpenAI-compatible GLM endpoint by default,
- removes the scorer setup from the upstream template,
- traces the CLI agent span and weather tool span with the local TypeScript `etrace` SDK source,
- exports spans to etrace Studio over OTLP.

## Run

```bash
cd examples/mastra-weather-agent
pnpm install
cp .env.example .env
```

Fill in `ZAI_API_KEY`, then run:

```bash
set -a; source .env; set +a
pnpm ask "What is the weather in Mumbai and should I walk outside?"
```

To use Mastra Studio:

```bash
pnpm dev
```

Open the Mastra Studio URL printed by the CLI.

## Notes

`OPENAI_BASE_URL` defaults to:

```bash
https://api.z.ai/api/paas/v4/
```

The example sends etrace spans to:

```bash
http://localhost:3001/v1/traces
```

Override that with `ETRACE_STUDIO_OTLP_ENDPOINT` if your etrace Studio receiver uses another host or port.

Source inspiration: <https://github.com/mastra-ai/weather-agent>
