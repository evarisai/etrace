import { createTool } from "@mastra/core/tools";
import { z } from "zod";
import { trace, setOutput } from "../../etrace";

interface GeocodingResponse {
  results?: Array<{
    latitude: number;
    longitude: number;
    name: string;
    country?: string;
    admin1?: string;
  }>;
}

interface WeatherResponse {
  current: {
    time: string;
    temperature_2m: number;
    apparent_temperature: number;
    relative_humidity_2m: number;
    wind_speed_10m: number;
    wind_gusts_10m: number;
    precipitation: number;
    weather_code: number;
  };
}

export const weatherTool = createTool({
  id: "get-weather",
  description: "Get current weather for a location using Open-Meteo.",
  inputSchema: z.object({
    location: z.string().describe("City or place name"),
  }),
  outputSchema: z.object({
    temperature: z.number(),
    feelsLike: z.number(),
    humidity: z.number(),
    windSpeed: z.number(),
    windGust: z.number(),
    precipitation: z.number(),
    conditions: z.string(),
    location: z.string(),
    observedAt: z.string(),
  }),
  execute: async (context) =>
    trace(
      "get-weather",
      async () => {
        const result = await getWeather(context.location);
        setOutput(result);
        return result;
      },
      {
        kind: "tool",
        input: context,
        attributes: { "etrace.kind": "tool", "tool.name": "get-weather" },
      },
    ),
});

async function getWeather(location: string) {
  const geocodingUrl = `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(
    location,
  )}&count=1&language=en&format=json`;
  const geocodingResponse = await fetch(geocodingUrl);
  if (!geocodingResponse.ok) {
    throw new Error(
      `Geocoding failed: ${geocodingResponse.status} ${geocodingResponse.statusText}`,
    );
  }

  const geocodingData = (await geocodingResponse.json()) as GeocodingResponse;
  const match = geocodingData.results?.[0];
  if (!match) throw new Error(`Location '${location}' not found`);

  const displayLocation = [match.name, match.admin1, match.country]
    .filter(Boolean)
    .join(", ");
  const weatherUrl =
    `https://api.open-meteo.com/v1/forecast?latitude=${match.latitude}&longitude=${match.longitude}` +
    "&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,precipitation,weather_code";
  const response = await fetch(weatherUrl);
  if (!response.ok) {
    throw new Error(
      `Weather fetch failed: ${response.status} ${response.statusText}`,
    );
  }

  const data = (await response.json()) as WeatherResponse;
  return {
    temperature: data.current.temperature_2m,
    feelsLike: data.current.apparent_temperature,
    humidity: data.current.relative_humidity_2m,
    windSpeed: data.current.wind_speed_10m,
    windGust: data.current.wind_gusts_10m,
    precipitation: data.current.precipitation,
    conditions: getWeatherCondition(data.current.weather_code),
    location: displayLocation,
    observedAt: data.current.time,
  };
}

function getWeatherCondition(code: number): string {
  const conditions: Record<number, string> = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
  };
  return conditions[code] ?? "Unknown";
}
