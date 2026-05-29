import { useEffect, useMemo, useRef, useState } from "react"

export function ResizeRail({
  label,
  value,
  min,
  max,
  onChange,
  direction = "normal",
  className,
}: {
  label: string
  value: number
  min: number
  max: number
  onChange: (value: number) => void
  direction?: "normal" | "inverse"
  className?: string
}) {
  const startXRef = useRef(0)
  const startValueRef = useRef(value)
  const [dragging, setDragging] = useState(false)

  const clamp = useMemo(() => {
    return (nextValue: number) => Math.min(max, Math.max(min, nextValue))
  }, [max, min])

  useEffect(() => {
    if (!dragging) {
      return
    }

    const handlePointerMove = (event: PointerEvent) => {
      const delta = event.clientX - startXRef.current
      onChange(
        clamp(
          startValueRef.current + (direction === "inverse" ? -delta : delta)
        )
      )
    }

    const handlePointerUp = () => {
      setDragging(false)
      document.body.style.cursor = ""
      document.body.style.userSelect = ""
    }

    document.body.style.cursor = "col-resize"
    document.body.style.userSelect = "none"
    window.addEventListener("pointermove", handlePointerMove)
    window.addEventListener("pointerup", handlePointerUp)

    return () => {
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", handlePointerUp)
      document.body.style.cursor = ""
      document.body.style.userSelect = ""
    }
  }, [clamp, direction, dragging, onChange])

  return (
    <button
      type="button"
      aria-label={label}
      data-dragging={dragging}
      className={`tp-resizer ${className ?? ""}`}
      onPointerDown={(event) => {
        startXRef.current = event.clientX
        startValueRef.current = value
        setDragging(true)
      }}
    />
  )
}
