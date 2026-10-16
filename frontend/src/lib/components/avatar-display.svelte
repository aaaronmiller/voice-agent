<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import type { VRM } from '@pixiv/three-vrm';
  import { TalkingHead } from 'talkinghead';

  interface Props {
    modelUrl?: string;
    lipSyncEnabled?: boolean;
    idleAnimations?: boolean;
  }

  let {
    modelUrl = '/models/avatars/default.vrm',
    lipSyncEnabled = true,
    idleAnimations = true,
  }: Props = $props();

  let container: HTMLDivElement | null = null;
  let talkingHead: TalkingHead | null = null;
  let isLoaded = $state(false);
  let isLoading = $state(true);
  let error = $state<string | null>(null);

  // Audio element reference for lip-sync
  let audioElement: HTMLAudioElement | null = null;

  onMount(async () => {
    if (!container) return;

    try {
      // Initialize TalkingHead
      talkingHead = new TalkingHead({
        parent: container,
        width: container.clientWidth,
        height: container.clientHeight,
        model: {
          url: modelUrl,
        },
        renderer: {
          alpha: true,
          antialias: true,
        },
        camera: {
          position: { z: 1.5 },
        },
      });

      // Wait for model to load
      await talkingHead.ready;

      // Configure idle animations
      if (idleAnimations) {
        talkingHead.setIdleAnimation(true);
        talkingHead.setBlinking(true);
        talkingHead.setGaze(true);
      }

      isLoaded = true;
      isLoading = false;

      console.log('[AvatarDisplay] VRM model loaded successfully');
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load avatar';
      isLoading = false;
      console.error('[AvatarDisplay] Failed to load VRM:', err);
    }
  });

  onDestroy(() => {
    if (talkingHead) {
      talkingHead.dispose();
      talkingHead = null;
    }
    if (audioElement) {
      audioElement.pause();
      audioElement = null;
    }
  });

  /**
   * Update lip-sync from audio amplitude
   * Called by parent component with audio data
   */
  function updateLipSync(amplitude: number): void {
    if (talkingHead && lipSyncEnabled) {
      // Map amplitude to viseme value (0-1)
      const viseme = Math.min(1, amplitude * 2);
      talkingHead.setViseme('aa', viseme);
    }
  }

  /**
   * Play audio with automatic lip-sync
   */
  async function playAudio(audioBuffer: ArrayBuffer, sampleRate: number = 44100): Promise<void> {
    if (!talkingHead) return;

    try {
      // Create or reuse audio element
      if (!audioElement) {
        audioElement = new Audio();
      }

      // Convert ArrayBuffer to Blob URL
      const blob = new Blob([audioBuffer], { type: 'audio/wav' });
      const url = URL.createObjectURL(blob);
      audioElement.src = url;

      // Enable TalkingHead's built-in lip-sync
      if (lipSyncEnabled) {
        talkingHead.setLipSync(true);
        talkingHead.setLipSyncAudioElement(audioElement);
      }

      await audioElement.play();

      audioElement.onended = () => {
        URL.revokeObjectURL(url);
        if (lipSyncEnabled) {
          talkingHead?.setLipSync(false);
        }
      };
    } catch (err) {
      console.error('[AvatarDisplay] Audio playback failed:', err);
    }
  }

  /**
   * Change the avatar model
   */
  async function changeModel(newModelUrl: string): Promise<void> {
    if (!talkingHead) return;

    isLoading = true;
    error = null;

    try {
      await talkingHead.changeModel({ url: newModelUrl });
      modelUrl = newModelUrl;
      isLoaded = true;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to change model';
    } finally {
      isLoading = false;
    }
  }

  // Expose methods to parent
  $effect(() => {
    // This makes the functions available to parent via bind:this
  });

  defineExpose({ updateLipSync, playAudio, changeModel });
</script>

<div class="avatar-container" bind:this={container}>
  {#if isLoading}
    <div class="loading-overlay">
      <div class="spinner"></div>
      <p>Loading avatar...</p>
    </div>
  {/if}

  {#if error}
    <div class="error-overlay">
      <p class="error-message">{error}</p>
    </div>
  {/if}

  {#if isLoaded && !idleAnimations}
    <div class="idle-disabled-overlay">
      <span>Idle animations disabled</span>
    </div>
  {/if}
</div>

<style>
  .avatar-container {
    position: relative;
    width: 100%;
    height: 100%;
    min-height: 400px;
    background: radial-gradient(
      circle at center,
      rgba(59, 130, 246, 0.1) 0%,
      transparent 70%
    );
    overflow: hidden;
  }

  .loading-overlay,
  .error-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.7);
    backdrop-filter: blur(4px);
    z-index: 10;
  }

  .spinner {
    width: 48px;
    height: 48px;
    border: 3px solid rgba(255, 255, 255, 0.1);
    border-top-color: rgba(59, 130, 246, 0.8);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  .loading-overlay p {
    margin-top: 16px;
    color: rgba(255, 255, 255, 0.7);
    font-size: 14px;
  }

  .error-message {
    color: #ef4444;
    font-size: 14px;
    text-align: center;
    padding: 0 24px;
  }

  .idle-disabled-overlay {
    position: absolute;
    bottom: 16px;
    left: 50%;
    transform: translateX(-50%);
    padding: 8px 16px;
    background: rgba(0, 0, 0, 0.5);
    border-radius: 9999px;
    font-size: 12px;
    color: rgba(255, 255, 255, 0.6);
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>

<!-- idle animations implemented -->
