import type { Span } from "./types"

const textDecoder = new TextDecoder()

interface DecodedSpan {
  traceId: string
  spanId: string
  parentSpanId: string | null
  name: string
  kind: Span["kind"]
  startTime: number
  endTime: number | null
  attributes: Record<string, unknown>
  events: Span["events"]
  status: Span["status"]
}

class ProtoReader {
  private offset = 0

  constructor(private readonly bytes: Uint8Array) {}

  get done(): boolean {
    return this.offset >= this.bytes.length
  }

  readTag(): { field: number; wire: number } | null {
    if (this.done) return null
    const tag = Number(this.readVarint())
    return { field: tag >>> 3, wire: tag & 7 }
  }

  readVarint(): bigint {
    let shift = 0n
    let result = 0n
    while (!this.done) {
      const byte = this.bytes[this.offset]
      this.offset += 1
      if (byte === undefined) break
      result |= BigInt(byte & 0x7f) << shift
      if ((byte & 0x80) === 0) return result
      shift += 7n
    }
    return result
  }

  readFixed64(): bigint {
    const view = new DataView(
      this.bytes.buffer,
      this.bytes.byteOffset + this.offset,
      8
    )
    const value = view.getBigUint64(0, true)
    this.offset += 8
    return value
  }

  readDouble(): number {
    const view = new DataView(
      this.bytes.buffer,
      this.bytes.byteOffset + this.offset,
      8
    )
    const value = view.getFloat64(0, true)
    this.offset += 8
    return value
  }

  readBytes(): Uint8Array {
    const length = Number(this.readVarint())
    const start = this.offset
    this.offset += length
    return this.bytes.subarray(start, start + length)
  }

  readString(): string {
    return textDecoder.decode(this.readBytes())
  }

  skip(wire: number): void {
    if (wire === 0) {
      this.readVarint()
      return
    }
    if (wire === 1) {
      this.offset += 8
      return
    }
    if (wire === 2) {
      this.readBytes()
      return
    }
    if (wire === 5) {
      this.offset += 4
    }
  }
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join(
    ""
  )
}

function nsToMs(ns: bigint): number {
  return Number(ns / 1_000_000n)
}

function readTime(reader: ProtoReader, wire: number): number {
  if (wire === 1) return nsToMs(reader.readFixed64())
  if (wire === 0) return nsToMs(reader.readVarint())
  reader.skip(wire)
  return 0
}

function decodeAnyValue(bytes: Uint8Array): unknown {
  const reader = new ProtoReader(bytes)
  while (!reader.done) {
    const tag = reader.readTag()
    if (!tag) break
    if (tag.field === 1 && tag.wire === 2) return reader.readString()
    if (tag.field === 2 && tag.wire === 0) return reader.readVarint() !== 0n
    if (tag.field === 3 && tag.wire === 0) return Number(reader.readVarint())
    if (tag.field === 4 && tag.wire === 1) return reader.readDouble()
    if (tag.field === 7 && tag.wire === 2) return bytesToHex(reader.readBytes())
    reader.skip(tag.wire)
  }
  return null
}

function decodeKeyValue(bytes: Uint8Array): [string, unknown] | null {
  const reader = new ProtoReader(bytes)
  let key = ""
  let value: unknown = null
  while (!reader.done) {
    const tag = reader.readTag()
    if (!tag) break
    if (tag.field === 1 && tag.wire === 2) {
      key = reader.readString()
    } else if (tag.field === 2 && tag.wire === 2) {
      value = decodeAnyValue(reader.readBytes())
    } else {
      reader.skip(tag.wire)
    }
  }
  return key ? [key, value] : null
}

function decodeAttributes(bytes: Uint8Array): Record<string, unknown> {
  const reader = new ProtoReader(bytes)
  const attributes: Record<string, unknown> = {}
  while (!reader.done) {
    const tag = reader.readTag()
    if (!tag) break
    if (tag.field === 1 && tag.wire === 2) {
      const pair = decodeKeyValue(reader.readBytes())
      if (pair) attributes[pair[0]] = pair[1]
    } else {
      reader.skip(tag.wire)
    }
  }
  return attributes
}

function decodeEvent(bytes: Uint8Array): Span["events"][number] {
  const reader = new ProtoReader(bytes)
  const event: Span["events"][number] = {
    name: "event",
    timestamp: Date.now(),
    attributes: {},
  }
  while (!reader.done) {
    const tag = reader.readTag()
    if (!tag) break
    if (tag.field === 1) {
      event.timestamp = readTime(reader, tag.wire)
    } else if (tag.field === 2 && tag.wire === 2) {
      event.name = reader.readString()
    } else if (tag.field === 3 && tag.wire === 2) {
      const pair = decodeKeyValue(reader.readBytes())
      if (pair) event.attributes[pair[0]] = pair[1]
    } else {
      reader.skip(tag.wire)
    }
  }
  return event
}

function mapKind(kind: number): Span["kind"] {
  if (kind === 2) return "SERVER"
  if (kind === 3) return "CLIENT"
  if (kind === 4) return "PRODUCER"
  if (kind === 5) return "CONSUMER"
  return "INTERNAL"
}

function mapStatus(statusCode: number): Span["status"] {
  if (statusCode === 1) return "OK"
  if (statusCode === 2) return "ERROR"
  return "UNSET"
}

function decodeStatus(bytes: Uint8Array): Span["status"] {
  const reader = new ProtoReader(bytes)
  let code = 0
  while (!reader.done) {
    const tag = reader.readTag()
    if (!tag) break
    if (tag.field === 3 && tag.wire === 0) {
      code = Number(reader.readVarint())
    } else {
      reader.skip(tag.wire)
    }
  }
  return mapStatus(code)
}

function decodeSpan(
  bytes: Uint8Array,
  resourceAttributes: Record<string, unknown>
): DecodedSpan | null {
  const reader = new ProtoReader(bytes)
  const span: DecodedSpan = {
    traceId: "",
    spanId: "",
    parentSpanId: null,
    name: "span",
    kind: "INTERNAL",
    startTime: Date.now(),
    endTime: null,
    attributes: { ...resourceAttributes },
    events: [],
    status: "UNSET",
  }

  while (!reader.done) {
    const tag = reader.readTag()
    if (!tag) break
    if (tag.field === 1 && tag.wire === 2) {
      span.traceId = bytesToHex(reader.readBytes())
    } else if (tag.field === 2 && tag.wire === 2) {
      span.spanId = bytesToHex(reader.readBytes())
    } else if (tag.field === 4 && tag.wire === 2) {
      const parent = bytesToHex(reader.readBytes())
      span.parentSpanId = parent || null
    } else if (tag.field === 5 && tag.wire === 2) {
      span.name = reader.readString()
    } else if (tag.field === 6 && tag.wire === 0) {
      span.kind = mapKind(Number(reader.readVarint()))
    } else if (tag.field === 7) {
      span.startTime = readTime(reader, tag.wire)
    } else if (tag.field === 8) {
      span.endTime = readTime(reader, tag.wire)
    } else if (tag.field === 9 && tag.wire === 2) {
      const pair = decodeKeyValue(reader.readBytes())
      if (pair) span.attributes[pair[0]] = pair[1]
    } else if (tag.field === 11 && tag.wire === 2) {
      span.events.push(decodeEvent(reader.readBytes()))
    } else if (tag.field === 15 && tag.wire === 2) {
      span.status = decodeStatus(reader.readBytes())
    } else {
      reader.skip(tag.wire)
    }
  }

  if (!span.traceId || !span.spanId) return null
  return span
}

function decodeScopeSpans(
  bytes: Uint8Array,
  resourceAttributes: Record<string, unknown>
): DecodedSpan[] {
  const reader = new ProtoReader(bytes)
  const spans: DecodedSpan[] = []
  while (!reader.done) {
    const tag = reader.readTag()
    if (!tag) break
    if (tag.field === 2 && tag.wire === 2) {
      const span = decodeSpan(reader.readBytes(), resourceAttributes)
      if (span) spans.push(span)
    } else {
      reader.skip(tag.wire)
    }
  }
  return spans
}

function decodeResourceSpans(bytes: Uint8Array): DecodedSpan[] {
  const reader = new ProtoReader(bytes)
  const scopePayloads: Uint8Array[] = []
  let resourceAttributes: Record<string, unknown> = {}

  while (!reader.done) {
    const tag = reader.readTag()
    if (!tag) break
    if (tag.field === 1 && tag.wire === 2) {
      resourceAttributes = decodeAttributes(reader.readBytes())
    } else if (tag.field === 2 && tag.wire === 2) {
      scopePayloads.push(reader.readBytes())
    } else {
      reader.skip(tag.wire)
    }
  }

  return scopePayloads.flatMap((payload) =>
    decodeScopeSpans(payload, resourceAttributes)
  )
}

export function decodeOtlpTraceRequest(bytes: Uint8Array): Span[] {
  const reader = new ProtoReader(bytes)
  const decoded: DecodedSpan[] = []
  while (!reader.done) {
    const tag = reader.readTag()
    if (!tag) break
    if (tag.field === 1 && tag.wire === 2) {
      decoded.push(...decodeResourceSpans(reader.readBytes()))
    } else {
      reader.skip(tag.wire)
    }
  }

  return decoded.map((span): Span => {
    const inputTokens = toNumber(span.attributes["gen_ai.usage.prompt_tokens"])
    const outputTokens = toNumber(
      span.attributes["gen_ai.usage.completion_tokens"]
    )
    const totalCost = toNumber(span.attributes["gen_ai.usage.cost"])
    return {
      id: span.spanId,
      trace_id: span.traceId,
      parent_span_id: span.parentSpanId,
      name: span.name,
      kind: span.kind,
      status: span.status,
      start_time: span.startTime,
      end_time: span.endTime,
      attributes: span.attributes,
      events: span.events,
      duration_ms:
        span.endTime === null
          ? null
          : Math.max(0, span.endTime - span.startTime),
      model: toStringValue(span.attributes["gen_ai.request.model"]),
      provider: toStringValue(span.attributes["gen_ai.system"]),
      input_tokens: inputTokens,
      output_tokens: outputTokens,
      total_cost: totalCost,
      input_payload: toStringValue(span.attributes["etrace.input"]),
      output_payload: toStringValue(span.attributes["etrace.output"]),
    }
  })
}

function toNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function toStringValue(value: unknown): string | null {
  return typeof value === "string" ? value : null
}
