<script lang="ts">
  import { pipelineStateStore } from '$lib/stores/pipeline-state.svelte';

  interface Props {
    bars?: number;
    height?: number;
    color?: string;
  }

  let { bars = 32, height = 64, color = '#10b981' }: Props = $props();

  const isListening = $derived(pipelineStateStore.isListening);
  const barHeights = $state<number[]>(Array(bars).fill(0.1));
  let animationFrame: number | null = null;

  // Simulated audio data for waveform animation
  function generateWaveformData(): number[] {
    const data: number[] = [];
    const time = Date.now() / 200;

    for (let i = 0; i < bars; i++) {
      // Combine multiple sine waves for natural-looking waveform
      const base = Math.sin(time + i * 0.3) * 0.5;
      const harmonic = Math.sin(time * 2 - i * 0.2) * 0.3;
      const noise = (Math.random() - 0.5) * 0.2;
      const value = Math.abs(base + harmonic + noise) + 0.1;
      data.push(Math.min(1, Math.max(0.1, value)));
    }

    return data;
  }

  function animate(): void {
    if (!isListening) {
      // Smoothly return to flat line when not listening
      const allFlat = barHeights.every((h) => h === 0.1);
      if (allFlat) {
        animationFrame = null;
        return;
      }

      for (let i = 0; i < bars; i++) {
        barHeights[i] += (0.1 - barHeights[i]) * 0.2;
      }
    } else {
      const newData = generateWaveformData();
      for (let i = 0; i < bars; i++) {
        // Smooth interpolation
        barHeights[i] += (newData[i] - barHeights[i]) * 0.3;
      }
    }

    animationFrame = requestAnimationFrame(animate);
  }

  $effect(() => {
    if (isListening && !animationFrame) {
      animate();
    } else if (!isListening && animationFrame) {
      // Let the animation complete before stopping
      setTimeout(() => {
        if (!isListening) {
          cancelAnimationFrame(animationFrame!);
          animationFrame = null;
        }
      }, 500);
    }

    return () => {
      if (animationFrame) {
        cancelAnimationFrame(animationFrame);
      }
    };
  });
</script>

<div class="waveform-container" style="height: {height}px">
  <div class="waveform">
    {#each barHeights as barHeight, i}
      <div
        class="bar"
        style="
          height: {barHeight * 100}%;
          background-color: {color};
          transition: height 0.05s ease;
        "
      ></div>
    {/each}
  </div>
</div>

<style>
  .waveform-container {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    padding: 0 8px;
  }

  .waveform {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 3px;
    width: 100%;
    max-width: 400px;
  }

  .bar {
    flex: 1;
    min-width: 3px;
    border-radius: 2px;
    opacity: 0.8;
    box-shadow: 0 0 8px currentColor;
  }
</style>
