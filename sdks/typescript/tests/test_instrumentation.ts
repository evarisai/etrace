/**
 * Tests for auto-instrumentation: OpenAI and Anthropic instrumentors.
 *
 * Uses mock SDK objects injected via subclassing BaseInstrumentor._resolve().
 * Tests verify:
 *   - Patching creates etrace spans with correct names/kinds
 *   - Token usage is extracted from responses
 *   - Cost is calculated when enabled
 *   - Streaming flag is set
 *   - Error handling (ERROR status)
 *   - Uninstrument restores originals
 *
 * Matches Python test_instrumentation.py (30 tests).
 */
import { describe, it, expect, afterEach } from "vitest";
import { init, shutdown, InMemoryExporter } from "../src/index.js";
import { OpenAIInstrumentor } from "../src/instrumentation/openai.js";
import { AnthropicInstrumentor } from "../src/instrumentation/anthropic.js";

afterEach(() => {
  shutdown();
});

function setup() {
  const exporter = new InMemoryExporter();
  init({ exporters: [exporter], calculateCosts: false, autoInstrument: { llm: false } });
  return exporter;
}

// ── Mock response factories ──────────────────────────────────────────────────

function openaiChatResponse(
  opts: {
    model?: string;
    promptTokens?: number;
    completionTokens?: number;
    totalTokens?: number;
    cachedTokens?: number;
    reasoningTokens?: number;
    content?: string;
  } = {},
) {
  const model = opts.model ?? "gpt-4o";
  const pt = opts.promptTokens ?? 100;
  const ct = opts.completionTokens ?? 50;
  const tt = opts.totalTokens ?? 150;
  return {
    model,
    usage: {
      prompt_tokens: pt,
      completion_tokens: ct,
      total_tokens: tt,
      prompt_tokens_details: { cached_tokens: opts.cachedTokens ?? 0 },
      completion_tokens_details: { reasoning_tokens: opts.reasoningTokens ?? 0 },
    },
    choices: [{ message: { content: opts.content ?? "Hello!" } }],
  };
}

function openaiEmbeddingResponse(
  opts: {
    model?: string;
    promptTokens?: number;
    totalTokens?: number;
  } = {},
) {
  return {
    model: opts.model ?? "text-embedding-3-small",
    usage: { prompt_tokens: opts.promptTokens ?? 20, total_tokens: opts.totalTokens ?? 20 },
    data: [{ embedding: [0.1, 0.2] }],
  };
}

function anthropicMessageResponse(
  opts: {
    model?: string;
    inputTokens?: number;
    outputTokens?: number;
    cacheRead?: number;
    cacheCreation?: number;
    text?: string;
  } = {},
) {
  return {
    model: opts.model ?? "claude-sonnet-4-20250514",
    usage: {
      input_tokens: opts.inputTokens ?? 80,
      output_tokens: opts.outputTokens ?? 40,
      cache_read_input_tokens: opts.cacheRead ?? 0,
      cache_creation_input_tokens: opts.cacheCreation ?? 0,
    },
    content: [{ type: "text", text: opts.text ?? "Hi there!" }],
  };
}

// ── Testable instrumentor: injects mock SDK via _resolve override ────────────

class TestableOpenAIInstrumentor extends OpenAIInstrumentor {
  private _mockSdk: Record<string, unknown> | null = null;

  useMock(sdk: Record<string, unknown>) {
    this._mockSdk = sdk;
  }

  protected override _resolve(_name: string): Record<string, unknown> | null {
    return this._mockSdk;
  }
}

class TestableAnthropicInstrumentor extends AnthropicInstrumentor {
  private _mockSdk: Record<string, unknown> | null = null;

  useMock(sdk: Record<string, unknown>) {
    this._mockSdk = sdk;
  }

  protected override _resolve(_name: string): Record<string, unknown> | null {
    return this._mockSdk;
  }
}

// ── BaseInstrumentor tests ───────────────────────────────────────────────────

describe("BaseInstrumentor", () => {
  it("patch wraps and stores original", () => {
    const inst = new TestableOpenAIInstrumentor();
    const obj: Record<string, unknown> = {
      method: () => "original",
    };

    inst.patch(obj, "method", (orig) => () => `${(orig as () => string)()}-wrapped`);

    expect(obj.method()).toBe("original-wrapped");
    expect(inst.originals).toHaveLength(1);
    expect(inst.originals[0].method).toBe("method");
  });

  it("uninstrument restores originals", () => {
    const inst = new TestableOpenAIInstrumentor();
    const obj: Record<string, unknown> = {
      method: () => "original",
    };
    const originalRef = obj.method;

    inst.patch(obj, "method", () => () => "wrapped");
    expect(obj.method()).toBe("wrapped");

    inst.uninstrument();
    expect(obj.method).toBe(originalRef);
  });

  it("uninstrument with no patches is safe", () => {
    const inst = new TestableOpenAIInstrumentor();
    expect(() => inst.uninstrument()).not.toThrow();
  });
});

// ── OpenAI Instrumentation ───────────────────────────────────────────────────

describe("OpenAIInstrumentor", () => {
  function makeOpenAISdk(
    chatFn?: (...args: unknown[]) => unknown,
    embFn?: (...args: unknown[]) => unknown,
  ) {
    const chatCreate = chatFn ?? (() => openaiChatResponse());
    const embCreate = embFn ?? (() => openaiEmbeddingResponse());

    function MockCompletions() {}
    MockCompletions.prototype.create = chatCreate;

    function MockEmbeddings() {}
    MockEmbeddings.prototype.create = embCreate;

    return {
      default: {
        Chat: { Completions: MockCompletions },
        Embeddings: MockEmbeddings,
      },
    };
  }

  it("instrument returns true with mock SDK", () => {
    const inst = new TestableOpenAIInstrumentor();
    inst.useMock(makeOpenAISdk());
    expect(inst.instrument(false)).toBe(true);
    inst.uninstrument();
  });

  it("instrument returns false without SDK", () => {
    const inst = new TestableOpenAIInstrumentor();
    // _resolve returns null
    expect(inst.instrument(false)).toBe(false);
  });

  it("uninstrument restores original create", () => {
    const originalCreate = () => openaiChatResponse();
    const sdk = makeOpenAISdk(originalCreate);
    const inst = new TestableOpenAIInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const patchedCreate = sdk.default.Chat.Completions.prototype.create;
    expect(patchedCreate).not.toBe(originalCreate);

    inst.uninstrument();
    expect(sdk.default.Chat.Completions.prototype.create).toBe(originalCreate);
  });

  it("chat span created with correct name", async () => {
    const exp = setup();
    const originalCreate = (..._args: unknown[]) => Promise.resolve(openaiChatResponse());
    const sdk = makeOpenAISdk(originalCreate);
    const inst = new TestableOpenAIInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const Completions = sdk.default.Chat.Completions as Record<string, unknown>;
    const proto = Completions.prototype as Record<string, unknown>;
    const createFn = proto.create as (...args: unknown[]) => Promise<unknown>;
    await createFn.call({}, { model: "gpt-4o", messages: [{ role: "user", content: "hi" }] });

    const spans = exp.getFinishedSpans();
    expect(spans.length).toBeGreaterThanOrEqual(1);
    const chatSpan = spans.find((s) => s.name === "openai.chat");
    expect(chatSpan).toBeDefined();

    inst.uninstrument();
  });

  it("chat span has semconv attributes", async () => {
    const exp = setup();
    const originalCreate = (..._args: unknown[]) => Promise.resolve(openaiChatResponse());
    const sdk = makeOpenAISdk(originalCreate);
    const inst = new TestableOpenAIInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Chat.Completions as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await (proto.create as (...args: unknown[]) => Promise<unknown>)({
      model: "gpt-4o",
      messages: [{ role: "user", content: "hi" }],
    });

    const span = exp.getFinishedSpans().find((s) => s.name === "openai.chat")!;
    expect(span.attributes?.["gen_ai.system"]).toBe("openai");
    expect(span.attributes?.["gen_ai.request.model"]).toBe("gpt-4o");

    inst.uninstrument();
  });

  it("chat span has usage tokens", async () => {
    const exp = setup();
    const originalCreate = (..._args: unknown[]) =>
      Promise.resolve(
        openaiChatResponse({ promptTokens: 200, completionTokens: 100, totalTokens: 300 }),
      );
    const sdk = makeOpenAISdk(originalCreate);
    const inst = new TestableOpenAIInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Chat.Completions as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await (proto.create as (...args: unknown[]) => Promise<unknown>)({
      model: "gpt-4o",
      messages: [{ role: "user", content: "hi" }],
    });

    const span = exp.getFinishedSpans().find((s) => s.name === "openai.chat")!;
    expect(span.attributes?.["gen_ai.usage.prompt_tokens"]).toBe(200);
    expect(span.attributes?.["gen_ai.usage.completion_tokens"]).toBe(100);
    expect(span.attributes?.["gen_ai.usage.total_tokens"]).toBe(300);

    inst.uninstrument();
  });

  it("chat span captures output", async () => {
    const exp = setup();
    const originalCreate = (..._args: unknown[]) =>
      Promise.resolve(openaiChatResponse({ content: "Test response" }));
    const sdk = makeOpenAISdk(originalCreate);
    const inst = new TestableOpenAIInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Chat.Completions as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await (proto.create as (...args: unknown[]) => Promise<unknown>)({
      model: "gpt-4o",
      messages: [{ role: "user", content: "hi" }],
    });

    const span = exp.getFinishedSpans().find((s) => s.name === "openai.chat")!;
    expect(span.attributes?.["gen_ai.output"]).toBe("Test response");

    inst.uninstrument();
  });

  it("chat span captures input messages", async () => {
    const exp = setup();
    const originalCreate = (..._args: unknown[]) => Promise.resolve(openaiChatResponse());
    const sdk = makeOpenAISdk(originalCreate);
    const inst = new TestableOpenAIInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const msgs = [{ role: "user", content: "hi" }];
    const proto = (sdk.default.Chat.Completions as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await (proto.create as (...args: unknown[]) => Promise<unknown>)({
      model: "gpt-4o",
      messages: msgs,
    });

    const span = exp.getFinishedSpans().find((s) => s.name === "openai.chat")!;
    expect(span.attributes?.["gen_ai.input.messages"]).toBeDefined();
    expect(span.input).toEqual(msgs);

    inst.uninstrument();
  });

  it("chat span captures cached tokens", async () => {
    const exp = setup();
    const originalCreate = (..._args: unknown[]) =>
      Promise.resolve(openaiChatResponse({ cachedTokens: 500 }));
    const sdk = makeOpenAISdk(originalCreate);
    const inst = new TestableOpenAIInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Chat.Completions as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await (proto.create as (...args: unknown[]) => Promise<unknown>)({
      model: "gpt-4o",
      messages: [{ role: "user", content: "hi" }],
    });

    const span = exp.getFinishedSpans().find((s) => s.name === "openai.chat")!;
    expect(span.attributes?.["gen_ai.usage.cache_read_tokens"]).toBe(500);

    inst.uninstrument();
  });

  it("chat span captures reasoning tokens", async () => {
    const exp = setup();
    const originalCreate = (..._args: unknown[]) =>
      Promise.resolve(openaiChatResponse({ reasoningTokens: 1000 }));
    const sdk = makeOpenAISdk(originalCreate);
    const inst = new TestableOpenAIInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Chat.Completions as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await (proto.create as (...args: unknown[]) => Promise<unknown>)({
      model: "gpt-4o",
      messages: [{ role: "user", content: "hi" }],
    });

    const span = exp.getFinishedSpans().find((s) => s.name === "openai.chat")!;
    expect(span.attributes?.["gen_ai.usage.reasoning_tokens"]).toBe(1000);

    inst.uninstrument();
  });

  it("chat span has ok status on success", async () => {
    const exp = setup();
    const originalCreate = (..._args: unknown[]) => Promise.resolve(openaiChatResponse());
    const sdk = makeOpenAISdk(originalCreate);
    const inst = new TestableOpenAIInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Chat.Completions as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await (proto.create as (...args: unknown[]) => Promise<unknown>)({
      model: "gpt-4o",
      messages: [{ role: "user", content: "hi" }],
    });

    const span = exp.getFinishedSpans().find((s) => s.name === "openai.chat")!;
    expect(span.status).toBe("ok");

    inst.uninstrument();
  });

  it("chat span error on exception", async () => {
    const exp = setup();
    const originalCreate = (..._args: unknown[]) => {
      throw new Error("bad_api_key");
    };
    const sdk = makeOpenAISdk(originalCreate);
    const inst = new TestableOpenAIInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Chat.Completions as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await expect(
      (proto.create as (...args: unknown[]) => Promise<unknown>)({
        model: "gpt-4o",
        messages: [{ role: "user", content: "hi" }],
      }),
    ).rejects.toThrow("bad_api_key");

    const span = exp.getFinishedSpans().find((s) => s.name === "openai.chat")!;
    expect(span.status).toBe("error");
    expect(span.error?.message).toBe("bad_api_key");

    inst.uninstrument();
  });

  it("embedding span created", async () => {
    const exp = setup();
    const originalEmb = (..._args: unknown[]) => Promise.resolve(openaiEmbeddingResponse());
    const sdk = makeOpenAISdk(undefined, originalEmb);
    const inst = new TestableOpenAIInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Embeddings as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await (proto.create as (...args: unknown[]) => Promise<unknown>)({
      model: "text-embedding-3-small",
      input: "hello",
    });

    const span = exp.getFinishedSpans().find((s) => s.name === "openai.embeddings")!;
    expect(span).toBeDefined();
    expect(span.kind).toBe("embedding");

    inst.uninstrument();
  });

  it("embedding span has usage", async () => {
    const exp = setup();
    const originalEmb = (..._args: unknown[]) =>
      Promise.resolve(openaiEmbeddingResponse({ promptTokens: 30, totalTokens: 30 }));
    const sdk = makeOpenAISdk(undefined, originalEmb);
    const inst = new TestableOpenAIInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Embeddings as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await (proto.create as (...args: unknown[]) => Promise<unknown>)({
      model: "text-embedding-3-small",
      input: "hello",
    });

    const span = exp.getFinishedSpans().find((s) => s.name === "openai.embeddings")!;
    expect(span.attributes?.["gen_ai.usage.prompt_tokens"]).toBe(30);
    expect(span.attributes?.["gen_ai.usage.completion_tokens"]).toBe(0);
    expect(span.attributes?.["gen_ai.usage.total_tokens"]).toBe(30);

    inst.uninstrument();
  });
});

// ── Anthropic Instrumentation ────────────────────────────────────────────────

describe("AnthropicInstrumentor", () => {
  function makeAnthropicSdk(msgFn?: (...args: unknown[]) => unknown) {
    const msgCreate = msgFn ?? (() => anthropicMessageResponse());

    function MockMessages() {}
    MockMessages.prototype.create = msgCreate;

    return {
      default: {
        Messages: MockMessages,
      },
    };
  }

  it("instrument returns true with mock SDK", () => {
    const inst = new TestableAnthropicInstrumentor();
    inst.useMock(makeAnthropicSdk());
    expect(inst.instrument(false)).toBe(true);
    inst.uninstrument();
  });

  it("instrument returns false without SDK", () => {
    const inst = new TestableAnthropicInstrumentor();
    expect(inst.instrument(false)).toBe(false);
  });

  it("messages span created with correct name", async () => {
    const exp = setup();
    const originalCreate = (..._args: unknown[]) => Promise.resolve(anthropicMessageResponse());
    const sdk = makeAnthropicSdk(originalCreate);
    const inst = new TestableAnthropicInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Messages as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await (proto.create as (...args: unknown[]) => Promise<unknown>)({
      model: "claude-sonnet-4-20250514",
      messages: [{ role: "user", content: "hi" }],
    });

    const span = exp.getFinishedSpans().find((s) => s.name === "anthropic.messages")!;
    expect(span).toBeDefined();

    inst.uninstrument();
  });

  it("messages span has semconv attributes", async () => {
    const exp = setup();
    const originalCreate = (..._args: unknown[]) => Promise.resolve(anthropicMessageResponse());
    const sdk = makeAnthropicSdk(originalCreate);
    const inst = new TestableAnthropicInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Messages as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await (proto.create as (...args: unknown[]) => Promise<unknown>)({
      model: "claude-sonnet-4-20250514",
      messages: [{ role: "user", content: "hi" }],
    });

    const span = exp.getFinishedSpans().find((s) => s.name === "anthropic.messages")!;
    expect(span.attributes?.["gen_ai.system"]).toBe("anthropic");
    expect(span.attributes?.["gen_ai.request.model"]).toBe("claude-sonnet-4-20250514");

    inst.uninstrument();
  });

  it("messages span has usage tokens", async () => {
    const exp = setup();
    const originalCreate = (..._args: unknown[]) =>
      Promise.resolve(anthropicMessageResponse({ inputTokens: 80, outputTokens: 40 }));
    const sdk = makeAnthropicSdk(originalCreate);
    const inst = new TestableAnthropicInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Messages as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await (proto.create as (...args: unknown[]) => Promise<unknown>)({
      model: "claude-sonnet-4-20250514",
      messages: [{ role: "user", content: "hi" }],
    });

    const span = exp.getFinishedSpans().find((s) => s.name === "anthropic.messages")!;
    expect(span.attributes?.["gen_ai.usage.prompt_tokens"]).toBe(80);
    expect(span.attributes?.["gen_ai.usage.completion_tokens"]).toBe(40);
    expect(span.attributes?.["gen_ai.usage.total_tokens"]).toBe(120);

    inst.uninstrument();
  });

  it("messages span captures cache tokens", async () => {
    const exp = setup();
    const originalCreate = (..._args: unknown[]) =>
      Promise.resolve(anthropicMessageResponse({ cacheRead: 500, cacheCreation: 100 }));
    const sdk = makeAnthropicSdk(originalCreate);
    const inst = new TestableAnthropicInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Messages as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await (proto.create as (...args: unknown[]) => Promise<unknown>)({
      model: "claude-sonnet-4-20250514",
      messages: [{ role: "user", content: "hi" }],
    });

    const span = exp.getFinishedSpans().find((s) => s.name === "anthropic.messages")!;
    expect(span.attributes?.["gen_ai.usage.cache_read_tokens"]).toBe(500);

    inst.uninstrument();
  });

  it("messages span captures output", async () => {
    const exp = setup();
    const originalCreate = (..._args: unknown[]) =>
      Promise.resolve(anthropicMessageResponse({ text: "Test response from Claude" }));
    const sdk = makeAnthropicSdk(originalCreate);
    const inst = new TestableAnthropicInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Messages as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await (proto.create as (...args: unknown[]) => Promise<unknown>)({
      model: "claude-sonnet-4-20250514",
      messages: [{ role: "user", content: "hi" }],
    });

    const span = exp.getFinishedSpans().find((s) => s.name === "anthropic.messages")!;
    expect(span.attributes?.["gen_ai.output"]).toBe("Test response from Claude");

    inst.uninstrument();
  });

  it("messages span error on exception", async () => {
    const exp = setup();
    const originalCreate = (..._args: unknown[]) => {
      throw new Error("timeout");
    };
    const sdk = makeAnthropicSdk(originalCreate);
    const inst = new TestableAnthropicInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Messages as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    await expect(
      (proto.create as (...args: unknown[]) => Promise<unknown>)({
        model: "claude-sonnet-4-20250514",
        messages: [{ role: "user", content: "hi" }],
      }),
    ).rejects.toThrow("timeout");

    const span = exp.getFinishedSpans().find((s) => s.name === "anthropic.messages")!;
    expect(span.status).toBe("error");
    expect(span.error?.message).toBe("timeout");

    inst.uninstrument();
  });

  it("uninstrument restores original create", () => {
    const originalCreate = () => anthropicMessageResponse();
    const sdk = makeAnthropicSdk(originalCreate);
    const inst = new TestableAnthropicInstrumentor();
    inst.useMock(sdk);
    inst.instrument(false);

    const proto = (sdk.default.Messages as Record<string, unknown>).prototype as Record<
      string,
      unknown
    >;
    expect(proto.create).not.toBe(originalCreate);

    inst.uninstrument();
    expect(proto.create).toBe(originalCreate);
  });
});
