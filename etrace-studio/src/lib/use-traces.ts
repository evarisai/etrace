import { useEffect, useState } from "react"
import type { Trace } from "./types"

export function useTraces(pollMs = 1500): Trace[] {
  const [traces, setTraces] = useState<Trace[]>([])

  useEffect(() => {
    let active = true

    async function load(): Promise<void> {
      try {
        const response = await fetch("/api/traces", {
          headers: { accept: "application/json" },
        })
        if (!response.ok) return
        const payload: unknown = await response.json()
        if (active && isTraceArray(payload)) {
          setTraces(payload)
        }
      } catch {
        // The status indicator already shows disconnected when no fresh traces arrive.
      }
    }

    void load()
    const interval = window.setInterval(() => void load(), pollMs)
    return () => {
      active = false
      window.clearInterval(interval)
    }
  }, [pollMs])

  return traces
}

function isTraceArray(value: unknown): value is Trace[] {
  return Array.isArray(value) && value.every(isTrace)
}

function isTrace(value: unknown): value is Trace {
  if (!value || typeof value !== "object") return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.id === "string" &&
    typeof candidate.name === "string" &&
    typeof candidate.start_time === "number" &&
    Array.isArray(candidate.spans)
  )
}
