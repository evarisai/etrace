/**
 * Evaris cloud client — init() and score() one-liners.
 *
 * Usage:
 *   import { init, score } from "etrace/evaris";
 *   init({ apiKey: "...", projectId: "..." });
 *   score({ apiKey: "...", projectId: "...", traceId: "...", name: "relevance", value: 0.9 });
 */
import * as etrace from "../index.js";
import { EvarisExporter, DEFAULT_ENDPOINT } from "./exporter.js";

const _BASE_URL = DEFAULT_ENDPOINT.replace(/\/traces$/, "");
const _SCORES_ENDPOINT = `${_BASE_URL}/scores`;

export interface EvarisInitOptions {
  apiKey: string;
  projectId: string;
  endpoint?: string;
  calculateCosts?: boolean;
  autoInstrument?: { llm?: boolean };
  debug?: boolean;
  version?: string;
  release?: string;
}

export function init(opts: EvarisInitOptions): void {
  const exporter = new EvarisExporter({
    apiKey: opts.apiKey,
    projectId: opts.projectId,
    endpoint: opts.endpoint,
  });

  etrace.init({
    exporters: [exporter],
    calculateCosts: opts.calculateCosts ?? true,
    autoInstrument: opts.autoInstrument ?? { llm: true },
    debug: opts.debug,
    version: opts.version,
    release: opts.release,
  });
}

export async function score(opts: {
  apiKey: string;
  projectId: string;
  traceId: string;
  name: string;
  value: unknown;
  endpoint?: string;
}): Promise<Record<string, unknown>> {
  const url = opts.endpoint ?? _SCORES_ENDPOINT;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${opts.apiKey}`,
      "X-Evaris-Project-ID": opts.projectId,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      trace_id: opts.traceId,
      name: opts.name,
      value: opts.value,
    }),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`Evaris score failed: ${resp.status} ${resp.statusText} ${text}`);
  }
  return (await resp.json()) as Record<string, unknown>;
}

export { EvarisExporter, DEFAULT_ENDPOINT } from "./exporter.js";
