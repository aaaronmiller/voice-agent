/**
 * Shared TypeScript Types for Echo-Node
 * 
 * Type definitions for WebSocket events, configuration, and state.
 */

import type { EchoNodeConfig } from './config-loader';

/**
 * Pipeline states
 */
export type PipelineState = 'dormant' | 'triggered' | 'listening' | 'processing' | 'speaking';

/**
 * Events from Python worker → Gateway → Frontend
 */
export type WorkerEvent =
  | { type: 'state_change'; from: PipelineState; to: PipelineState; timestamp: number }
  | { type: 'transcript_partial'; text: string }
  | { type: 'transcript_final'; text: string }
  | { type: 'llm_token'; token: string }
  | { type: 'llm_complete'; text: string }
  | { type: 'tts_audio'; data: ArrayBuffer; sample_rate: number }
  | { type: 'tts_complete' }
  | { type: 'vram_report'; total_mb: number; used_mb: number; available_mb: number }
  | { type: 'error'; message: string; code: string }
  | { type: 'ready' };  // Startup complete, ready for voice input

/**
 * Events from Frontend → Gateway → Python worker
 */
export type ClientEvent =
  | { type: 'keyboard_trigger' }  // Manual activation (bypass wake word)
  | { type: 'barge_in' }  // Interrupt speaking
  | { type: 'config_update'; config: Partial<EchoNodeConfig> }
  | { type: 'stop' };  // Halt pipeline

/**
 * Gateway REST API types
 */
export interface HealthResponse {
  status: 'ok' | 'error';
  worker_connected: boolean;
  pipeline_state: PipelineState;
  uptime_seconds: number;
}

export interface StatusResponse {
  state: PipelineState;
  session_active: boolean;
  current_personality: string;
  conversation_turns: number;
  vram?: {
    total_mb: number;
    used_mb: number;
    available_mb: number;
  };
}

export interface ConfigUpdateRequest {
  personality?: { active: string };
  stt?: { provider?: string; threshold?: number };
  tts?: { provider?: string; voice?: string };
  llm?: { provider?: string; model?: string; base_url?: string };
  [key: string]: unknown;
}

export interface ConfigUpdateResponse {
  success: boolean;
  restarted_components: string[];
  message: string;
}

export interface PersonalityInfo {
  name: string;
  description: string;
}

export interface PersonalitiesResponse {
  built_in: PersonalityInfo[];
  custom: PersonalityInfo[];
}

export interface AvatarInfo {
  model: string;
  display_name: string;
}

export interface AvatarsResponse {
  bundled: AvatarInfo[];
  custom: AvatarInfo[];
}

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    suggestion?: string;
  };
}

/**
 * Session types
 */
export interface Session {
  id: string;
  client_id: string;
  started_at: number;
  personality: string;
  conversation_history: Turn[];
  current_state: PipelineState;
}

export interface Turn {
  turn_number: number;
  user_transcript: string;
  assistant_response: string;
  timestamp: number;
}

/**
 * WebSocket message wrapper
 */
export interface WSMessage<T> {
  type: string;
  payload: T;
  timestamp?: number;
}
