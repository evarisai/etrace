import { useMemo, useState } from "react"
import { ToolCallPill } from "./SpanBadges"
import { FlameTimeline } from "./FlameTimeline"
import { spanKind } from "@/lib/types"
import type { Span } from "@/lib/types"

const COMPACT_CHARS = 700

function ExpandableText({
  content,
  align = "left",
  className = "",
}: {
  content: string
  align?: "left" | "right"
  className?: string
}) {
  const [expanded, setExpanded] = useState(false)
  const isLong =
    content.length > COMPACT_CHARS || content.split("\n").length > 10
  const display =
    !isLong || expanded
      ? content
      : `${content.slice(0, COMPACT_CHARS).trimEnd()}…`

  return (
    <div className={className}>
      <pre
        className={`font-sans text-xs leading-relaxed whitespace-pre-wrap text-foreground ${
          align === "right" ? "text-right" : ""
        }`}
      >
        {display}
      </pre>
      {isLong && (
        <button
          type="button"
          className="mt-1 border border-border bg-background px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground hover:text-foreground"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "collapse" : "expand"}
        </button>
      )}
    </div>
  )
}

function UserBubble({ content, source }: { content: string; source?: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[65%] rounded-lg rounded-br-sm border border-primary/20 bg-primary/10 px-3 py-2">
        {source && (
          <div className="mb-1 font-mono text-[10px] text-primary/70">
            {source}
          </div>
        )}
        <ExpandableText content={content} align="right" />
      </div>
    </div>
  )
}

function LLMOutput({ content }: { content: string }) {
  return (
    <div className="max-w-[80%]">
      <ExpandableText content={content} />
    </div>
  )
}

type ChatItem =
  | { type: "user"; content: string; time: number; source?: string }
  | { type: "llm"; span: Span; time: number }
  | { type: "tool_group"; tools: Span[]; time: number }
  | { type: "error"; span: Span; time: number }

export function ChatFlow({
  spans,
  onSpanClick,
}: {
  spans: Span[]
  onSpanClick?: (id: string) => void
}) {
  const colorMap = useMemo(() => new Map<string, string>(), [])

  const items = useMemo(() => {
    const all: ChatItem[] = []
    const rootSpan = spans.find((s) => s.parent_span_id === null)
    const firstLlmWithInput = spans.find(
      (s) => spanKind(s) === "llm" && s.input_payload
    )
    const userPrompt =
      extractUserPrompt(rootSpan?.input_payload) ??
      extractUserPrompt(firstLlmWithInput?.input_payload)

    if (userPrompt) {
      all.push({
        type: "user",
        content: userPrompt,
        source: rootSpan?.input_payload ? "request" : "first user message",
        time: (rootSpan ?? firstLlmWithInput)?.start_time ?? 0,
      })
    }

    for (const span of spans) {
      const kind = spanKind(span)
      if (span.parent_span_id === null) continue

      if (kind === "llm") {
        if (span.status === "ERROR") {
          all.push({
            type: "error",
            span,
            time: span.end_time ?? span.start_time,
          })
        } else if (span.output_payload) {
          all.push({
            type: "llm",
            span,
            time: span.end_time ?? span.start_time,
          })
        }
      }
    }

    // Collect tools
    const tools = spans.filter(
      (s) => spanKind(s) === "tool" && s.parent_span_id !== null
    )
    if (tools.length > 0) {
      // Group consecutive tools
      const grouped: Span[][] = []
      let current: Span[] = []
      for (const tool of tools) {
        if (
          current.length > 0 &&
          tool.start_time - (current[current.length - 1].end_time ?? 0) > 2000
        ) {
          grouped.push(current)
          current = []
        }
        current.push(tool)
      }
      if (current.length > 0) grouped.push(current)

      for (const group of grouped) {
        all.push({
          type: "tool_group",
          tools: group,
          time: group[0].start_time,
        })
      }
    }

    // For traces without LLM child spans (e.g. agent/workflow traces),
    // show the root span output as the assistant response.
    const hasLlmSpans = spans.some(
      (s) => spanKind(s) === "llm" && s.parent_span_id !== null
    )
    if (!hasLlmSpans) {
      if (rootSpan?.output_payload) {
        all.push({
          type: "llm",
          span: rootSpan,
          time: rootSpan.end_time ?? rootSpan.start_time,
        })
      }
    }

    all.sort((a, b) => a.time - b.time)
    return all
  }, [spans])

  if (items.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-xs text-muted-foreground">
        No conversation data
      </div>
    )
  }

  return (
    <div className="space-y-2 py-2 pb-24">
      <div className="px-3">
        <FlameTimeline
          spans={spans.filter((s) => s.parent_span_id !== null)}
          onSpanClick={onSpanClick}
          compact
        />
      </div>

      {items.map((item, i) => {
        if (item.type === "user") {
          return (
            <div key={`u${i}`} className="px-4 pt-4">
              <UserBubble content={item.content} source={item.source} />
            </div>
          )
        }

        if (item.type === "llm") {
          return (
            <div key={`l${i}`} className="px-4 py-2">
              {item.span.model && (
                <div className="mb-1 font-mono text-[10px] text-muted-foreground">
                  {item.span.model}
                </div>
              )}
              <LLMOutput content={item.span.output_payload ?? ""} />
            </div>
          )
        }

        if (item.type === "error") {
          return (
            <div key={`e${i}`} className="px-4 py-2">
              <div className="inline-flex items-center gap-2 rounded border border-red-500/20 bg-red-500/10 px-3 py-1.5">
                <span className="text-xs font-medium text-red-500">Error</span>
                <span className="max-w-80 truncate font-mono text-xs text-red-400/70">
                  {item.span.output_payload ?? "Unknown error"}
                </span>
              </div>
            </div>
          )
        }

        if (item.type === "tool_group") {
          return (
            <div
              key={`t${i}`}
              className="flex flex-wrap items-center gap-1.5 px-4 py-1"
            >
              {item.tools.map((t) => (
                <ToolCallPill
                  key={t.id}
                  span={t}
                  colorMap={colorMap}
                  onClick={() => onSpanClick?.(t.id)}
                />
              ))}
            </div>
          )
        }

        return null
      })}
    </div>
  )
}

function extractUserPrompt(payload: string | null | undefined): string | null {
  if (!payload) return null
  const parsed = parseMaybeJson(payload)
  const fromMessages = findLastMessageContent(parsed, new Set())
  if (fromMessages) return fromMessages
  return summarizeScalarPayload(parsed ?? payload)
}

function parseMaybeJson(value: unknown): unknown {
  if (typeof value !== "string") return value
  const trimmed = value.trim()
  if (!trimmed) return value
  if (!["{", "["].includes(trimmed[0])) return value
  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

function findLastMessageContent(
  value: unknown,
  visited: Set<unknown>
): string | null {
  const parsed = parseMaybeJson(value)
  if (parsed === null || typeof parsed !== "object") return null
  if (visited.has(parsed)) return null
  visited.add(parsed)

  if (Array.isArray(parsed)) {
    for (let i = parsed.length - 1; i >= 0; i -= 1) {
      const content = findLastMessageContent(parsed[i], visited)
      if (content) return content
    }
    return null
  }

  const record = parsed as Record<string, unknown>
  const role = String(record.role ?? record.type ?? "").toLowerCase()
  const content = contentToText(record.content)
  if (content && ["human", "user"].some((needle) => role.includes(needle))) {
    return content
  }

  for (const key of ["messages", "input", "inputs"]) {
    const content = findLastMessageContent(record[key], visited)
    if (content) return content
  }

  return null
}

function contentToText(value: unknown): string | null {
  const parsed = parseMaybeJson(value)
  if (typeof parsed === "string") return parsed
  if (Array.isArray(parsed)) {
    const parts = parsed
      .map((item) => {
        const record =
          item && typeof item === "object"
            ? (item as Record<string, unknown>)
            : null
        return record
          ? contentToText(record.text ?? record.content)
          : contentToText(item)
      })
      .filter((item): item is string => Boolean(item))
    return parts.length ? parts.join("\n") : null
  }
  return null
}

function summarizeScalarPayload(value: unknown): string | null {
  if (typeof value === "string") return value
  if (Array.isArray(value)) {
    const texts = value
      .map(contentToText)
      .filter((item): item is string => Boolean(item))
    if (texts.length) return texts[texts.length - 1]
  }
  try {
    return JSON.stringify(value)
  } catch {
    return null
  }
}
