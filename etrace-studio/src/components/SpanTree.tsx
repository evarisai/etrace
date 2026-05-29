import { useState, useMemo } from "react"
import { PanelRightClose, PanelRightOpen } from "lucide-react"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Button } from "@/components/ui/button"
import { KindBadge, StatusBadge } from "./SpanBadges"
import { JsonView } from "./JsonView"
import { ResizeRail } from "./ResizeRail"
import { spanColor, fmtDuration, buildTree } from "@/lib/helpers"
import type { Span } from "@/lib/types"

function SpanRow({
  span,
  children,
  tree,
  depth,
  selectedId,
  onSelect,
  timeRange,
  colorMap,
}: {
  span: Span
  children: Span[]
  tree: Map<string | null, Span[]>
  depth: number
  selectedId: string | null
  onSelect: (id: string) => void
  timeRange: [number, number]
  colorMap: Map<string, string>
}) {
  const [open, setOpen] = useState(depth < 2)
  const selected = selectedId === span.id
  const hasChildren = children.length > 0
  const range = timeRange[1] - timeRange[0] || 1
  const barLeft = ((span.start_time - timeRange[0]) / range) * 100
  const barWidth = Math.max(
    ((span.end_time! - span.start_time) / range) * 100,
    0.5
  )
  const color = spanColor(span.name, colorMap)

  return (
    <div>
      <div
        className={`flex cursor-pointer items-center gap-1 transition-colors hover:bg-accent/50 ${
          selected ? "bg-accent" : ""
        }`}
        style={{ paddingLeft: depth * 20 + 4, height: 28 }}
        onClick={() => onSelect(span.id)}
      >
        {hasChildren ? (
          <button
            onClick={(e) => {
              e.stopPropagation()
              setOpen(!open)
            }}
            className="flex h-4 w-4 items-center justify-center text-muted-foreground hover:text-foreground"
          >
            <span
              className={`text-[10px] transition-transform ${open ? "rotate-90" : ""}`}
            >
              ▶
            </span>
          </button>
        ) : (
          <span className="w-4" />
        )}

        <KindBadge span={span} />
        <StatusBadge span={span} />

        <Tooltip>
          <TooltipTrigger asChild>
            <span className="min-w-0 flex-1 truncate font-mono text-xs font-medium">
              {span.name}
            </span>
          </TooltipTrigger>
          <TooltipContent className="max-w-80 text-xs">
            <span className="font-mono">{span.name}</span>
            {span.model && (
              <span className="text-muted-foreground"> • {span.model}</span>
            )}
          </TooltipContent>
        </Tooltip>

        {/* Mini timeline bar */}
        <div className="relative h-3 w-24 flex-shrink-0 rounded-sm bg-muted/30">
          <div
            className="absolute top-0 h-full rounded-sm"
            style={{
              left: `${barLeft}%`,
              width: `${barWidth}%`,
              background: `color-mix(in srgb, ${color} 40%, transparent)`,
              borderLeft: `1px solid ${color}`,
            }}
          />
        </div>

        <span className="w-14 flex-shrink-0 text-right font-mono text-[10px] text-muted-foreground">
          {fmtDuration(span.duration_ms)}
        </span>
      </div>

      {open &&
        hasChildren &&
        children.map((child) => (
          <SpanRow
            key={child.id}
            span={child}
            children={tree.get(child.id) ?? []}
            tree={tree}
            depth={depth + 1}
            selectedId={selectedId}
            onSelect={onSelect}
            timeRange={timeRange}
            colorMap={colorMap}
          />
        ))}
    </div>
  )
}

function SpanDetailPanel({ span }: { span: Span }) {
  return (
    <div className="w-full min-w-0 max-w-full space-y-3 overflow-hidden p-3 text-xs">
      <div className="flex min-w-0 items-center gap-2">
        <span className="min-w-0 truncate font-mono font-semibold">
          {span.name}
        </span>
      </div>

      {/* Meta grid */}
      <div className="grid min-w-0 max-w-full grid-cols-[minmax(82px,auto)_minmax(0,1fr)] gap-x-4 gap-y-1 overflow-hidden text-[11px]">
        <div className="text-muted-foreground">Span ID</div>
        <div className="truncate font-mono">{span.id}</div>
        {span.parent_span_id && (
          <>
            <div className="text-muted-foreground">Parent</div>
            <div className="truncate font-mono">{span.parent_span_id}</div>
          </>
        )}
        <div className="text-muted-foreground">Duration</div>
        <div className="min-w-0 truncate font-mono">
          {fmtDuration(span.duration_ms)}
        </div>
        {span.model && (
          <>
            <div className="text-muted-foreground">Model</div>
            <div className="min-w-0 truncate font-mono">{span.model}</div>
          </>
        )}
        {span.provider && (
          <>
            <div className="text-muted-foreground">Provider</div>
            <div className="min-w-0 truncate font-mono">{span.provider}</div>
          </>
        )}
        {span.input_tokens !== null && (
          <>
            <div className="text-muted-foreground">Input Tokens</div>
            <div className="min-w-0 truncate font-mono">
              {span.input_tokens.toLocaleString()}
            </div>
          </>
        )}
        {span.output_tokens !== null && (
          <>
            <div className="text-muted-foreground">Output Tokens</div>
            <div className="min-w-0 truncate font-mono">
              {span.output_tokens.toLocaleString()}
            </div>
          </>
        )}
        {span.total_cost !== null && (
          <>
            <div className="text-muted-foreground">Cost</div>
            <div className="min-w-0 truncate font-mono">
              ${span.total_cost.toFixed(4)}
            </div>
          </>
        )}
      </div>

      {/* Input */}
      {span.input_payload && (
        <PayloadSection
          title="Input"
          data={span.input_payload}
          defaultOpen={false}
        />
      )}

      {/* Output */}
      {span.output_payload && (
        <PayloadSection title="Output" data={span.output_payload} defaultOpen />
      )}

      {/* Attributes */}
      {Object.keys(span.attributes).length > 0 && (
        <PayloadSection
          title="Attributes"
          data={span.attributes}
          defaultOpen={false}
        />
      )}
    </div>
  )
}

function PayloadSection({
  title,
  data,
  defaultOpen = false,
}: {
  title: string
  data: unknown
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const summary = summarizePayload(data)

  return (
    <div className="min-w-0 max-w-full overflow-hidden border border-border bg-muted/20">
      <button
        type="button"
        className="flex w-full min-w-0 max-w-full items-center gap-2 px-2 py-1.5 text-left"
        onClick={() => setOpen((value) => !value)}
      >
        <span
          className={`text-[10px] text-muted-foreground transition-transform ${open ? "rotate-90" : ""}`}
        >
          ▶
        </span>
        <span className="shrink-0 text-[10px] font-medium tracking-wider text-muted-foreground uppercase">
          {title}
        </span>
        {!open && (
          <span className="min-w-0 flex-1 overflow-hidden font-mono text-[10px] text-muted-foreground">
            {summary}
          </span>
        )}
      </button>
      {open && (
        <div className="max-h-72 min-w-0 max-w-full contain-inline-size overflow-y-auto overflow-x-hidden border-t border-border bg-background/60 p-2">
          <JsonView data={data} />
        </div>
      )}
    </div>
  )
}

function summarizePayload(data: unknown): string {
  if (typeof data === "string") {
    const normalized = data.replace(/\s+/g, " ").trim()
    return normalized.length > 120
      ? `${normalized.slice(0, 120)}…`
      : normalized || "empty"
  }
  if (Array.isArray(data))
    return `${data.length} item${data.length === 1 ? "" : "s"}`
  if (data && typeof data === "object") {
    const keys = Object.keys(data as Record<string, unknown>)
    return `${keys.length} key${keys.length === 1 ? "" : "s"}${keys.length ? `: ${keys.slice(0, 4).join(", ")}` : ""}`
  }
  return String(data)
}

export function SpanTree({
  spans,
  selectedId,
  onSelect,
}: {
  spans: Span[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const colorMap = useMemo(() => new Map<string, string>(), [])
  const [detailWidth, setDetailWidth] = useState(360)
  const [detailCollapsed, setDetailCollapsed] = useState(false)

  const { tree, roots, timeRange } = useMemo(() => {
    const tree = buildTree(spans)
    const roots = tree.get(null) ?? []
    const allStarts = spans.map((s) => s.start_time)
    const allEnds = spans.map((s) => s.end_time ?? s.start_time + 1)
    const timeRange: [number, number] = [
      Math.min(...allStarts),
      Math.max(...allEnds),
    ]
    return { tree, roots, timeRange }
  }, [spans])

  const selected = selectedId ? spans.find((s) => s.id === selectedId) : null

  return (
    <div className="flex h-full min-w-0 overflow-hidden">
      <ScrollArea className="min-w-0 flex-1">
        <div className="py-1">
          {roots.map((root) => (
            <SpanRow
              key={root.id}
              span={root}
              children={tree.get(root.id) ?? []}
              tree={tree}
              depth={0}
              selectedId={selectedId}
              onSelect={onSelect}
              timeRange={timeRange}
              colorMap={colorMap}
            />
          ))}
        </div>
      </ScrollArea>

      {detailCollapsed ? (
        <CollapsedSpanPanel
          hasSelection={Boolean(selected)}
          onExpand={() => setDetailCollapsed(false)}
        />
      ) : (
        <>
          <ResizeRail
            label="Resize span detail panel"
            value={detailWidth}
            min={280}
            max={620}
            direction="inverse"
            onChange={setDetailWidth}
            className="hidden md:block"
          />
          <div
            className="min-w-0 max-w-[70%] flex-shrink overflow-hidden border-l border-border bg-card md:flex-shrink-0"
            style={{ width: `min(${detailWidth}px, 70%)` }}
          >
            <div className="flex h-10 items-center justify-between border-b border-border px-3">
              <span className="text-xs font-semibold">Span detail</span>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="rounded-none border border-border bg-background"
                onClick={() => setDetailCollapsed(true)}
                aria-label="Collapse span detail panel"
              >
                <PanelRightClose className="size-4" />
              </Button>
            </div>
            {selected ? (
              <ScrollArea className="h-[calc(100%-2.5rem)]">
                <SpanDetailPanel span={selected} />
              </ScrollArea>
            ) : (
              <div className="flex h-[calc(100%-2.5rem)] items-center justify-center text-xs text-muted-foreground">
                Select a span to view details
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function CollapsedSpanPanel({
  hasSelection,
  onExpand,
}: {
  hasSelection: boolean
  onExpand: () => void
}) {
  return (
    <div className="flex h-full w-12 flex-shrink-0 flex-col items-center border-l border-border bg-card">
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="mt-2 rounded-none border border-border bg-background"
        onClick={onExpand}
        aria-label="Expand span detail panel"
      >
        <PanelRightOpen className="size-4" />
      </Button>
      <div className="mt-4 flex rotate-180 items-center gap-2 text-[10px] font-semibold tracking-normal text-muted-foreground uppercase [writing-mode:vertical-rl]">
        span detail
        <span className="border border-border bg-background px-1 py-0.5 text-foreground">
          {hasSelection ? "1" : "0"}
        </span>
      </div>
    </div>
  )
}
