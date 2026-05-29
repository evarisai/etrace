import { useState, useCallback, useMemo } from "react"

const MONO =
  "'JetBrains Mono Variable', ui-monospace, SFMono-Regular, monospace"

type JsonValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | JsonValue[]
  | { [key: string]: JsonValue }

function isObject(v: JsonValue): v is { [key: string]: JsonValue } {
  return v !== null && typeof v === "object" && !Array.isArray(v)
}

function ExpandableString({ value }: { value: string }) {
  const [expanded, setExpanded] = useState(false)
  const display = expanded ? value : value.slice(0, 300) + "…"
  return (
    <>
      <span className="text-amber-700 dark:text-amber-300">
        &quot;{display}&quot;
      </span>
      <button
        onClick={(e) => {
          e.stopPropagation()
          setExpanded(!expanded)
        }}
        className="ml-1 text-[10px] text-primary hover:underline"
      >
        {expanded ? "less" : "more"}
      </button>
    </>
  )
}

function JsonNode({
  name,
  value,
  depth,
  isLast,
}: {
  name?: string | number
  value: JsonValue
  depth: number
  isLast: boolean
}) {
  const [open, setOpen] = useState(depth < 2)
  const indent = depth * 16
  const trail = isLast ? "" : ","

  const isArr = Array.isArray(value)
  const isObj = isObject(value)
  const expandable = isArr || isObj
  const entries: [string | number, JsonValue][] = isArr
    ? value.map((v, i) => [i, v])
    : isObj
      ? Object.entries(value)
      : []
  const br = isArr ? ["[", "]"] : ["{", "}"]

  const keyEl = name !== undefined && (
    <>
      <span
        className={
          typeof name === "number"
            ? "text-muted-foreground"
            : "font-semibold text-foreground"
        }
      >
        {name}
      </span>
      <span className="text-muted-foreground">: </span>
    </>
  )

  if (!expandable) {
    let val: React.ReactNode
    let cls = "text-muted-foreground"
    if (value === null) {
      val = "null"
      cls = "italic text-muted-foreground"
    } else if (value === undefined) {
      val = "undefined"
      cls = "italic text-muted-foreground"
    } else if (typeof value === "boolean") {
      val = String(value)
      cls = "text-sky-600 dark:text-sky-400"
    } else if (typeof value === "number") {
      val = String(value)
      cls = "text-sky-600 dark:text-sky-400"
    } else if (typeof value === "string") {
      val =
        value.length > 300 ? (
          <ExpandableString value={value} />
        ) : (
          <>&quot;{value}&quot;</>
        )
      cls = "text-amber-700 dark:text-amber-300"
    } else {
      val = String(value)
    }

    return (
      <div
        style={{ paddingLeft: indent }}
        className="mt-0.5 min-w-0 [overflow-wrap:anywhere] break-words"
      >
        {keyEl}
        <span className={cls}>{val}</span>
        <span className="text-muted-foreground">{trail}</span>
      </div>
    )
  }

  if (entries.length === 0) {
    return (
      <div style={{ paddingLeft: indent }}>
        {keyEl}
        <span className="text-muted-foreground">
          {br[0]}
          {br[1]}
        </span>
        <span className="text-muted-foreground">{trail}</span>
      </div>
    )
  }

  if (!open) {
    return (
      <div
        style={{ paddingLeft: indent }}
        className="min-w-0 cursor-pointer [overflow-wrap:anywhere] break-words"
        onClick={(e) => {
          e.stopPropagation()
          setOpen(true)
        }}
      >
        <span className="mr-1 inline-block text-muted-foreground transition-transform">
          ▶
        </span>
        {keyEl}
        <span className="text-muted-foreground">{br[0]}</span>
        <span className="mx-1 text-[10px] text-muted-foreground">
          {entries.length}{" "}
          {isArr
            ? entries.length === 1
              ? "item"
              : "items"
            : entries.length === 1
              ? "key"
              : "keys"}
        </span>
        <span className="text-muted-foreground">{br[1]}</span>
        <span className="text-muted-foreground">{trail}</span>
      </div>
    )
  }

  return (
    <div>
      <div
        style={{ paddingLeft: indent }}
        className="min-w-0 cursor-pointer [overflow-wrap:anywhere] break-words"
        onClick={(e) => {
          e.stopPropagation()
          setOpen(false)
        }}
      >
        <span className="mr-1 inline-block rotate-90 text-muted-foreground transition-transform">
          ▶
        </span>
        {keyEl}
        <span className="text-muted-foreground">{br[0]}</span>
      </div>
      <div className="relative">
        <div
          className="absolute cursor-pointer border-l border-border hover:border-muted-foreground/30"
          style={{ top: 0, bottom: 0, left: indent + 5, width: 8 }}
          onClick={(e) => {
            e.stopPropagation()
            setOpen(false)
          }}
        />
        {entries.map(([k, v], i) => (
          <JsonNode
            key={typeof k === "number" ? i : k}
            name={k}
            value={v}
            depth={depth + 1}
            isLast={i === entries.length - 1}
          />
        ))}
      </div>
      <div style={{ paddingLeft: indent + 10 }}>
        <span className="text-muted-foreground">{br[1]}</span>
        <span className="text-muted-foreground">{trail}</span>
      </div>
    </div>
  )
}

export function JsonView({ data }: { data: unknown; maxExpand?: number }) {
  const parseDeep = useCallback((v: unknown): unknown => {
    if (typeof v === "string") {
      const s = v.trim()
      if (
        (s[0] === "{" && s[s.length - 1] === "}") ||
        (s[0] === "[" && s[s.length - 1] === "]")
      ) {
        try {
          const p = JSON.parse(s)
          if (p && typeof p === "object") return parseDeep(p)
        } catch {
          /* not JSON */
        }
      }
      return v
    }
    if (Array.isArray(v)) return v.map(parseDeep)
    if (v && typeof v === "object") {
      const o: Record<string, unknown> = {}
      for (const [k, val] of Object.entries(v as Record<string, unknown>))
        o[k] = parseDeep(val)
      return o
    }
    return v
  }, [])

  const parsed = useMemo(() => {
    const raw =
      typeof data === "string"
        ? (() => {
            try {
              return JSON.parse(data)
            } catch {
              return data
            }
          })()
        : data
    return parseDeep(raw)
  }, [data, parseDeep])

  if (parsed !== null && typeof parsed === "object") {
    return (
      <div
        className="max-w-full min-w-0 overflow-hidden text-xs leading-relaxed [overflow-wrap:anywhere] break-words"
        style={{ fontFamily: MONO, fontSize: 11 }}
        onClick={(e) => e.stopPropagation()}
      >
        <JsonNode value={parsed as JsonValue} depth={0} isLast />
      </div>
    )
  }

  return (
    <pre
      className="max-w-full [overflow-wrap:anywhere] break-words whitespace-pre-wrap text-muted-foreground"
      style={{ fontFamily: MONO, fontSize: 11, margin: 0 }}
    >
      {String(parsed)}
    </pre>
  )
}
