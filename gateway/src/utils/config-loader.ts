/**
 * Configuration Loader for Echo-Node Gateway
 * 
 * Parses and validates config.yaml for the Bun/Hono gateway.
 */

import { readFileSync, existsSync } from 'fs';
import { parse } from 'yaml';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

export interface EchoNodeConfig {
  echo_node: { name: string; version: string };
  pipeline_mode?: 'local' | 'cloud';
  audio: { sample_rate: number; channels: number; chunk_size: number; device: string | null };
  wake_word: { provider: string; model: string; threshold: number; cooldown_ms: number };
  activation_sound: { enabled: boolean; sound: string };
  vad: { provider: string; threshold: number; min_speech_ms: number; max_silence_ms: number };
  stt: { provider: string; model: string; device: string; language: string };
  tts: { provider: string; model: string; voice: string; device: string; streaming: boolean; sample_rate: number };
  llm: { provider: string; model: string; base_url: string; api_key: string; temperature: number; max_tokens: number; tools: unknown[] };
  personality: { active: string; custom_prompt: string };
  conversation: { memory_turns: number; persist_across_sessions: boolean };
  echo_cancellation: { mode: string; speexdsp?: { filter_length: number; frame_size: number } };
  integrations: {
    hermes: { enabled: boolean; url: string; channel_name: string };
    openclaw: { enabled: boolean; skill_dir: string };
    mcp: { enabled: boolean; servers: unknown[] };
  };
  ui: {
    mode: 'web' | 'headless';
    theme: string;
    avatar: { model: string; pool: string[]; idle_animations: boolean; eye_tracking: boolean };
    port: number;
  };
  gateway: { port: number; bind?: string; worker_url: string };
  worker: { port: number; log_level: string };
}

/**
 * Load configuration from config.yaml
 * 
 * @param configPath - Optional custom path to config file
 * @returns Validated configuration object
 */
export function loadConfig(configPath?: string): EchoNodeConfig {
  const path = configPath ?? findConfig();
  const raw = readFileSync(path, 'utf-8');
  const config = parse(raw) as EchoNodeConfig;
  validateConfig(config);
  return config;
}

/**
 * Find config file in current directory or parent directories
 */
function findConfig(): string {
  const candidates = ['config.yaml', 'config.example.yaml'];
  
  // Check current directory
  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  
  // Check parent directory (gateway/../config.yaml)
  const parentDir = join(__dirname, '..');
  for (const candidate of candidates) {
    const parentPath = join(parentDir, candidate);
    if (existsSync(parentPath)) {
      return parentPath;
    }
  }
  
  throw new Error(`No config.yaml or config.example.yaml found. Searched: ${candidates.join(', ')}`);
}

/**
 * Validate configuration
 * 
 * @param config - Configuration object to validate
 */
function validateConfig(config: EchoNodeConfig): void {
  const errors: string[] = [];

  // Required provider fields
  if (!config.stt?.provider) errors.push('stt.provider is required');
  if (!config.tts?.provider) errors.push('tts.provider is required');
  if (!config.llm?.provider) errors.push('llm.provider is required');
  if (!config.wake_word?.provider) errors.push('wake_word.provider is required');

  // Pipeline mode validation
  const pipelineMode = config.pipeline_mode ?? 'local';
  if (pipelineMode !== 'local' && pipelineMode !== 'cloud') {
    errors.push(`Invalid pipeline_mode: ${pipelineMode}. Must be 'local' or 'cloud'`);
  }

  // Cloud mode requires API key
  if (pipelineMode === 'cloud' && !config.llm.api_key) {
    errors.push('llm.api_key is required for cloud pipeline mode');
  }

  // OpenAI-compat provider with non-local URL requires API key
  if (config.llm.provider === 'openai-compat' && !config.llm.api_key) {
    if (!config.llm.base_url.startsWith('http://localhost')) {
      errors.push('llm.api_key is required for cloud LLM providers (OpenRouter/OpenAI)');
    }
  }

  if (errors.length > 0) {
    throw new Error(`Config validation failed:\n${errors.map(e => `  - ${e}`).join('\n')}`);
  }
}

/**
 * Get available provider names for a category
 */
export function getAvailableProviders(category: 'stt' | 'tts' | 'vad' | 'wake_word' | 'llm'): string[] {
  const providers: Record<string, string[]> = {
    stt: ['sherpa-onnx', 'faster-whisper', 'vibevoice-asr'],
    tts: ['kokoro', 'chatterbox', 'orpheus', 'piper'],
    vad: ['silero'],
    wake_word: ['openwakeword'],
    llm: ['ollama', 'openai-compat'],
  };
  return providers[category] || [];
}
