/**
 * Anthropic auto-instrumentor (TypeScript).
 *
 * Patches:
 *   - Anthropic.Messages.prototype.create
 *
 * Uses etrace spans (no OTel dependency).
 */
import type { Span } from "../types.js";
import { BaseInstrumentor } from "./base.js";

export class AnthropicInstrumentor extends BaseInstrumentor {
  name = "anthropic";
  targetPackages = ["@anthropic-ai/sdk"];

  instrument(calcCosts: boolean): boolean {
    const anthropic = this._resolve("@anthropic-ai/sdk");
    if (!anthropic) return false;

    const SDK = (anthropic.default ?? anthropic) as Record<string, unknown>;

    try {
      // ── Messages ──────────────────────────────────────────────────────
      const Messages = SDK.Messages as Record<string, unknown> | undefined;
      if (Messages?.prototype) {
        this.patch(Messages.prototype as Record<string, unknown>, "create", (original) =>
          this.wrapLLMCall(
            calcCosts,
            original,
            "anthropic.messages",
            "anthropic",
            (span, res, model) => {
              this.processMessages(span, res, model, calcCosts);
            },
          ),
        );
      }
    } catch (exc) {
      console.warn(`[etrace] anthropic patch failed: ${exc}`);
      this.uninstrument();
      return false;
    }

    console.info("[etrace] anthropic auto-instrumented (messages)");
    return true;
  }

  // ── Messages response processing ────────────────────────────────────────

  private processMessages(
    span: Span,
    result: unknown,
    requestModel: string,
    calcCosts: boolean,
  ): void {
    const res = result as Record<string, unknown> | null | undefined;
    if (!res) return;

    const model = (res.model as string) ?? requestModel;

    const isStream =
      typeof (res as unknown as AsyncIterable<unknown>)[Symbol.asyncIterator] === "function";
    if (isStream) {
      span.attributes ??= {};
      span.attributes["gen_ai.streaming"] = true;
      return;
    }

    // Extract usage
    const usage = res.usage as Record<string, unknown> | null | undefined;
    if (usage) {
      const inputTokens = (usage.input_tokens as number) ?? 0;
      const outputTokens = (usage.output_tokens as number) ?? 0;
      const cacheRead = (usage.cache_read_input_tokens as number) ?? 0;
      const cacheCreation = (usage.cache_creation_input_tokens as number) ?? 0;

      this.setUsageAndCost(
        span,
        model,
        inputTokens,
        outputTokens,
        0,
        cacheRead,
        0,
        cacheCreation,
        calcCosts,
      );
    }

    // Capture output text
    try {
      const content = res.content as Array<Record<string, unknown>> | null;
      if (content) {
        const text = content
          .filter((block) => typeof block.text === "string")
          .map((block) => block.text as string)
          .join("");
        if (text) {
          this.captureOutput(span, text);
        }
      }
    } catch {
      /* best-effort */
    }
  }
}
