/**
 * SpanExporter — protocol for sending finished spans to a backend.
 *
 * Mirrors the Python etrace._exporter module exactly.
 */
import type { Span } from "./types.js";

export enum SpanExportResult {
  SUCCESS = 0,
  FAILED = 1,
}

export interface SpanExporter {
  export(spans: Span[]): SpanExportResult | Promise<SpanExportResult>;
  shutdown(): void;
  forceFlush?(timeoutMs?: number): boolean;
}

/** Collects exported spans in memory. Ideal for testing. */
export class InMemoryExporter implements SpanExporter {
  private _spans: Span[] = [];

  export(spans: Span[]): SpanExportResult {
    this._spans.push(...spans);
    return SpanExportResult.SUCCESS;
  }

  getFinishedSpans(): Span[] {
    return [...this._spans];
  }

  clear(): void {
    this._spans = [];
  }

  shutdown(): void {
    this.clear();
  }

  forceFlush(): boolean {
    return true;
  }
}

/** Logs spans to the console. Useful for local development. */
export class ConsoleExporter implements SpanExporter {
  export(spans: Span[]): SpanExportResult {
    for (const span of spans) {
      console.log(
        `[etrace] ${span.name} (${span.kind}) status=${span.status} ` +
          `duration=${span.durationNs ?? 0}ns`,
      );
    }
    return SpanExportResult.SUCCESS;
  }

  shutdown(): void {}
}
