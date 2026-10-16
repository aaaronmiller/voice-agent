/**
 * Pipeline state store for Echo-Node
 * Tracks the 5-state machine: DORMANT → TRIGGERED → LISTENING → PROCESSING → SPEAKING
 * Uses Svelte 5 $state runes for reactivity
 */

export type PipelineState = 'dormant' | 'triggered' | 'listening' | 'processing' | 'speaking';

export interface TranscriptEntry {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  timestamp: number;
  isFinal: boolean;
}

export interface VramReport {
  total_mb: number;
  used_mb: number;
  available_mb: number;
}

class PipelineStateStore {
  state = $state<PipelineState>('dormant');
  transcript = $state<TranscriptEntry[]>([]);
  partialTranscript = $state<string>('');
  currentResponse = $state<string>('');
  error = $state<string | null>(null);
  vramReport = $state<VramReport | null>(null);

  #stateHistory: Array<{ state: PipelineState; timestamp: number }> = $state([]);
  #maxTranscriptLength = 50; // Keep last 50 entries

  constructor() {
    this.#stateHistory = [];
  }

  /**
   * Update the pipeline state
   */
  setState(newState: PipelineState): void {
    const oldState = this.state;
    this.state = newState;
    this.#stateHistory.push({ state: newState, timestamp: Date.now() });

    // Clear partial transcript on state change
    if (newState !== 'listening') {
      this.partialTranscript = '';
    }

    console.log(`[Pipeline] State: ${oldState} → ${newState}`);
  }

  /**
   * Add a partial transcript update (streaming STT)
   */
  setPartialTranscript(text: string): void {
    this.partialTranscript = text;
  }

  /**
   * Add a final transcript entry
   */
  addTranscript(text: string, role: 'user' | 'assistant' = 'user'): void {
    const entry: TranscriptEntry = {
      id: crypto.randomUUID(),
      role,
      text,
      timestamp: Date.now(),
      isFinal: true,
    };

    this.transcript.push(entry);

    // Trim if too long
    if (this.transcript.length > this.#maxTranscriptLength) {
      this.transcript = this.transcript.slice(-this.#maxTranscriptLength);
    }
  }

  /**
   * Update the current LLM response being built
   */
  appendResponse(token: string): void {
    this.currentResponse += token;
  }

  /**
   * Finalize the current response and add to transcript
   */
  finalizeResponse(): void {
    if (this.currentResponse.trim()) {
      this.addTranscript(this.currentResponse.trim(), 'assistant');
    }
    this.currentResponse = '';
  }

  /**
   * Set an error state
   */
  setError(message: string, code?: string): void {
    this.error = code ? `[${code}] ${message}` : message;
    console.error(`[Pipeline] Error: ${this.error}`);
  }

  /**
   * Clear the error state
   */
  clearError(): void {
    this.error = null;
  }

  /**
   * Update VRAM report
   */
  setVramReport(report: VramReport): void {
    this.vramReport = report;
  }

  /**
   * Clear the transcript
   */
  clearTranscript(): void {
    this.transcript = [];
    this.partialTranscript = '';
    this.currentResponse = '';
  }

  /**
   * Get the current state with derived properties
   */
  get isActive(): boolean {
    return this.state !== 'dormant';
  }

  get isListening(): boolean {
    return this.state === 'listening';
  }

  get isSpeaking(): boolean {
    return this.state === 'speaking';
  }

  get isProcessing(): boolean {
    return this.state === 'processing';
  }

  /**
   * Get state transition history
   */
  get history(): Array<{ state: PipelineState; timestamp: number }> {
    return [...this.#stateHistory];
  }

  /**
   * Get time spent in current state (ms)
   */
  get currentStateDuration(): number {
    const lastTransition = this.#stateHistory[this.#stateHistory.length - 1];
    return lastTransition ? Date.now() - lastTransition.timestamp : 0;
  }
}

// Singleton instance
export const pipelineStateStore = new PipelineStateStore();

// Hook for Svelte 5 components
export function usePipelineState() {
  return pipelineStateStore;
}
