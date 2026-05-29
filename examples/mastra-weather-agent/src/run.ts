import { agent as etraceAgent } from "./etrace";
import "./mastra/tracing";
import { weatherAgent as mastraWeatherAgent } from "./mastra/agents/weather-agent";

const tracedWeatherAgent = etraceAgent(async function runWeatherAgent(
  prompt: string,
): Promise<string> {
  const response = await mastraWeatherAgent.generate(prompt);
  return response.text;
});

async function main() {
  const prompt =
    process.argv.slice(2).join(" ") ||
    "What is the weather in Bengaluru and should I go for a run?";

  const result = await tracedWeatherAgent(prompt);
  console.log(result);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
