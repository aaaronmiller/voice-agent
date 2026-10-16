/**
 * Audio utilities for Echo-Node frontend
 * Handles audio playback, amplitude analysis, and lip-sync data
 */

export interface AudioAnalysis {
  amplitude: number;
  frequency: number;
  rms: number;
}

/**
 * Create an AudioContext and analyser for audio processing
 */
export function createAudioAnalyser(): {
  context: AudioContext;
  analyser: AnalyserNode;
  source: MediaElementAudioSourceNode | null;
} {
  const context = new AudioContext({
    sampleRate: 44100,
  });

  const analyser = context.createAnalyser();
  analyser.fftSize = 256;
  analyser.smoothingTimeConstant = 0.8;

  return {
    context,
    analyser,
    source: null,
  };
}

/**
 * Calculate amplitude from audio data (0-1 range)
 */
export function calculateAmplitude(analyser: AnalyserNode): number {
  const dataArray = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteFrequencyData(dataArray);

  // Calculate RMS (root mean square) amplitude
  let sum = 0;
  for (let i = 0; i < dataArray.length; i++) {
    const value = dataArray[i] / 255; // Normalize to 0-1
    sum += value * value;
  }

  return Math.sqrt(sum / dataArray.length);
}

/**
 * Play an audio buffer with optional gain control
 */
export async function playAudioBuffer(
  context: AudioContext,
  buffer: ArrayBuffer,
  gain: number = 1.0
): Promise<void> {
  try {
    const audioBuffer = await context.decodeAudioData(buffer);
    const source = context.createBufferSource();
    source.buffer = audioBuffer;

    const gainNode = context.createGain();
    gainNode.gain.value = gain;

    source.connect(gainNode);
    gainNode.connect(context.destination);
    source.start(0);

    return new Promise((resolve) => {
      source.onended = resolve;
    });
  } catch (error) {
    console.error('[AudioUtils] Failed to play audio buffer:', error);
    throw error;
  }
}

/**
 * Convert ArrayBuffer to Blob URL for audio playback
 */
export function arrayBufferToBlobUrl(buffer: ArrayBuffer, mimeType: string = 'audio/wav'): string {
  const blob = new Blob([buffer], { type: mimeType });
  return URL.createObjectURL(blob);
}

/**
 * Revoke a Blob URL to free memory
 */
export function revokeBlobUrl(url: string): void {
  URL.revokeObjectURL(url);
}

/**
 * Create a simple beep sound for activation feedback
 */
export function playActivationSound(
  context: AudioContext,
  frequency: number = 440,
  duration: number = 0.1
): void {
  const oscillator = context.createOscillator();
  const gainNode = context.createGain();

  oscillator.type = 'sine';
  oscillator.frequency.value = frequency;

  gainNode.gain.setValueAtTime(0.3, context.currentTime);
  gainNode.gain.exponentialRampToValueAtTime(0.01, context.currentTime + duration);

  oscillator.connect(gainNode);
  gainNode.connect(context.destination);

  oscillator.start(context.currentTime);
  oscillator.stop(context.currentTime + duration);
}

/**
 * Analyze audio data for visualization
 */
export function getFrequencyData(analyser: AnalyserNode): Uint8Array {
  const dataArray = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteFrequencyData(dataArray);
  return dataArray;
}

/**
 * Get time domain data for waveform visualization
 */
export function getTimeDomainData(analyser: AnalyserNode): Uint8Array {
  const dataArray = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteTimeDomainData(dataArray);
  return dataArray;
}
