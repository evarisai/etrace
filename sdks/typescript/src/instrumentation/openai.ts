/**
 * OpenAI auto-instrumentor (TypeScript).
 *
 * Patches:
 *   - OpenAI.Chat.Completions.prototype.create
 *   - OpenAI.Embeddings.prototype.create
 *
 * Uses etrace spans (no OTel dependency).
 */
import type { Span } from "../types.js";
import { BaseInstrumentor } from "./base.js";

export class OpenAIInstrumentor extends BaseInstrumentor {
  name = "openai";
  targetPackages = ["openai"];

  instrument(calcCosts: boolean): boolean {
    const openai = this._resolve("openai");
    if (!openai) return false;

    const OpenAI = (openai.default ?? openai) as Record<string, unknown>;

    try {
      // ── Chat completions ──────────────────────────────────────────────
      const Chat = OpenAI.Chat as Record<string, unknown> | undefined;
      const Completions = Chat?.Completions as Record<string, unknown> | undefined;
      if (Completions?.prototype) {
        this.patch(Completions.prototype as Record<string, unknown>, "create", (original) =>
          this.wrapLLMCall(calcCosts, original, "openai.chat", "openai", (span, res, model) => {
            this.processChat(span, res, model, calcCosts);
          }),
        );
      }

      // ── Embeddings ────────────────────────────────────────────────────
      const Embeddings = OpenAI.Embeddings as Record<string, unknown> | undefined;
      if (Embeddings?.prototype) {
        this.patch(Embeddings.prototype as Record<string, unknown>, "create", (original) =>
          this.wrapLLMCall(
            calcCosts,
            original,
            "openai.embeddings",
            "openai",
            (span, res, model) => {
              this.processEmbeddings(span, res, model, calcCosts);
            },
            "embedding",
          ),
        );
      }
    } catch (exc) {
      console.warn(`[etrace] openai patch failed: ${exc}`);
      this.uninstrument();
      return false;
    }

    console.info("[etrace] openai auto-instrumented (chat + embeddings)");
    return true;
  }

  // ── Chat response processing ────────────────────────────────────────────

  private processChat(span: Span, result: unknown, requestModel: string, calcCosts: boolean): void {
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
      const prompt = (usage.prompt_tokens as number) ?? 0;
      const completion = (usage.completion_tokens as number) ?? 0;
      const total = (usage.total_tokens as number) ?? 0;

      let cachedTokens = 0;
      const details = usage.prompt_tokens_details as Record<string, unknown> | null;
      if (details) cachedTokens = (details.cached_tokens as number) ?? 0;

      let reasoningTokens = 0;
      const compDetails = usage.completion_tokens_details as Record<string, unknown> | null;
      if (compDetails) reasoningTokens = (compDetails.reasoning_tokens as number) ?? 0;

      this.setUsageAndCost(
        span,
        model,
        prompt,
        completion,
        total,
        cachedTokens,
        reasoningTokens,
        0,
        calcCosts,
      );
    }

    // Capture output text
    try {
      const choices = res.choices as Array<Record<string, unknown>> | null;
      if (choices && choices.length > 0) {
        const msg = choices[0].message as Record<string, unknown> | null;
        if (msg?.content) {
          this.captureOutput(span, String(msg.content));
        }
      }
    } catch {
      /* best-effort */
    }
  }

  // ── Embedding response processing ───────────────────────────────────────

  private processEmbeddings(
    span: Span,
    result: unknown,
    requestModel: string,
    calcCosts: boolean,
  ): void {
    const res = result as Record<string, unknown> | null;
    if (!res) return;

    const model = (res.model as string) ?? requestModel;
    const usage = res.usage as Record<string, unknown> | null;
    if (usage) {
      const prompt = (usage.prompt_tokens as number) ?? 0;
      const total = (usage.total_tokens as number) ?? 0;
      this.setUsageAndCost(span, model, prompt, 0, total, 0, 0, 0, calcCosts);
    }
  }
}
