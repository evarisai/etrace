import { trace, setOutput, shutdown } from "./etrace";
import "./mastra/tracing";
import { weatherAgent } from "./mastra/agents/weather-agent";

async function main() {
  const prompt =
    process.argv.slice(2).join(" ") ||
    "What is the weather in Bengaluru and should I go for a run?";

  try {
    const result = await trace(
      "weather-agent",
      async () => {
        const response = await weatherAgent.generate(prompt);
        const text = response.text;
        setOutput(text);
        return text;
      },
      {
        kind: "agent",
        input: prompt,
        model: process.env.OPENAI_MODEL ?? "glm-5.1",
        provider: "zai",
      },
    );

    console.log(result);
  } finally {
    await shutdown();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
