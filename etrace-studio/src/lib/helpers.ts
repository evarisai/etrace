import type { Trace, Span } from "./types"

// Span color palette (12 colors, rotating by name hash)
const PALETTE = [
  "#e06c75",
  "#98c379",
  "#e5c07b",
  "#61afef",
  "#c678dd",
  "#56b6c2",
  "#d19a66",
  "#be5046",
  "#7ec699",
  "#f99157",
  "#80cbc4",
  "#ffcb6b",
]

export function spanColor(name: string, cache?: Map<string, string>): string {
  if (cache?.has(name)) return cache.get(name)!
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) | 0
  }
  const color = PALETTE[Math.abs(hash) % PALETTE.length]
  cache?.set(name, color)
  return color
}

export function fmtDuration(ms: number | null): string {
  if (ms === null) return "—"
  if (ms < 1) return `${ms.toFixed(2)}ms`
  if (ms < 1000) return `${ms.toFixed(0)}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const mins = Math.floor(ms / 60_000)
  const secs = ((ms % 60_000) / 1000).toFixed(0)
  return `${mins}m${secs}s`
}

export function fmtCost(cost: number | null): string {
  if (cost === null || cost === 0) return "—"
  if (cost < 0.0001) return "<$0.0001"
  if (cost < 0.01) return `$${cost.toFixed(4)}`
  if (cost < 1) return `$${cost.toFixed(3)}`
  return `$${cost.toFixed(2)}`
}

export function fmtTokens(n: number | null): string {
  if (n === null) return "—"
  if (n < 1000) return String(n)
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`
  return `${(n / 1_000_000).toFixed(1)}M`
}

export function fmtTime(ts: number): string {
  const d = new Date(ts)
  return d.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

export function fmtTimeAgo(ts: number): string {
  const diff = Date.now() - ts
  if (diff < 60_000) return "just now"
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return `${Math.floor(diff / 86_400_000)}d ago`
}

export function getChildren(spans: Span[], parentId: string): Span[] {
  return spans.filter((s) => s.parent_span_id === parentId)
}

export function getRootSpan(trace: Trace): Span | undefined {
  return trace.spans.find((s) => s.id === trace.root_span_id)
}

export function buildTree(spans: Span[]): Map<string | null, Span[]> {
  const tree = new Map<string | null, Span[]>()
  for (const span of spans) {
    const parent = span.parent_span_id ?? null
    const children = tree.get(parent) ?? []
    children.push(span)
    tree.set(parent, children)
  }
  return tree
}
