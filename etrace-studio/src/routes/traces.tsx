import { createFileRoute } from "@tanstack/react-router"
import {
  Activity,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Trash2,
} from "lucide-react"
import { Link } from "@tanstack/react-router"
import { RunList } from "@/components/RunList"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useEffect, useState } from "react"
import { RunDetail } from "@/components/RunDetail"
import { ResizeRail } from "@/components/ResizeRail"
import { fmtCost, fmtDuration, fmtTokens } from "@/lib/helpers"
import { useTraces } from "@/lib/use-traces"

export const Route = createFileRoute("/traces")({
  component: TracesLayout,
})

function TracesLayout() {
  const traces = useTraces()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [navWidth, setNavWidth] = useState(224)
  const [listWidth, setListWidth] = useState(360)
  const [traceListCollapsed, setTraceListCollapsed] = useState(false)

  useEffect(() => {
    if (!selectedId && traces[0]) {
      setSelectedId(traces[0].id)
    }
  }, [selectedId, traces])

  const selected = traces.find((t) => t.id === selectedId)
  const runningCount = traces.filter(
    (trace) => trace.status === "RUNNING"
  ).length
  const errorCount = traces.reduce((sum, trace) => sum + trace.error_count, 0)
  const totalCost = traces.reduce((sum, trace) => sum + trace.total_cost, 0)
  const totalTokens = traces.reduce(
    (sum, trace) => sum + trace.total_input_tokens + trace.total_output_tokens,
    0
  )
  const connected = traces.some(
    (trace) => Date.now() - trace.start_time < 60_000
  )

  async function deleteSelectedTrace(): Promise<void> {
    if (!selectedId) return
    const response = await fetch(
      `/api/traces/${encodeURIComponent(selectedId)}`,
      { method: "DELETE" }
    )
    if (response.ok) {
      const nextTrace = traces.find((trace) => trace.id !== selectedId) ?? null
      setSelectedId(nextTrace?.id ?? null)
    }
  }

  async function deleteAllTraces(): Promise<void> {
    const response = await fetch("/api/traces", { method: "DELETE" })
    if (response.ok) {
      setSelectedId(null)
    }
  }

  return (
    <main className="h-screen overflow-hidden bg-background p-3">
      <div
        className="trace-workspace h-full min-h-0"
        style={
          {
            "--nav-width": `${navWidth}px`,
            "--list-width": traceListCollapsed ? "48px" : `${listWidth}px`,
          } as React.CSSProperties
        }
      >
        <aside className="tp-panel flex min-h-0 flex-col overflow-hidden bg-card">
          <div className="border-b border-border p-3">
            <Link to="/" className="flex items-center gap-2">
              <span className="flex size-9 items-center justify-center border border-border bg-background">
                <img
                  src="/favicon.svg"
                  alt=""
                  className="size-6 object-contain"
                />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold">
                  etrace studio
                </span>
                <span className="block text-[10px] text-muted-foreground">
                  client trace intake
                </span>
              </span>
            </Link>
          </div>
          <div className="grid gap-2 border-b border-border p-3">
            <StatusRow connected={connected} />
            <div className="grid grid-cols-2 gap-2">
              <SideMetric label="traces" value={String(traces.length)} />
              <SideMetric label="running" value={String(runningCount)} />
              <SideMetric label="tokens" value={fmtTokens(totalTokens)} />
              <SideMetric label="cost" value={fmtCost(totalCost)} />
            </div>
          </div>
          <nav className="grid gap-1 p-2 text-xs">
            <Button
              variant="secondary"
              className="justify-start rounded-none border border-border px-2"
            >
              <Activity className="size-4" />
              Traces
            </Button>
          </nav>
          <div className="mt-auto border-t border-border p-3 text-[10px] text-muted-foreground">
            SDKs can post spans here while clients run agents, evals, and tools.
          </div>
        </aside>

        <ResizeRail
          label="Resize navigation"
          value={navWidth}
          min={168}
          max={340}
          onChange={setNavWidth}
        />

        <section className="tp-panel flex min-h-0 flex-col overflow-hidden bg-card">
          {traceListCollapsed ? (
            <CollapsedTraceList
              count={traces.length}
              onExpand={() => setTraceListCollapsed(false)}
            />
          ) : (
            <>
              <div className="border-b border-border p-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h1 className="tp-title">Traces</h1>
                    <p className="text-[10px] text-muted-foreground">
                      {traces.length} traces / {errorCount} errors /{" "}
                      {fmtDuration(selected?.duration_ms ?? null)} selected
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="rounded-none border border-border bg-background"
                    onClick={() => setTraceListCollapsed(true)}
                    aria-label="Collapse traces sidebar"
                  >
                    <PanelLeftClose className="size-4" />
                  </Button>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="min-w-0 justify-start overflow-hidden rounded-none"
                    disabled={!selectedId}
                    onClick={() => void deleteSelectedTrace()}
                  >
                    <Trash2 className="size-3.5" />
                    <span className="min-w-0 truncate">Delete selected</span>
                  </Button>
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    className="min-w-0 justify-start overflow-hidden rounded-none"
                    disabled={traces.length === 0}
                    onClick={() => void deleteAllTraces()}
                  >
                    <Trash2 className="size-3.5" />
                    <span className="min-w-0 truncate">Clear all</span>
                  </Button>
                </div>
                <div className="relative mt-3">
                  <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    aria-label="Search traces"
                    placeholder="search traces"
                    className="h-8 rounded-none border-border bg-background pl-8 text-xs"
                  />
                </div>
              </div>
              <ScrollArea className="min-h-0 flex-1">
                <RunList
                  traces={traces}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                />
              </ScrollArea>
            </>
          )}
        </section>

        {traceListCollapsed ? (
          <div className="hidden md:block" />
        ) : (
          <ResizeRail
            label="Resize trace list"
            value={listWidth}
            min={280}
            max={560}
            onChange={setListWidth}
            className="hidden md:block"
          />
        )}

        <section className="tp-panel min-w-0 overflow-hidden bg-card">
          {selected ? (
            <RunDetail key={selected.id} trace={selected} />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Select a trace to view
            </div>
          )}
        </section>
      </div>
    </main>
  )
}

function CollapsedTraceList({
  count,
  onExpand,
}: {
  count: number
  onExpand: () => void
}) {
  return (
    <div className="flex h-full flex-col items-center border-border bg-card">
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="mt-2 rounded-none border border-border bg-background"
        onClick={onExpand}
        aria-label="Expand traces sidebar"
      >
        <PanelLeftOpen className="size-4" />
      </Button>
      <div className="mt-4 flex rotate-180 items-center gap-2 text-[10px] font-semibold tracking-normal text-muted-foreground uppercase [writing-mode:vertical-rl]">
        traces
        <span className="border border-border bg-background px-1 py-0.5 text-foreground">
          {count}
        </span>
      </div>
    </div>
  )
}

function StatusRow({ connected }: { connected: boolean }) {
  return (
    <div className="flex items-center justify-between border border-border bg-background p-2">
      <span className="text-[10px] text-muted-foreground">receiver</span>
      <span className="flex items-center gap-2 text-xs font-semibold">
        <span
          className={`size-2 rounded-full ${connected ? "bg-emerald-600" : "bg-red-600"}`}
        />
        {connected ? "connected" : "disconnected"}
      </span>
    </div>
  )
}

function SideMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-border bg-background p-2">
      <div className="tp-label">{label}</div>
      <div className="mt-1 truncate text-xs font-semibold">{value}</div>
    </div>
  )
}
