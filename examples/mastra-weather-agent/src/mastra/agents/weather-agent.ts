import "dotenv/config";

import { createOpenAI } from "@ai-sdk/openai";
import { Agent } from "@mastra/core/agent";
import { weatherTool } from "../tools/weather-tool";

const ZAI_OPENAI_BASE_URL = "https://api.z.ai/api/paas/v4/";

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}

const zai = createOpenAI({
  apiKey:
    process.env.OPENAI_API_KEY ??
    process.env.ZAI_API_KEY ??
    requireEnv("ZAI_API_KEY"),
  baseURL: process.env.OPENAI_BASE_URL ?? ZAI_OPENAI_BASE_URL,
});

export const weatherAgent = new Agent({
  id: "weather-agent",
  name: "Weather Agent",
  instructions: `
You are a concise weather assistant.

Rules:
- Ask for a location if none is provided.
- Translate non-English location names before using the weather tool.
- For multi-part locations such as "New York, NY", use the most relevant city/place.
- Always use weatherTool for current weather questions.
- Include conditions, temperature, feels-like temperature, humidity, wind, gusts, and precipitation when available.
- If the user asks for activity ideas, base them on the fetched weather and keep the answer practical.
- Do not mention scorers, evaluation, or implementation details.
  `,
  model: zai.chat(process.env.OPENAI_MODEL ?? "glm-5.1"),
  tools: { weatherTool },
});
