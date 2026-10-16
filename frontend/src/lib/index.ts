/**
 * Echo-Node Frontend - Component Exports
 */

// Components
export { default as Frame } from './components/frame.svelte';
export { default as AvatarDisplay } from './components/avatar-display.svelte';
export { default as StatusIndicator } from './components/status-indicator.svelte';
export { default as Waveform } from './components/waveform.svelte';
export { default as Transcript } from './components/transcript.svelte';

// Stores
export { websocketStore, useWebSocket } from './stores/websocket.svelte';
export { pipelineStateStore, usePipelineState } from './stores/pipeline-state.svelte';

// Types
export type { ThemeName } from './components/frame.svelte';
export type { PipelineState } from './stores/pipeline-state.svelte';
export type { WebSocketStatus, WebSocketMessage } from './stores/websocket.svelte';
