<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import Frame from '$lib/components/frame.svelte';
  import AvatarDisplay from '$lib/components/avatar-display.svelte';
  import Transcript from '$lib/components/transcript.svelte';
  import StatusIndicator from '$lib/components/status-indicator.svelte';
  import Waveform from '$lib/components/waveform.svelte';
  import { websocketStore, useWebSocket } from '$lib/stores/websocket.svelte';
  import { pipelineStateStore, usePipelineState } from '$lib/stores/pipeline-state.svelte';
  import type { ThemeName } from '$lib/components/frame.svelte';

  // Component state
  let settingsOpen = $state(false);
  let selectedTheme: ThemeName = 'minimal';
  let avatarRef: HTMLDivElement | null = null;
  let avatarComponent: any = null;

  // Use stores
  const ws = useWebSocket();
  const pipeline = usePipelineState();

  // Handle WebSocket events
  let unsubscribeState: (() => void) | null = null;
  let unsubscribeTranscript: (() => void) | null = null;
  let unsubscribeAudio: (() => void) | null = null;

  onMount(() => {
    // Connect to WebSocket
    ws.connect('ws://localhost:3000/ws');

    // Subscribe to state changes
    unsubscribeState = ws.on('state_change', (data) => {
      pipeline.setState(data.to as any);
    });

    // Subscribe to transcript updates
    unsubscribeTranscript = ws.on('transcript_partial', (data) => {
      pipeline.setPartialTranscript(data.text as string);
    });

    ws.on('transcript_final', (data) => {
      pipeline.addTranscript(data.text as string, 'user');
    });

    ws.on('llm_token', (data) => {
      pipeline.appendResponse(data.token as string);
    });

    ws.on('llm_complete', () => {
      pipeline.finalizeResponse();
    });

    // Subscribe to TTS audio
    unsubscribeAudio = ws.on('tts_audio', async (data) => {
      if (avatarComponent?.playAudio) {
        await avatarComponent.playAudio(data.data as ArrayBuffer, data.sample_rate as number);
      }
    });

    // Subscribe to errors
    ws.on('error', (data) => {
      pipeline.setError(data.message as string, data.code as string);
    });

    // Subscribe to VRAM report
    ws.on('vram_report', (data) => {
      pipeline.setVramReport(data as any);
    });

    // Keyboard trigger (spacebar to activate)
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.code === 'Space' && !event.repeat) {
        event.preventDefault();
        ws.send({ type: 'keyboard_trigger' });
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      ws.disconnect();
      unsubscribeState?.();
      unsubscribeTranscript?.();
      unsubscribeAudio?.();
      window.removeEventListener('keydown', handleKeyDown);
    };
  });

  function toggleSettings(): void {
    settingsOpen = !settingsOpen;
  }

  function handleBargeIn(): void {
    ws.send({ type: 'barge_in' });
  }

  function handleStop(): void {
    ws.send({ type: 'stop' });
  }
</script>

<svelte:head>
  <title>Echo-Node Voice AI</title>
  <meta name="description" content="Modular open-source voice AI interface" />
</svelte:head>

<div class="page">
  <Frame theme={selectedTheme}>
    <main class="main-content">
      {/* Header */}
      <header class="header">
        <div class="header-left">
          <h1 class="logo">Echo-Node</h1>
          <StatusIndicator />
        </div>
        <div class="header-right">
          <button
            class="icon-button"
            onclick={toggleSettings}
            aria-label="Toggle settings"
            aria-expanded={settingsOpen}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>
        </div>
      </header>

      {/* Main content area */}
      <div class="content-area">
        {/* Avatar display */}
        <div class="avatar-section" bind:this={avatarRef}>
          <AvatarDisplay bind:this={avatarComponent} />

          {/* Waveform overlay during listening */}
          {#if pipeline.isListening}
            <div class="waveform-overlay">
              <Waveform bars={48} height={80} />
            </div>
          {/if}
        </div>

        {/* Transcript panel */}
        <aside class="transcript-section">
          <div class="transcript-header">
            <h2>Conversation</h2>
            <button
              class="clear-button"
              onclick={() => pipeline.clearTranscript()}
              aria-label="Clear transcript"
            >
              Clear
            </button>
          </div>
          <Transcript />
        </aside>
      </div>

      {/* Control bar */}
      <footer class="control-bar">
        <div class="controls">
          <button
            class="control-button primary"
            onclick={() => ws.send({ type: 'keyboard_trigger' })}
            disabled={!ws.isConnected}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 1a9 9 0 0 0-9 9v7c0 1.66 1.34 3 3 3h3v-8H5v-2c0-3.87 3.13-7 7-7s7 3.13 7 7v2h-4v8h3c1.66 0 3-1.34 3-3v-7a9 9 0 0 0-9-9z" />
            </svg>
            <span>Push to Talk</span>
          </button>

          {#if pipeline.isSpeaking}
            <button
              class="control-button danger"
              onclick={handleBargeIn}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 8L6 20M6 8l12 12" />
              </svg>
              <span>Interrupt</span>
            </button>
          {/if}

          <button
            class="control-button"
            onclick={handleStop}
            disabled={!pipeline.isActive}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            </svg>
            <span>Stop</span>
          </button>
        </div>

        {/* Connection status */}
        <div class="connection-status">
          <span class="status-dot" class:connected={ws.isConnected}></span>
          <span class="status-text">
            {ws.isConnected ? 'Connected' : ws.status === 'connecting' ? 'Connecting...' : 'Disconnected'}
          </span>
        </div>
      </footer>

      {/* Error banner */}
      {#if pipeline.error}
        <div class="error-banner">
          <span>{pipeline.error}</span>
          <button onclick={() => pipeline.clearError()} aria-label="Dismiss error">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      {/if}

      {/* Settings panel */}
      {#if settingsOpen}
        <div class="settings-panel">
          <div class="settings-header">
            <h2>Settings</h2>
            <button onclick={toggleSettings} aria-label="Close settings">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div class="settings-section">
            <h3>Theme</h3>
            <div class="theme-options">
              {#each ['minimal', 'cyberpunk', 'retro-terminal', 'glassmorphism', 'none'] as themeName}
                <button
                  class="theme-option"
                  class:active={selectedTheme === themeName}
                  onclick={() => selectedTheme = themeName as ThemeName}
                >
                  {themeName}
                </button>
              {/each}
            </div>
          </div>

          {#if pipeline.vramReport}
            <div class="settings-section">
              <h3>VRAM Usage</h3>
              <div class="vram-stats">
                <span>Used: {pipeline.vramReport.used_mb} MB</span>
                <span>Total: {pipeline.vramReport.total_mb} MB</span>
                <span>Available: {pipeline.vramReport.available_mb} MB</span>
              </div>
            </div>
          {/if}
        </div>
      {/if}
    </main>
  </Frame>
</div>

<style>
  :global(*) {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }

  :global(body) {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    color: rgba(255, 255, 255, 0.9);
    min-height: 100vh;
  }

  .page {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  .main-content {
    display: flex;
    flex-direction: column;
    height: 100vh;
    padding: 16px;
    gap: 16px;
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 12px;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .logo {
    font-size: 20px;
    font-weight: 700;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .icon-button {
    width: 40px;
    height: 40px;
    border-radius: 8px;
    border: none;
    background: rgba(255, 255, 255, 0.1);
    color: rgba(255, 255, 255, 0.8);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
  }

  .icon-button:hover {
    background: rgba(255, 255, 255, 0.2);
  }

  .icon-button svg {
    width: 20px;
    height: 20px;
  }

  .content-area {
    display: grid;
    grid-template-columns: 1fr 400px;
    flex: 1;
    gap: 16px;
    min-height: 0;
    overflow: hidden;
  }

  .avatar-section {
    position: relative;
    border-radius: 16px;
    overflow: hidden;
    background: rgba(0, 0, 0, 0.2);
  }

  .waveform-overlay {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 24px;
    background: linear-gradient(transparent, rgba(0, 0, 0, 0.7));
  }

  .transcript-section {
    display: flex;
    flex-direction: column;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 16px;
    overflow: hidden;
  }

  .transcript-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  }

  .transcript-header h2 {
    font-size: 14px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: rgba(255, 255, 255, 0.6);
  }

  .clear-button {
    font-size: 12px;
    padding: 4px 12px;
    border-radius: 6px;
    border: none;
    background: rgba(255, 255, 255, 0.1);
    color: rgba(255, 255, 255, 0.7);
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .clear-button:hover {
    background: rgba(255, 255, 255, 0.2);
  }

  .control-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 12px;
  }

  .controls {
    display: flex;
    gap: 8px;
  }

  .control-button {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    border-radius: 8px;
    border: none;
    background: rgba(255, 255, 255, 0.1);
    color: rgba(255, 255, 255, 0.8);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .control-button:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.2);
  }

  .control-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .control-button.primary {
    background: rgba(59, 130, 246, 0.3);
    color: #60a5fa;
  }

  .control-button.primary:hover:not(:disabled) {
    background: rgba(59, 130, 246, 0.5);
  }

  .control-button.danger {
    background: rgba(239, 68, 68, 0.3);
    color: #f87171;
  }

  .control-button.danger:hover:not(:disabled) {
    background: rgba(239, 68, 68, 0.5);
  }

  .control-button svg {
    width: 18px;
    height: 18px;
  }

  .connection-status {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: rgba(255, 255, 255, 0.6);
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.3);
  }

  .status-dot.connected {
    background: #10b981;
    box-shadow: 0 0 8px rgba(16, 185, 129, 0.5);
  }

  .error-banner {
    position: fixed;
    top: 16px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 20px;
    background: rgba(239, 68, 68, 0.2);
    border: 1px solid rgba(239, 68, 68, 0.5);
    border-radius: 8px;
    z-index: 100;
  }

  .error-banner button {
    background: none;
    border: none;
    color: rgba(255, 255, 255, 0.7);
    cursor: pointer;
    padding: 4px;
  }

  .error-banner button svg {
    width: 16px;
    height: 16px;
  }

  .settings-panel {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: 360px;
    background: rgba(15, 23, 42, 0.98);
    border-left: 1px solid rgba(255, 255, 255, 0.1);
    padding: 24px;
    z-index: 50;
    overflow-y: auto;
    animation: slideIn 0.3s ease;
  }

  @keyframes slideIn {
    from {
      transform: translateX(100%);
    }
    to {
      transform: translateX(0);
    }
  }

  .settings-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
  }

  .settings-header h2 {
    font-size: 18px;
    font-weight: 600;
  }

  .settings-header button {
    background: none;
    border: none;
    color: rgba(255, 255, 255, 0.6);
    cursor: pointer;
    padding: 8px;
  }

  .settings-header button svg {
    width: 20px;
    height: 20px;
  }

  .settings-section {
    margin-bottom: 24px;
  }

  .settings-section h3 {
    font-size: 14px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: rgba(255, 255, 255, 0.5);
    margin-bottom: 12px;
  }

  .theme-options {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .theme-option {
    padding: 12px 16px;
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    background: rgba(255, 255, 255, 0.05);
    color: rgba(255, 255, 255, 0.8);
    cursor: pointer;
    text-align: left;
    text-transform: capitalize;
    transition: all 0.2s ease;
  }

  .theme-option:hover {
    background: rgba(255, 255, 255, 0.1);
  }

  .theme-option.active {
    border-color: rgba(59, 130, 246, 0.5);
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
  }

  .vram-stats {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 8px;
  }

  .vram-stats span {
    font-size: 13px;
    color: rgba(255, 255, 255, 0.7);
  }

  /* Responsive */
  @media (max-width: 1024px) {
    .content-area {
      grid-template-columns: 1fr;
      grid-template-rows: 1fr 1fr;
    }
  }

  @media (max-width: 640px) {
    .main-content {
      padding: 8px;
    }

    .control-bar {
      flex-direction: column;
      gap: 12px;
    }

    .controls {
      width: 100%;
      justify-content: center;
    }

    .settings-panel {
      width: 100%;
    }
  }
</style>

<!-- responsive design tuned -->
