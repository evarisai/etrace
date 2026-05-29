/**
 * SpanProcessor — pipeline stage between span lifecycle and export.
 *
 * Mirrors the Python etrace._processor module exactly:
 *   SpanProcessor.on_end(span) → SpanExporter.export([span])
 */
import type { Span } from "./types.js";
import { SpanExportResult } from "./exporter.js";
import type { SpanExporter } from "./exporter.js";
import type { MaybePromise } from "./exporter.js";

export interface SpanProcessor {
  onStart(span: Span): void;
  onEnd(span: Span): void;
  forceFlush(timeoutMs?: number): MaybePromise<boolean>;
  shutdown(): MaybePromise<void>;
}

/** Sends every finished span directly to the exporter. */
export class SimpleProcessor implements SpanProcessor {
  private _exporter: SpanExporter;

  constructor(exporter: SpanExporter) {
    this._exporter = exporter;
  }

  onStart(_span: Span): void {}

  onEnd(span: Span): void {
    this._exporter.export([span]);
  }

  forceFlush(timeoutMs?: number): MaybePromise<boolean> {
    return this._exporter.forceFlush?.(timeoutMs) ?? true;
  }

  shutdown(): MaybePromise<void> {
    return this._exporter.shutdown();
  }
}

/** Buffers spans and exports them in batches. */
export class BatchProcessor implements SpanProcessor {
  private _exporter: SpanExporter;
  private _buffer: Span[] = [];
  private readonly _maxSize: number;
  private readonly _delayMs: number;
  private _timer: ReturnType<typeof setInterval> | null = null;

  constructor(exporter: SpanExporter, options?: { maxSize?: number; delayMs?: number }) {
    this._exporter = exporter;
    this._maxSize = options?.maxSize ?? 512;
    this._delayMs = options?.delayMs ?? 5000;
    this._timer = setInterval(() => this._flush(), this._delayMs);
    if (this._timer?.unref) this._timer.unref();
  }

  onStart(_span: Span): void {}

  onEnd(span: Span): void {
    this._buffer.push(span);
    if (this._buffer.length >= this._maxSize) {
      this._flush();
    }
  }

  private _flush(): SpanExportResult | Promise<SpanExportResult> {
    if (this._buffer.length === 0) return SpanExportResult.SUCCESS;
    const batch = this._buffer.splice(0);
    return this._exporter.export(batch);
  }

  forceFlush(timeoutMs?: number): MaybePromise<boolean> {
    const result = this._flush();
    if (result instanceof Promise) {
      return result.then(async (exportResult) => {
        if (exportResult !== SpanExportResult.SUCCESS) return false;
        return (await this._exporter.forceFlush?.(timeoutMs)) ?? true;
      });
    }
    if (result !== SpanExportResult.SUCCESS) return false;
    return this._exporter.forceFlush?.(timeoutMs) ?? true;
  }

  shutdown(): MaybePromise<void> {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
    const result = this._flush();
    if (result instanceof Promise) {
      return result.then(() => this._exporter.shutdown());
    }
    return this._exporter.shutdown();
  }
}

/** Fans out to multiple processors (e.g. console + HTTP). */
export class MultiProcessor implements SpanProcessor {
  private _processors: readonly SpanProcessor[];

  constructor(processors: readonly SpanProcessor[]) {
    this._processors = processors;
  }

  onStart(span: Span): void {
    for (const p of this._processors) p.onStart(span);
  }

  onEnd(span: Span): void {
    for (const p of this._processors) p.onEnd(span);
  }

  forceFlush(timeoutMs?: number): MaybePromise<boolean> {
    const results = this._processors.map((p) => p.forceFlush(timeoutMs));
    if (results.some((result) => result instanceof Promise)) {
      return Promise.all(results).then((resolved) => resolved.every(Boolean));
    }
    return (results as boolean[]).every(Boolean);
  }

  shutdown(): MaybePromise<void> {
    const results = this._processors.map((p) => p.shutdown());
    if (results.some((result) => result instanceof Promise)) {
      return Promise.all(results).then(() => undefined);
    }
  }
}
