import "dotenv/config";

import { init, OtelExporter } from "../etrace";

const DEFAULT_STUDIO_OTLP_ENDPOINT = "http://localhost:3001/v1/traces";

process.env.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT ??=
  process.env.ETRACE_STUDIO_OTLP_ENDPOINT ?? DEFAULT_STUDIO_OTLP_ENDPOINT;
process.env.OTEL_SERVICE_NAME ??= "etrace-mastra-weather-agent";

init({
  exporters: [new OtelExporter()],
  calculateCosts: true,
  autoInstrument: { llm: false },
});
