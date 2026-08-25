/**
 * Gateway configuration loader.
 * Reads from environment variables and the existing config.yaml.
 */

import { type GatewayConfig, type ProviderConfig } from "./types";

export function loadConfig(): GatewayConfig {
  return {
    port: parseInt(Bun.env.GATEWAY_PORT || "3000", 10),
    host: Bun.env.GATEWAY_HOST || "127.0.0.1",
    provider: Bun.env.ECHO_DEFAULT_PROVIDER || "gemini-live",
    metricsWindow: 100,
    sessionTimeoutSeconds: 300,
    providers: loadProviderConfigs(),
  };
}

function loadProviderConfigs(): Record<string, ProviderConfig> {
  return {
    "gemini-live": {
      apiKey: Bun.env.GEMINI_API_KEY || "",
      model: Bun.env.GEMINI_MODEL || "gemini-3.1-flash-live-preview",
      voice: Bun.env.GEMINI_VOICE || "Puck",
    },
    "openai-realtime": {
      apiKey: Bun.env.OPENAI_API_KEY || "",
      model: Bun.env.OPENAI_REALTIME_MODEL || "gpt-4o-realtime-preview-2024-12-17",
      voice: Bun.env.OPENAI_VOICE || "alloy",
    },
    hermes: {
      apiKey: Bun.env.HERMES_API_KEY || "",
      baseUrl: Bun.env.HERMES_URL || "http://127.0.0.1:8642/v1",
      model: "hermes-agent",
      timeout: 90,
    },
    "pi-agent": {
      command: ["pi", "-p"],
      timeout: 120,
    },
  };
}

export function getProviderConfig(provider: string, config: GatewayConfig): ProviderConfig | undefined {
  return config.providers[provider];
}

export function listAvailableProviders(config: GatewayConfig): string[] {
  return Object.keys(config.providers).filter((name) => {
    const p = config.providers[name];
    // A provider is "available" if it has an API key (for cloud) or is always available (for local)
    if (name === "hermes" || name === "pi-agent") return true;
    return !!(p.apiKey);
  });
}
