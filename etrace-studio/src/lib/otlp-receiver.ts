import { decodeOtlpTraceRequest } from "./otlp"
import { TRACES, clearTraces, deleteTrace, ingestSpans } from "./traces"

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "content-type",
}

export function tracesResponse(): Response {
  return Response.json(TRACES, { headers: corsHeaders })
}

export async function ingestOtlpRequest(request: Request): Promise<Response> {
  const body = new Uint8Array(await request.arrayBuffer())
  const spans = decodeOtlpTraceRequest(body)
  ingestSpans(spans)
  return Response.json(
    { partialSuccess: {}, acceptedSpans: spans.length },
    { headers: corsHeaders }
  )
}

export function deleteTraceResponse(traceId: string): Response {
  if (!deleteTrace(traceId)) {
    return Response.json(
      { error: "Trace not found" },
      { status: 404, headers: corsHeaders }
    )
  }
  return Response.json({ deleted: true, traceId }, { headers: corsHeaders })
}

export function clearTracesResponse(): Response {
  clearTraces()
  return Response.json({ deleted: true }, { headers: corsHeaders })
}

export function optionsResponse(): Response {
  return new Response(null, { status: 204, headers: corsHeaders })
}
