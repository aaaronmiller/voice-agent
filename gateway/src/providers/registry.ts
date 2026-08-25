/**
 * Provider registry.
 * Maps provider names to their real implementations.
 * Each provider implements the VoiceProvider interface.
 *
 * Lazy imports — providers are loaded only when selected,
 * keeping memory usage minimal.
 */

import { type VoiceProvider, type GatewayConfig } from "../types";

type ProviderFactory = (config: GatewayConfig) => Promise<VoiceProvider>;

const registry = new Map<string, ProviderFactory>();

/** Register a provider factory. */
export function registerProvider(name: string, factory: ProviderFactory): void {
  registry.set(name, factory);
}

/** Instantiate a provider by name. Returns null if not found or fails. */
export async function createProvider(
  name: string,
  config: GatewayConfig
): Promise<VoiceProvider | null> {
  const factory = registry.get(name);
  if (!factory) {
    console.error(`[provider] unknown provider: ${name}`);
    return null;
  }
  try {
    const provider = await factory(config);
    await provider.init();
    return provider;
  } catch (err) {
    console.error(`[provider] failed to create ${name}:`, err);
    return null;
  }
}

/** List all registered provider names. */
export function listProviders(): string[] {
  return Array.from(registry.keys());
}

// ── REAL provider implementations ──

// Stub — for testing the gateway pipeline without real APIs
registerProvider("stub", async (_config: GatewayConfig) => {
  const { StubProvider } = await import("./stub");
  return new StubProvider();
});

// Gemini Multimodal Live — real Google API, bidirectional audio
registerProvider("gemini-live", async (config: GatewayConfig) => {
  const { GeminiLiveProvider } = await import("./gemini-live");
  const provider = new GeminiLiveProvider(config.providers["gemini-live"] || {});
  return provider;
});

// OpenAI Realtime — real OpenAI API, bidirectional audio with server VAD
registerProvider("openai-realtime", async (config: GatewayConfig) => {
  const { OpenAIRealtimeProvider } = await import("./openai-realtime");
  const provider = new OpenAIRealtimeProvider(config.providers["openai-realtime"] || {});
  return provider;
});

// Hermes Agent — text-in/text-out, connects to local Hermes API server
registerProvider("hermes", async (config: GatewayConfig) => {
  const { HermesProvider } = await import("./hermes");
  return new HermesProvider(config.providers["hermes"] || {});
});

// Pi Agent — subprocess-based, text-in/text-out
registerProvider("pi-agent", async (config: GatewayConfig) => {
  const { PiProvider } = await import("./pi-agent");
  return new PiProvider(config.providers["pi-agent"] || {});
});

// Python Worker — stdio bridge to the existing assistant_v2.py
registerProvider("python-worker", async (config: GatewayConfig) => {
  const { PythonWorkerProvider } = await import("./python-worker");
  return new PythonWorkerProvider(config.providers["python-worker"] || {});
});
