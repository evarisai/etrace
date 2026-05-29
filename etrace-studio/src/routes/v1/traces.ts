import { createFileRoute } from "@tanstack/react-router"
import {
  ingestOtlpRequest,
  optionsResponse,
  tracesResponse,
} from "@/lib/otlp-receiver"

export const Route = createFileRoute("/v1/traces")({
  server: {
    handlers: {
      GET: async () => tracesResponse(),
      POST: async ({ request }) => ingestOtlpRequest(request),
      OPTIONS: async () => optionsResponse(),
    },
  },
})
