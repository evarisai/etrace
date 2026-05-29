import { useState } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Activity, MessageSquare, GitBranch } from "lucide-react"
import { SpanTree } from "./SpanTree"
import { ChatFlow } from "./ChatFlow"
import { FlameTimeline } from "./FlameTimeline"
import { fmtDuration, fmtTokens, fmtCost } from "@/lib/helpers"
import type { Trace } from "@/lib/types"

function StatsLine({ trace }: { trace: Trace }) {
  return (
    <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] text-muted-foreground">
      <span>{trace.span_count} spans</span>
      <span>/</span>
      <span>{fmtDuration(trace.duration_ms)}</span>
      {(trace.total_input_tokens > 0 || trace.total_output_tokens > 0) && (
        <>
          <span>/</span>
          <span>
            {fmtTokens(trace.total_input_tokens)} in /{" "}
            {fmtTokens(trace.total_output_tokens)} out
          </span>
        </>
      )}
      {trace.total_cost > 0 && (
        <>
          <span>/</span>
          <span>{fmtCost(trace.total_cost)}</span>
        </>
      )}
      {trace.error_count > 0 && (
        <>
          <span>/</span>
          <Badge
            variant="outline"
            className="h-4 rounded-none border-red-700/40 bg-red-50 text-[9px] text-red-700"
          >
            {trace.error_count} error{trace.error_count > 1 ? "s" : ""}
          </Badge>
        </>
      )}
    </div>
  )
}

export function RunDetail({ trace }: { trace: Trace }) {
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null)

  return (
    <div className="flex h-full flex-col">
      <div className="flex-shrink-0 border-b border-border bg-card px-4 py-3">
        <div className="mb-2 flex items-center gap-2">
          <h2 className="truncate text-sm font-semibold">{trace.name}</h2>
          {trace.status === "RUNNING" && (
            <Badge
              variant="outline"
              className="h-5 rounded-none border-yellow-700/40 bg-yellow-50 text-[9px] text-yellow-700"
            >
              running
            </Badge>
          )}
          {trace.status === "ERROR" && (
            <Badge
              variant="outline"
              className="h-5 rounded-none border-red-700/40 bg-red-50 text-[9px] text-red-700"
            >
              error
            </Badge>
          )}
          {trace.model && (
            <Badge
              variant="outline"
              className="h-5 rounded-none border-border bg-background font-mono text-[9px]"
            >
              {trace.model}
            </Badge>
          )}
        </div>
        <StatsLine trace={trace} />
      </div>

      <Tabs defaultValue="overview" className="flex min-h-0 flex-1 flex-col">
        <div className="flex-shrink-0 border-b border-border bg-background/55 px-4">
          <TabsList className="h-10 gap-1 rounded-none bg-transparent p-0">
            <TabsTrigger
              value="overview"
              className="gap-1.5 rounded-none border border-transparent px-2 text-xs data-[state=active]:border-border data-[state=active]:bg-card"
            >
              <MessageSquare className="size-3" />
              Overview
            </TabsTrigger>
            <TabsTrigger
              value="spans"
              className="gap-1.5 rounded-none border border-transparent px-2 text-xs data-[state=active]:border-border data-[state=active]:bg-card"
            >
              <GitBranch className="size-3" />
              Spans
            </TabsTrigger>
            <TabsTrigger
              value="timeline"
              className="gap-1.5 rounded-none border border-transparent px-2 text-xs data-[state=active]:border-border data-[state=active]:bg-card"
            >
              <Activity className="size-3" />
              Timeline
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="overview" className="m-0 min-h-0 flex-1">
          <ScrollArea className="h-full">
            <ChatFlow spans={trace.spans} onSpanClick={setSelectedSpanId} />
          </ScrollArea>
        </TabsContent>

        <TabsContent value="spans" className="m-0 min-h-0 flex-1">
          <SpanTree
            spans={trace.spans}
            selectedId={selectedSpanId}
            onSelect={setSelectedSpanId}
          />
        </TabsContent>

        <TabsContent value="timeline" className="m-0 min-h-0 flex-1">
          <ScrollArea className="h-full">
            <div className="p-4">
              <FlameTimeline
                spans={trace.spans}
                onSpanClick={setSelectedSpanId}
              />
            </div>
          </ScrollArea>
        </TabsContent>
      </Tabs>
    </div>
  )
}
