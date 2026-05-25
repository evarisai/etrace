/**
 * Auto-instrumentation registry (TypeScript).
 *
 * Discovers available LLM provider SDKs and patches them to emit
 * etrace spans with automatic cost calculation.
 *
 * No OTel dependency — uses etrace spans directly.
 */
import type { BaseInstrumentor } from "./base.js";
import { OpenAIInstrumentor } from "./openai.js";
import { AnthropicInstrumentor } from "./anthropic.js";

// ── Registry ─────────────────────────────────────────────────────────────────

const INSTRUMENTOR_CLASSES: Array<new () => BaseInstrumentor> = [
  OpenAIInstrumentor,
  AnthropicInstrumentor,
];

const _active: BaseInstrumentor[] = [];

/**
 * Try every registered instrumentor.
 * Returns the list of provider names that were successfully patched.
 */
export function instrumentAll(calcCosts = true): string[] {
  const enabled: string[] = [];

  for (const Cls of INSTRUMENTOR_CLASSES) {
    const inst = new Cls();
    try {
      if (inst.instrument(calcCosts)) {
        _active.push(inst);
        enabled.push(inst.name);
      }
    } catch (exc) {
      console.warn(`[etrace] instrumentor ${inst.name} failed: ${exc}`);
    }
  }

  if (enabled.length) {
    console.info(`[etrace] auto-instrumentation enabled: ${enabled.join(", ")}`);
  } else {
    console.info(
      "[etrace] no LLM providers found — install openai and/or " +
        "@anthropic-ai/sdk for auto-instrumentation",
    );
  }

  return enabled;
}

/** Restore all original methods (called on shutdown). */
export function uninstrumentAll(): void {
  for (const inst of _active) {
    inst.uninstrument();
  }
  _active.length = 0;
}
