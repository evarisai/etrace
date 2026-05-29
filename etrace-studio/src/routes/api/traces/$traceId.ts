import { createFileRoute } from "@tanstack/react-router"
import { deleteTraceResponse, optionsResponse } from "@/lib/otlp-receiver"

export const Route = createFileRoute("/api/traces/$traceId")({
  server: {
    handlers: {
      DELETE: async ({ params }) => deleteTraceResponse(params.traceId),
      OPTIONS: async () => optionsResponse(),
    },
  },
})
