import { Badge } from "@/components/ui/badge"
import { spanColor, fmtDuration } from "@/lib/helpers"
import { spanKind } from "@/lib/types"
import type { Span } from "@/lib/types"

const KIND_STYLES: Record<string, string> = {
  llm: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  tool: "bg-amber-500/10 text-amber-500 border-amber-500/20",
  trace: "bg-purple-500/10 text-purple-500 border-purple-500/20",
  other: "bg-muted text-muted-foreground border-border",
}

export function KindBadge({ span }: { span: Span }) {
  const kind = spanKind(span)
  return (
    <Badge
      variant="outline"
      className={`border px-1.5 py-0 font-mono text-[9px] uppercase ${KIND_STYLES[kind]}`}
    >
      {kind}
    </Badge>
  )
}

export function StatusBadge({ span }: { span: Span }) {
  if (span.status === "OK") return null
  const isError = span.status === "ERROR"
  return (
    <Badge
      variant="outline"
      className={`border px-1.5 py-0 font-mono text-[9px] ${
        isError
          ? "border-red-500/20 bg-red-500/10 text-red-500"
          : "border-yellow-500/20 bg-yellow-500/10 text-yellow-500"
      }`}
    >
      {span.status.toLowerCase()}
    </Badge>
  )
}

export function ToolCallPill({
  span,
  colorMap,
  onClick,
}: {
  span: Span
  colorMap: Map<string, string>
  onClick?: () => void
}) {
  const color = spanColor(span.name, colorMap)
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 font-mono text-xs transition-colors hover:opacity-80"
      style={{
        background: `color-mix(in srgb, ${color} 10%, transparent)`,
        border: `1px solid color-mix(in srgb, ${color} 20%, transparent)`,
        color,
      }}
    >
      <span className="font-semibold">{span.name}</span>
      <span className="text-[10px] text-muted-foreground">
        {fmtDuration(span.duration_ms)}
      </span>
      {span.status === "ERROR" && (
        <span className="text-[10px] text-red-500">✗</span>
      )}
    </button>
  )
}
