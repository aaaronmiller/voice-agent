<script lang="ts">
  import { pipelineStateStore, type PipelineState } from '$lib/stores/pipeline-state.svelte';

  interface Props {
    compact?: boolean;
  }

  let { compact = false }: Props = $props();

  const state = $derived(pipelineStateStore.state);

  const stateConfig: Record<PipelineState, { label: string; color: string; pulse: boolean }> = {
    dormant: { label: 'Standby', color: '#6b7280', pulse: false },
    triggered: { label: 'Active', color: '#f59e0b', pulse: true },
    listening: { label: 'Listening', color: '#10b981', pulse: true },
    processing: { label: 'Processing', color: '#8b5cf6', pulse: true },
    speaking: { label: 'Speaking', color: '#3b82f6', pulse: false },
  };

  const config = $derived(stateConfig[state]);
</script>

<div class="status-indicator" class:compact>
  <div class="indicator-ring">
    <div
      class="indicator-dot"
      style="background-color: {config.color}"
      class:pulse={config.pulse}
    ></div>
    {#if config.pulse}
      <div class="pulse-ring" style="background-color: {config.color}"></div>
    {/if}
  </div>
  {#if !compact}
    <span class="status-label">{config.label}</span>
  {/if}
</div>

<style>
  .status-indicator {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 16px;
    background: rgba(0, 0, 0, 0.3);
    border-radius: 9999px;
    backdrop-filter: blur(8px);
  }

  .status-indicator.compact {
    padding: 4px;
  }

  .indicator-ring {
    position: relative;
    width: 16px;
    height: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .indicator-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    transition: background-color 0.3s ease;
  }

  .indicator-dot.pulse {
    animation: pulse 1.5s ease-in-out infinite;
  }

  .pulse-ring {
    position: absolute;
    width: 100%;
    height: 100%;
    border-radius: 50%;
    opacity: 0.3;
    animation: ripple 1.5s ease-out infinite;
  }

  .status-label {
    font-size: 14px;
    font-weight: 500;
    color: rgba(255, 255, 255, 0.9);
    text-transform: capitalize;
    letter-spacing: 0.025em;
  }

  @keyframes pulse {
    0%, 100% {
      opacity: 1;
      transform: scale(1);
    }
    50% {
      opacity: 0.5;
      transform: scale(0.9);
    }
  }

  @keyframes ripple {
    0% {
      transform: scale(0.8);
      opacity: 0.5;
    }
    100% {
      transform: scale(2);
      opacity: 0;
    }
  }
</style>
