/**
 * Auto-shutdown test — verifies that init() registers process exit handlers
 * and users don't need to call shutdown() manually.
 */
import { describe, it, expect, afterEach } from "vitest";
import { init, shutdown, isInitialized, InMemoryExporter } from "../src/index.js";

afterEach(() => {
  shutdown();
});

describe("auto-shutdown", () => {
  it("init() registers exit handler — shutdown fires automatically", () => {
    const exporter = new InMemoryExporter();
    init({ exporters: [exporter], autoInstrument: { llm: false } });
    expect(isInitialized()).toBe(true);

    // Simulate process exit event
    const exitHandlers = process.listeners("exit");
    expect(exitHandlers.length).toBeGreaterThan(0);

    // Manually invoke the last registered exit handler
    // (the one we registered in init())
    const etraceHandler = exitHandlers[exitHandlers.length - 1];
    etraceHandler();

    // After exit handler fires, state should be cleaned up
    expect(isInitialized()).toBe(false);
  });

  it("shutdown() is idempotent — safe to call even after auto-shutdown", () => {
    init({ autoInstrument: { llm: false } });
    const exitHandlers = process.listeners("exit");
    exitHandlers[exitHandlers.length - 1]();

    // Should not throw — shutdown is best-effort
    expect(() => shutdown()).not.toThrow();
  });
});
