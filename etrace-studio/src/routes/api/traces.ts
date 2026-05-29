import { createFileRoute } from "@tanstack/react-router"
import {
  clearTracesResponse,
  ingestOtlpRequest,
  optionsResponse,
  tracesResponse,
} from "@/lib/otlp-receiver"

export const Route = createFileRoute("/api/traces")({
  server: {
    handlers: {
      GET: async () => tracesResponse(),
      POST: async ({ request }) => ingestOtlpRequest(request),
      DELETE: async () => clearTracesResponse(),
      OPTIONS: async () => optionsResponse(),
    },
  },
})
