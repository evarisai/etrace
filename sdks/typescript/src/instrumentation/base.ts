/**
 * Base class for LLM provider auto-instrumentors (TypeScript).
 *
 * Zero-dep — uses etrace spans directly (no OTel).
 * Every instrumentor follows the same pattern:
 *   1. Try to require() the target package.
 *   2. Patch specific prototype methods with wrappers that emit etrace spans.
 *   3. Extract usage (tokens) from the response.
 *   4. Auto-calculate cost from the pricing catalog.
 *   5. Restore originals on uninstrument().
 */
import { createRequire } from "node:module";
import type { Span, TraceKind } from "../types.js";
import {
  trace as etraceTrace,
  getCurrentSpan,
  setAttribute as etraceSetAttribute,
  setUsage as etraceSetUsage,
  MAX_ATTR_LEN,
} from "../index.js";

const _require = createRequire(import.meta.url);

export interface PatchRecord {
  obj: Record<string, unknown>;
  method: string;
  original: (...args: unknown[]) => unknown;
}

export abstract class BaseInstrumentor {
  abstract name: string;
  abstract targetPackages: string[];

  protected originals: PatchRecord[] = [];

  /** Resolve a module by name. Override in tests to inject mocks. */
  protected _resolve(name: string): Record<string, unknown> | null {
    try {
      return _require(name) as Record<string, unknown>;
    } catch {
      return null;
    }
  }

  /** Apply monkey patches. Return true if at least one patch succeeded. */
  abstract instrument(calcCosts: boolean): boolean;

  /** Restore all original methods. */
  uninstrument(): void {
    for (const { obj, method, original } of this.originals) {
      try {
        obj[method] = original;
      } catch {
        /* best-effort */
      }
    }
    this.originals = [];
  }

  /**
   * Replace `obj.method` with `factory(original)`.
   */
  protected patch(
    obj: Record<string, unknown>,
    method: string,
    factory: (original: (...args: unknown[]) => unknown) => (...args: unknown[]) => unknown,
  ): void {
    const original = obj[method] as (...args: unknown[]) => unknown;
    const wrapped = factory(original);
    obj[method] = wrapped;
    this.originals.push({ obj, method, original });
  }

  // ── Shared LLM call wrapper ────────────────────────────────────────────

  /**
   * Generic wrapper for LLM SDK methods.
   * Uses etrace.trace() internally — no OTel dependency.
   */
  protected wrapLLMCall(
    calcCosts: boolean,
    original: (...args: unknown[]) => unknown,
    spanName: string,
    provider: string,
    onSuccess: (span: Span, result: unknown, requestModel: string) => void,
    kind: TraceKind = "llm",
  ): (...args: unknown[]) => unknown {
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    const self = this;
    return function (this: unknown, ...args: unknown[]): unknown {
      const body = (args[0] ?? {}) as Record<string, unknown>;
      const model = (body.model as string) ?? "";

      return etraceTrace(
        spanName,
        async () => {
          const span = getCurrentSpan()!;
          self.setSemconvAttrs(span, provider, model);
          self.captureInput(span, body);

          const result = (await original.apply(this, args)) as unknown;
          onSuccess(span, result, model);
          return result;
        },
        { kind, provider, model, input: body.messages },
      );
    };
  }

  /** Set semconv provider/model attributes after trace() creates the span. */
  protected setSemconvAttrs(span: Span, provider: string, model: string): void {
    span.attributes ??= {};
    span.attributes["gen_ai.system"] = provider;
    if (model) span.attributes["gen_ai.request.model"] = model;
    span.attributes["etrace.kind"] = span.kind;
  }

  // ── Usage + cost helpers ───────────────────────────────────────────────

  protected setUsageAndCost(
    span: Span,
    model: string,
    promptTokens: number,
    completionTokens: number,
    totalTokens = 0,
    cachedTokens = 0,
    reasoningTokens = 0,
    cacheWriteTokens = 0,
    calcCosts = true,
  ): void {
    span.attributes ??= {};
    span.attributes["gen_ai.usage.prompt_tokens"] = promptTokens;
    span.attributes["gen_ai.usage.completion_tokens"] = completionTokens;
    span.attributes["gen_ai.usage.total_tokens"] = totalTokens || promptTokens + completionTokens;
    if (cachedTokens) span.attributes["gen_ai.usage.cache_read_tokens"] = cachedTokens;
    if (reasoningTokens) span.attributes["gen_ai.usage.reasoning_tokens"] = reasoningTokens;
    if (cacheWriteTokens) span.attributes["gen_ai.usage.cache_write_tokens"] = cacheWriteTokens;

    if (calcCosts) {
      etraceSetUsage({
        inputTokens: promptTokens,
        outputTokens: completionTokens,
        totalTokens: totalTokens || promptTokens + completionTokens,
        cachedTokens,
        reasoningTokens,
        model,
      });
    }
  }

  protected captureInput(span: Span, body: Record<string, unknown>): void {
    if (body.messages) {
      try {
        etraceSetAttribute(
          "gen_ai.input.messages",
          JSON.stringify(body.messages).slice(0, MAX_ATTR_LEN),
        );
      } catch {
        /* best-effort */
      }
    }
  }

  protected captureOutput(span: Span, text: string): void {
    etraceSetAttribute("gen_ai.output", text.slice(0, MAX_ATTR_LEN));
  }
}
