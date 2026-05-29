import { Link, createFileRoute } from "@tanstack/react-router"
import { ArrowRight, CircleDot, RadioTower } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { fmtDuration, fmtTimeAgo } from "@/lib/helpers"
import { useTraces } from "@/lib/use-traces"

export const Route = createFileRoute("/")({
  component: IndexPage,
})

function IndexPage() {
  const traces = useTraces()
  const lastTrace = traces[0] ?? null
  const isConnected = Boolean(
    lastTrace && Date.now() - lastTrace.start_time < 60_000
  )

  return (
    <main className="min-h-screen p-4 text-foreground md:p-8">
      <section className="tp-panel mx-auto flex min-h-[calc(100vh-4rem)] max-w-6xl flex-col justify-between gap-8 bg-background/95 p-5 md:p-8">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-5">
          <div className="flex items-center gap-3">
            <div className="flex size-11 items-center justify-center border border-border bg-card">
              <img
                src="/favicon.svg"
                alt=""
                className="size-7 object-contain"
              />
            </div>
            <div>
              <h1 className="font-heading text-xl leading-none font-semibold md:text-3xl">
                etrace studio
              </h1>
              <p className="mt-1 text-xs text-muted-foreground">
                Trace intake and inspection console
              </p>
            </div>
          </div>
          <Badge
            variant="outline"
            className="h-8 gap-2 rounded-none border-border bg-card px-3 font-mono text-xs"
          >
            <span
              className={`size-2 rounded-full ${isConnected ? "bg-emerald-600" : "bg-red-600"}`}
            />
            {isConnected ? "connected" : "disconnected"}
          </Badge>
        </header>

        <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
          <div className="flex min-h-[360px] flex-col justify-between border border-border bg-card p-5">
            <div>
              <div className="mb-6 inline-flex items-center gap-2 border border-border bg-background px-2 py-1 text-[10px] text-muted-foreground">
                <RadioTower className="size-3" />
                live trace receiver
              </div>
              <h2 className="max-w-3xl font-heading text-3xl leading-tight font-semibold md:text-5xl">
                Inspect client traces as they arrive.
              </h2>
              <p className="mt-5 max-w-2xl text-sm leading-6 text-muted-foreground">
                Send spans from SDKs or OpenTelemetry exporters, then use etrace
                studio to review requests, tool calls, model usage, cost,
                latency, and errors.
              </p>
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button asChild className="rounded-none">
                <Link to="/traces">
                  Open studio
                  <ArrowRight className="size-4" />
                </Link>
              </Button>
              <div className="text-xs text-muted-foreground">
                {traces.length} traces cached locally
              </div>
            </div>
          </div>

          <aside className="grid gap-4">
            <div className="tp-panel-soft p-4">
              <div className="tp-label">receiver status</div>
              <div className="mt-4 flex items-center justify-between gap-4">
                <div className="flex items-center gap-2">
                  <CircleDot
                    className={
                      isConnected
                        ? "size-4 text-emerald-700"
                        : "size-4 text-red-700"
                    }
                  />
                  <span className="text-sm font-semibold">
                    {isConnected ? "receiving traces" : "waiting for traces"}
                  </span>
                </div>
                <span className="text-xs text-muted-foreground">
                  {lastTrace ? fmtTimeAgo(lastTrace.start_time) : "never"}
                </span>
              </div>
            </div>
            <div className="tp-panel-soft p-4">
              <div className="tp-label">latest trace</div>
              {lastTrace ? (
                <div className="mt-4 space-y-3">
                  <div className="truncate text-sm font-semibold">
                    {lastTrace.name}
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <Metric
                      label="spans"
                      value={String(lastTrace.span_count)}
                    />
                    <Metric
                      label="latency"
                      value={fmtDuration(lastTrace.duration_ms)}
                    />
                    <Metric
                      label="status"
                      value={lastTrace.status.toLowerCase()}
                    />
                  </div>
                </div>
              ) : (
                <div className="mt-4 text-sm text-muted-foreground">
                  No traces yet
                </div>
              )}
            </div>
            <div className="tp-hatch min-h-24 border border-border" />
          </aside>
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5 text-[10px] text-muted-foreground">
          <span>client traces / spans / model costs / tool calls</span>
          <span>etrace studio</span>
        </footer>
      </section>
    </main>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-border bg-background p-2">
      <div className="tp-label">{label}</div>
      <div className="mt-1 truncate text-xs font-semibold">{value}</div>
    </div>
  )
}
