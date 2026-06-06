#!/usr/bin/env node

import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const serverEntry = resolve(__dirname, ".output", "server", "index.mjs");

// Parse CLI flags
const args = process.argv.slice(2);
let port = 3001;

for (let i = 0; i < args.length; i++) {
  if (args[i] === "--port" || args[i] === "-p") {
    port = Number(args[i + 1]) || 3001;
    i++;
  } else if (args[i].startsWith("--port=") || args[i].startsWith("-p=")) {
    port = Number(args[i].split("=")[1]) || 3001;
  } else if (args[i] === "--help" || args[i] === "-h") {
    printHelp();
    process.exit(0);
  } else {
    console.error(`  Unknown option: ${args[i]}`);
    console.error("  Run with --help for usage.\n");
    process.exit(1);
  }
}

function printHelp() {
  console.log(`
  etrace-studio - Local trace inspection UI

  Usage:
    npx etrace-studio [options]

  Options:
    -p, --port <number>   Port to listen on (default: 3001)
    -h, --help            Show this help message

  Example:
    npx etrace-studio
    npx etrace-studio --port 8080

  Point your SDK at the OTLP endpoint:
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:${port}/v1/traces
`);
}

// Set env vars BEFORE importing the Nitro server (it reads these on startup)
process.env.PORT = String(port);
process.env.HOST = "0.0.0.0";

console.log();
console.log("  etrace studio");
console.log("  Trace intake and inspection console");
console.log();
console.log(`  URL: http://localhost:${port}`);
console.log(`  OTLP endpoint: http://localhost:${port}/v1/traces`);
console.log();

try {
  // Dynamic import triggers Nitro's serve(); the server starts listening.
  await import(serverEntry);
} catch (err) {
  if (err.code === "ERR_MODULE_NOT_FOUND") {
    console.error(
      "  Server bundle not found. This package may not have been built correctly.\n"
    );
  } else {
    console.error("  Failed to start etrace-studio:", err.message, "\n");
  }
  process.exit(1);
}
