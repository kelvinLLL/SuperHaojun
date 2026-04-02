import type { Api, Model } from "@mariozechner/pi-ai";

/**
 * Model configuration with support for custom OpenAI-compatible endpoints.
 *
 * Environment variables:
 *   OPENAI_API_KEY   — API key for the provider
 *   OPENAI_BASE_URL  — Base URL (default: https://api.openai.com/v1)
 *   MODEL_ID         — Model identifier (default: gpt-4o)
 */

export interface ModelConfig {
  provider: string;
  modelId: string;
  baseUrl: string;
  apiKey: string;
  api: Api;
}

export function loadModelConfig(): ModelConfig {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    console.error("Error: OPENAI_API_KEY environment variable is required.");
    process.exit(1);
  }

  return {
    provider: process.env.MODEL_PROVIDER ?? "openai",
    modelId: process.env.MODEL_ID ?? "gpt-4o",
    baseUrl: process.env.OPENAI_BASE_URL ?? "https://api.openai.com/v1",
    apiKey,
    api: (process.env.MODEL_API as Api) ?? "openai-completions",
  };
}

export function createModel(config: ModelConfig): Model<"openai-completions"> {
  const isReasoning = /o[1-9]|gpt-5/.test(config.modelId);

  return {
    id: config.modelId,
    name: config.modelId,
    api: "openai-completions",
    provider: config.provider,
    baseUrl: config.baseUrl,
    reasoning: isReasoning,
    input: ["text", "image"],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 200000,
    maxTokens: 100000,
    compat: {
      supportsStore: false,
      supportsDeveloperRole: true,
    },
  };
}
