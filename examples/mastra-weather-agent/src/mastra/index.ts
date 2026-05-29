import { Mastra } from "@mastra/core/mastra";
import { PinoLogger } from "@mastra/loggers";
import { weatherAgent } from "./agents/weather-agent";
import "./tracing";

export const mastra = new Mastra({
  agents: { weatherAgent },
  logger: new PinoLogger({
    name: "etrace-mastra-weather-agent",
    level: "info",
  }),
});
