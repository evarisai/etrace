import { describe, it, expect, afterEach } from "vitest";
import {
  EtraceLangChainHandler,
  InMemoryExporter,
  RunTracker,
  init,
  langchainHandler,
  shutdown,
  trace,
} from "../src/index.js";

afterEach(() => {
  shutdown();
});

function setup() {
  const exporter = new InMemoryExporter();
  init({ exporters: [exporter], calculateCosts: false, autoInstrument: { llm: false } });
  return exporter;
}

describe("langchainHandler()", () => {
  it("creates a fresh handler", () => {
    expect(langchainHandler()).toBeInstanceOf(EtraceLangChainHandler);
    expect(langchainHandler()).not.toBe(langchainHandler());
  });

  it("captures LLM spans and usage", () => {
    const exporter = setup();
    const handler = langchainHandler();

    handler.handleChatModelStart(
      {},
      [[{ type: "human", content: "hello" }]],
      "llm-1",
      undefined,
      undefined,
      undefined,
      { ls_provider: "openai", ls_model_name: "gpt-4o" },
    );
    handler.handleLLMEnd(
      {
        generations: [
          [
            {
              message: {
                content: "hi",
                response_metadata: {
                  model_name: "gpt-4o-2024-08-06",
                  token_usage: {
                    prompt_tokens: 10,
                    completion_tokens: 5,
                    total_tokens: 15,
                  },
                },
              },
            },
          ],
        ],
      },
      "llm-1",
    );

    const span = exporter.getFinishedSpans()[0];
    expect(span.name).toBe("openai.chat");
    expect(span.kind).toBe("llm");
    expect(span.output).toBe("hi");
    expect(span.usage).toMatchObject({ input: 10, output: 5, total: 15 });
    expect(span.attributes?.["gen_ai.output"]).toBe("hi");
    expect(span.attributes?.["gen_ai.response.model"]).toBe("gpt-4o-2024-08-06");
  });

  it("nests tool spans below the triggering LLM", () => {
    const exporter = setup();
    const handler = langchainHandler();

    handler.handleChainStart({}, {}, "chain-1");
    handler.handleChatModelStart({}, [[{ type: "human", content: "weather" }]], "llm-1", "chain-1");
    handler.handleToolStart({ name: "weather" }, "{}", "tool-1", "chain-1");
    handler.handleToolEnd("sunny", "tool-1");
    handler.handleLLMEnd({ generations: [[{ message: { content: "sunny" } }]] }, "llm-1");

    const spans = exporter.getFinishedSpans();
    const tool = spans.find((span) => span.kind === "tool")!;
    const llm = spans.find((span) => span.kind === "llm")!;
    expect(tool.parentSpanId).toBe(llm.spanId);
  });

  it("inherits parent etrace context", () => {
    const exporter = setup();

    trace(
      "agent",
      () => {
        const handler = langchainHandler();
        handler.handleLLMStart({}, ["hello"], "llm-1");
        handler.handleLLMEnd({ generations: [[{ text: "hi" }]] }, "llm-1");
      },
      { kind: "agent" },
    );

    const spans = exporter.getFinishedSpans();
    const agent = spans.find((span) => span.kind === "agent")!;
    const llm = spans.find((span) => span.kind === "llm")!;
    expect(llm.traceId).toBe(agent.traceId);
    expect(llm.parentSpanId).toBe(agent.spanId);
  });
});

describe("RunTracker", () => {
  it("creates nested framework spans from run ids", () => {
    const exporter = setup();
    const tracker = new RunTracker();

    tracker.onRunStart("agent-run", { runId: "agent", kind: "agent" });
    tracker.onRunStart("llm-run", { runId: "llm", parentRunId: "agent", kind: "llm" });
    tracker.onRunEnd("llm", { output: "done" });
    tracker.onRunEnd("agent");

    const spans = exporter.getFinishedSpans();
    const agent = spans.find((span) => span.name === "agent-run")!;
    const llm = spans.find((span) => span.name === "llm-run")!;
    expect(llm.traceId).toBe(agent.traceId);
    expect(llm.parentSpanId).toBe(agent.spanId);
  });
});
