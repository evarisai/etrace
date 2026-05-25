/**
 * etrace-evaris — Evaris cloud backend plugin.
 *
 * Usage:
 *   import { init, score, EvarisExporter } from "etrace/evaris";
 *   init({ apiKey: "...", projectId: "..." });
 */
export { init, score, EvarisExporter, DEFAULT_ENDPOINT } from "./client.js";
export type { EvarisInitOptions } from "./client.js";
