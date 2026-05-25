/**
 * etrace[otel] — Optional OTel bridge.
 *
 * Export OtelExporter to convert etrace Span → OTel ReadableSpan
 * and delegate to any standard OTel SpanExporter.
 *
 * Requires: @opentelemetry/sdk-trace-base
 */
export { OtelExporter } from "./exporter.js";
