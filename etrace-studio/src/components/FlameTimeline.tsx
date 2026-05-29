import { useMemo } from "react"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { spanColor, fmtDuration } from "@/lib/helpers"
import type { Span } from "@/lib/types"

type TimelineItem = {
  span: Span
  left: number
  width: number
  color: string
  lane: number
}

export function FlameTimeline({
  spans,
  onSpanClick,
  compact = false,
  maxRows = compact ? 4 : Number.POSITIVE_INFINITY,
}: {
  spans: Span[]
  onSpanClick?: (id: string) => void
  compact?: boolean
  maxRows?: number
}) {
  const colorMap = useMemo(() => new Map<string, string>(), [])

  const { timeline, hiddenCount } = useMemo(() => {
    if (spans.length === 0)
      return { timeline: [] as TimelineItem[], hiddenCount: 0 }
    const minTime = Math.min(...spans.map((s) => s.start_time))
    const maxTime = Math.max(
      ...spans.map((s) => s.end_time ?? s.start_time + 1)
    )
    const range = maxTime - minTime || 1

    const laneEnds: number[] = []
    let hidden = 0
    const items: TimelineItem[] = []

    spans
      .filter((s) => s.duration_ms !== null)
      .sort(
        (a, b) =>
          a.start_time - b.start_time ||
          (b.duration_ms ?? 0) - (a.duration_ms ?? 0)
      )
      .forEach((s) => {
        const left = ((s.start_time - minTime) / range) * 100
        const width = Math.max(
          ((s.end_time! - s.start_time) / range) * 100,
          0.5
        )
        const color = spanColor(s.name, colorMap)
        const lane = laneEnds.findIndex((end) => s.start_time >= end)
        const nextLane = lane === -1 ? laneEnds.length : lane
        if (nextLane >= maxRows) {
          hidden += 1
          return
        }
        laneEnds[nextLane] = s.end_time ?? s.start_time
        items.push({ span: s, left, width, color, lane: nextLane })
      })

    return { timeline: items, hiddenCount: hidden }
  }, [spans, colorMap, maxRows])

  if (!timeline || timeline.length === 0) return null

  if (compact) {
    const laneCount = Math.max(1, ...timeline.map((item) => item.lane + 1))
    return (
      <div className="rounded border border-border bg-muted/20 px-2 py-1.5">
        <div className="relative" style={{ height: laneCount * 16 }}>
          {timeline.map(({ span: s, left, width, color, lane }) => (
            <Tooltip key={s.id}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  className="absolute h-2.5 cursor-pointer rounded-sm transition-opacity hover:opacity-80"
                  style={{
                    top: lane * 16 + 3,
                    left: `${left}%`,
                    width: `${width}%`,
                    minWidth: 4,
                    background: `color-mix(in srgb, ${color} 34%, transparent)`,
                    borderLeft: `2px solid ${color}`,
                  }}
                  onClick={() => onSpanClick?.(s.id)}
                  aria-label={`Select span ${s.name}`}
                />
              </TooltipTrigger>
              <TooltipContent side="top" className="text-xs">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-semibold">{s.name}</span>
                  <span className="text-muted-foreground">
                    {fmtDuration(s.duration_ms)}
                  </span>
                  {s.model && (
                    <span className="text-muted-foreground">• {s.model}</span>
                  )}
                </div>
              </TooltipContent>
            </Tooltip>
          ))}
        </div>
        {hiddenCount > 0 && (
          <div className="mt-1 border-t border-border pt-1 font-mono text-[10px] text-muted-foreground">
            +{hiddenCount} more spans in detailed waterfall
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-0.5 py-1">
      {timeline.map(({ span: s, left, width, color }) => (
        <Tooltip key={s.id}>
          <TooltipTrigger asChild>
            <div className="group relative flex h-5 items-center">
              <div className="absolute inset-0 flex">
                <div
                  className="relative flex cursor-pointer items-center overflow-hidden rounded-sm transition-opacity hover:opacity-80"
                  style={{
                    marginLeft: `${left}%`,
                    width: `${width}%`,
                    background: `color-mix(in srgb, ${color} 20%, transparent)`,
                    borderLeft: `2px solid ${color}`,
                  }}
                  onClick={() => onSpanClick?.(s.id)}
                >
                  {width > 8 && (
                    <span className="truncate px-1 font-mono text-[9px] whitespace-nowrap text-foreground/80">
                      {s.name}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </TooltipTrigger>
          <TooltipContent side="top" className="text-xs">
            <div className="flex items-center gap-2">
              <span className="font-mono font-semibold">{s.name}</span>
              <span className="text-muted-foreground">
                {fmtDuration(s.duration_ms)}
              </span>
              {s.model && (
                <span className="text-muted-foreground">• {s.model}</span>
              )}
            </div>
          </TooltipContent>
        </Tooltip>
      ))}
    </div>
  )
}
