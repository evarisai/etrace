import { fmtTimeAgo, fmtDuration, fmtTokens, fmtCost } from "@/lib/helpers"
import { Badge } from "@/components/ui/badge"
import type { Trace } from "@/lib/types"

export function RunListItem({
  trace,
  selected,
  onClick,
}: {
  trace: Trace
  selected: boolean
  onClick: () => void
}) {
  const isRunning = trace.status === "RUNNING"

  return (
    <button
      onClick={onClick}
      className={`w-full border bg-background p-3 text-left transition-all duration-150 ${
        selected
          ? "border-border shadow-[3px_3px_0_0_oklch(0.145_0.006_250_/_0.18)]"
          : "border-border/45 hover:border-border hover:bg-accent/60"
      }`}
    >
      <div className="flex items-start gap-2">
        {isRunning && (
          <div className="mt-1.5 size-2 flex-shrink-0 animate-pulse rounded-full bg-yellow-600" />
        )}
        {trace.status === "ERROR" && (
          <div className="mt-1.5 size-2 flex-shrink-0 rounded-full bg-red-600" />
        )}
        {trace.status === "OK" && (
          <div className="mt-1.5 size-2 flex-shrink-0 rounded-full bg-emerald-600" />
        )}
        <div className="min-w-0 flex-1 overflow-hidden">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-xs font-semibold">{trace.name}</span>
            <Badge
              variant="outline"
              className="h-5 shrink-0 rounded-none border-border bg-card px-1.5 text-[9px]"
            >
              {trace.span_count}
            </Badge>
          </div>
          <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-muted-foreground">
            {trace.model && <span className="font-mono">{trace.model}</span>}
            <span>{fmtDuration(trace.duration_ms)}</span>
            <span>{fmtTimeAgo(trace.start_time)}</span>
          </div>
          {trace.total_cost > 0 && (
            <div className="mt-2 border-t border-border/55 pt-2 text-[10px] text-muted-foreground">
              {fmtTokens(trace.total_input_tokens)} in /{" "}
              {fmtTokens(trace.total_output_tokens)} out /{" "}
              {fmtCost(trace.total_cost)}
            </div>
          )}
        </div>
      </div>
    </button>
  )
}

export function RunList({
  traces,
  selectedId,
  onSelect,
}: {
  traces: Trace[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  return (
    <div className="flex flex-col gap-2 p-3">
      {traces.length === 0 && (
        <div className="py-8 text-center text-xs text-muted-foreground">
          No traces yet
        </div>
      )}
      {traces.map((trace) => (
        <RunListItem
          key={trace.id}
          trace={trace}
          selected={trace.id === selectedId}
          onClick={() => onSelect(trace.id)}
        />
      ))}
    </div>
  )
}
