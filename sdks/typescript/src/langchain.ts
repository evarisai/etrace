/**
 * Callback adapter for framework-driven agent tracing.
 *
 * The class intentionally avoids importing the optional framework package at
 * module load time. Callback managers use method names on callback objects, so
 * this duck-typed handler can be passed directly in config.callbacks.
 */
import { MAX_ATTR_LEN } from "./index.js";
import { RunTracker } from "./tracing.js";
import type { UsageMap } from "./tracing.js";

export function langchainHandler(): EtraceLangChainHandler {
  return new EtraceLangChainHandler();
}

export class EtraceLangChainHandler {
  name = "EtraceLangChainHandler";

  private readonly _tracker = new RunTracker();
  private _lastLlmRunId: string | null = null;

  handleChatModelStart(
    llm: unknown,
    messages: unknown[][],
    runId: string,
    parentRunId?: string,
    _extraParams?: unknown,
    _tags?: string[],
    metadata?: Record<string, unknown>,
    _runName?: string,
  ): void {
    const provider = stringValue(metadata?.ls_provider) ?? stringValue(metadata?.provider) ?? "";
    const model = stringValue(metadata?.ls_model_name) ?? stringValue(metadata?.model) ?? "";

    this._tracker.onRunStart(provider ? `${provider}.chat` : "chat_model", {
      runId,
      parentRunId,
      kind: "llm",
      input: messages?.[0] ? serializeMessages(messages[0]) : undefined,
      model,
      provider,
      attributes: {
        "etrace.kind": "llm",
        "gen_ai.system": provider,
        "gen_ai.request.model": model,
      },
    });
    this._lastLlmRunId = runId;
  }

  handleLLMStart(
    _llm: unknown,
    prompts: string[],
    runId: string,
    parentRunId?: string,
    _extraParams?: unknown,
    _tags?: string[],
    metadata?: Record<string, unknown>,
    _runName?: string,
  ): void {
    const provider = stringValue(metadata?.ls_provider) ?? stringValue(metadata?.provider) ?? "";
    const model = stringValue(metadata?.ls_model_name) ?? stringValue(metadata?.model) ?? "";

    this._tracker.onRunStart(provider ? `${provider}.chat` : "llm", {
      runId,
      parentRunId,
      kind: "llm",
      input: prompts?.[0],
      model,
      provider,
      attributes: {
        "etrace.kind": "llm",
        "gen_ai.system": provider,
        "gen_ai.request.model": model,
      },
    });
    this._lastLlmRunId = runId;
  }

  handleLLMEnd(response: unknown, runId: string): void {
    const { output, usage, model, attributes } = parseLlmResponse(response);
    this._tracker.onRunEnd(runId, {
      output,
      usage,
      model,
      attributes,
    });
  }

  handleLLMError(error: unknown, runId: string): void {
    this._tracker.onRunError(runId, error);
  }

  handleToolStart(
    tool: unknown,
    input: string,
    runId: string,
    parentRunId?: string,
    _tags?: string[],
    _metadata?: Record<string, unknown>,
    _runName?: string,
    inputs?: Record<string, unknown>,
  ): void {
    const effectiveParent = this._lastLlmRunId ?? parentRunId;
    this._tracker.onRunStart(toolName(tool), {
      runId,
      parentRunId: effectiveParent,
      kind: "tool",
      input: inputs ?? input,
      attributes: { "etrace.kind": "tool" },
    });
  }

  handleToolEnd(output: unknown, runId: string): void {
    this._tracker.onRunEnd(runId, { output });
  }

  handleToolError(error: unknown, runId: string): void {
    this._tracker.onRunError(runId, error);
  }

  handleChainStart(
    _chain: unknown,
    _inputs: Record<string, unknown>,
    runId: string,
    parentRunId?: string,
  ): void {
    this._tracker.skipRun(runId, parentRunId);
  }

  handleChainEnd(_outputs: Record<string, unknown>, _runId: string): void {
    // Chain runs are used only for parent lookup; they are intentionally quiet.
  }

  handleChainError(_error: unknown, _runId: string): void {
    // Chain runs have no etrace span to close.
  }

  flush(): void {
    this._tracker.flush();
  }
}

function serializeMessages(messages: unknown[]): Array<Record<string, unknown>> {
  return messages.map((message) => {
    const msg = asRecord(message);
    const entry: Record<string, unknown> = {
      role: stringValue(msg.type) ?? getMessageType(msg) ?? stringValue(msg.role) ?? "unknown",
      content: msg.content ?? "",
    };
    const toolCalls = asArray(msg.tool_calls ?? msg.toolCalls);
    if (toolCalls.length) {
      entry.tool_calls = toolCalls.map((toolCall) => serializeToolCall(toolCall));
    }
    return entry;
  });
}

function parseLlmResponse(response: unknown): {
  output?: unknown;
  usage?: UsageMap | null;
  model?: string;
  attributes?: Record<string, unknown>;
} {
  const res = asRecord(response);
  const generation = firstGeneration(res.generations);
  const message = asRecord(asRecord(generation).message);
  const responseMetadata = asRecord(message.response_metadata ?? message.responseMetadata);
  const llmOutput = asRecord(res.llmOutput ?? res.llm_output);
  const tokenUsage = asRecord(
    responseMetadata.token_usage ??
      responseMetadata.tokenUsage ??
      llmOutput.tokenUsage ??
      llmOutput.token_usage,
  );

  const usage = parseUsage(tokenUsage);
  const attributes: Record<string, unknown> = {};
  const model =
    stringValue(responseMetadata.model_name) ??
    stringValue(responseMetadata.modelName) ??
    stringValue(llmOutput.model_name) ??
    stringValue(llmOutput.modelName);
  if (model) attributes["gen_ai.response.model"] = model;

  let output: unknown;
  const content = message.content ?? asRecord(generation).text;
  if (content) {
    output = content;
    attributes["gen_ai.output"] = stringOrJson(content).slice(0, MAX_ATTR_LEN);
  } else {
    const toolCalls = asArray(message.tool_calls ?? message.toolCalls);
    if (toolCalls.length) {
      const serialized = toolCalls.map((toolCall) => serializeToolCall(toolCall));
      output = serialized;
      attributes["gen_ai.output"] = JSON.stringify(serialized).slice(0, MAX_ATTR_LEN);
    }
  }

  return {
    output,
    usage,
    model,
    attributes: Object.keys(attributes).length ? attributes : undefined,
  };
}

function firstGeneration(generations: unknown): unknown {
  const outer = asArray(generations);
  const first = outer[0];
  const inner = asArray(first);
  return inner.length ? inner[0] : first;
}

function parseUsage(tokenUsage: Record<string, unknown>): UsageMap | null {
  const prompt =
    numberValue(tokenUsage.prompt_tokens) ??
    numberValue(tokenUsage.promptTokens) ??
    numberValue(tokenUsage.input_tokens) ??
    0;
  const completion =
    numberValue(tokenUsage.completion_tokens) ??
    numberValue(tokenUsage.completionTokens) ??
    numberValue(tokenUsage.output_tokens) ??
    0;
  const total =
    numberValue(tokenUsage.total_tokens) ??
    numberValue(tokenUsage.totalTokens) ??
    prompt + completion;
  const cached =
    numberValue(tokenUsage.cached_tokens) ??
    numberValue(tokenUsage.cachedTokens) ??
    numberValue(asRecord(tokenUsage.prompt_tokens_details).cached_tokens) ??
    0;
  const reasoning =
    numberValue(tokenUsage.reasoning_tokens) ??
    numberValue(tokenUsage.reasoningTokens) ??
    numberValue(asRecord(tokenUsage.completion_tokens_details).reasoning_tokens) ??
    0;

  if (!prompt && !completion && !total && !cached && !reasoning) return null;
  return {
    prompt_tokens: prompt,
    completion_tokens: completion,
    total_tokens: total,
    cached_tokens: cached,
    reasoning_tokens: reasoning,
  };
}

function serializeToolCall(toolCall: unknown): Record<string, unknown> {
  const tc = asRecord(toolCall);
  return {
    name: tc.name ?? asRecord(tc.function).name ?? "",
    arguments: tc.args ?? tc.arguments ?? asRecord(tc.function).arguments ?? {},
  };
}

function toolName(tool: unknown): string {
  const obj = asRecord(tool);
  return stringValue(obj.name) ?? stringValue(asRecord(obj.id).name) ?? "tool";
}

function getMessageType(message: Record<string, unknown>): string | undefined {
  const getType = message._getType;
  if (typeof getType !== "function") return undefined;
  try {
    return stringValue(getType.call(message));
  } catch {
    return undefined;
  }
}

function stringOrJson(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.length ? value : undefined;
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}
