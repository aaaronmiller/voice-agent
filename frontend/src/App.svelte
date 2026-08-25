<script lang="ts">
  import { onMount } from 'svelte';
  import { VoiceGateway } from './lib/websocket';
  import type { ProviderInfo, TurnMetrics, MetricsSnapshot } from './lib/types';

  let gateway: VoiceGateway;
  let state = $state('idle');
  let transcript = $state<Array<{text: string; source: string; time: string}>>([]);
  let providers = $state<ProviderInfo[]>([]);
  let currentProvider = $state('');
  let metrics = $state<TurnMetrics | null>(null);
  let snapshot = $state<MetricsSnapshot | null>(null);
  let showLatency = $state(false);
  let pushToTalkActive = $state(false);
  let connectionStatus = $state('connecting');

  onMount(() => {
    gateway = new VoiceGateway();

    gateway.onStateChange((s) => {
      state = s;
      connectionStatus = 'connected';
    });

    gateway.onTranscript((text, source, _final) => {
      const time = new Date().toLocaleTimeString();
      transcript = [...transcript, { text, source, time }];
      if (transcript.length > 100) transcript = transcript.slice(-100);
    });

    gateway.onMetrics((m) => { metrics = m; });
    gateway.onSnapshot((s) => { snapshot = s; });
    gateway.onProviders((p) => {
      providers = p;
      if (!currentProvider && p.length > 0) currentProvider = p[0].name;
    });
    gateway.onError((msg) => {
      transcript = [...transcript, { text: `Error: ${msg}`, source: 'system', time: new Date().toLocaleTimeString() }];
    });

    gateway.connect('ws://127.0.0.1:3000/ws');
  });

  async function togglePushToTalk() {
    pushToTalkActive = !pushToTalkActive;
    gateway.send({ type: 'push_to_talk', active: pushToTalkActive });
  }

  async function interrupt() {
    gateway.send({ type: 'interrupt' });
    pushToTalkActive = false;
  }

  async function changeProvider(e: Event) {
    const select = e.target as HTMLSelectElement;
    currentProvider = select.value;
    gateway.send({ type: 'set_provider', provider: currentProvider });
  }

  const stateColors: Record<string, string> = {
    idle: '#888',
    listening: '#4caf50',
    streaming: '#2196f3',
    thinking: '#ff9800',
    speaking: '#00bcd4',
    interrupted: '#f44336',
    error: '#f44336',
  };
</script>

<div class="app">
  <header class="header">
    <h1>Echo-Node</h1>
    <div class="status-bar">
      <span class="state-indicator" style="background: {stateColors[state] || '#888'}" title={state}></span>
      <span class="state-text">{state}</span>
      <span class="connection-status" class:connected={connectionStatus === 'connected'}>
        {connectionStatus === 'connected' ? '● Connected' : '○ Connecting...'}
      </span>
    </div>
    <div class="controls">
      <select value={currentProvider} onchange={changeProvider} class="provider-select">
        <option value="">Select provider...</option>
        {#each providers as p}
          <option value={p.name}>{p.name} ({p.type}) {p.pricing?.isFree ? '🆓' : p.pricing?.label ? '💰' + p.pricing.label : ''}</option>
        {/each}
      </select>
      <button class="latency-toggle" onclick={() => showLatency = !showLatency}>
        📊 {showLatency ? 'Hide' : 'Show'} Latency
      </button>
    </div>
  </header>

  <main class="main">
    <section class="transcript-panel">
      <h2>Conversation</h2>
      <div class="transcript">
        {#each transcript as entry}
          <div class="entry {entry.source}">
            <span class="time">{entry.time}</span>
            <span class="badge">{entry.source === 'user' ? 'You' : entry.source === 'system' ? 'System' : 'Assistant'}</span>
            <span class="text">{entry.text}</span>
          </div>
        {/each}
        {#if transcript.length === 0}
          <p class="placeholder">Start speaking or press Push to Talk...</p>
        {/if}
      </div>
    </section>

    {#if showLatency}
      <aside class="latency-panel">
        <h2>Latency Metrics</h2>
        {#if metrics}
          <div class="metric-grid">
            <div class="metric">
              <span class="metric-value" class:good={metrics.earsToMouth < 500} class:ok={metrics.earsToMouth >= 500 && metrics.earsToMouth < 1000} class:bad={metrics.earsToMouth >= 1000}>
                {metrics.earsToMouth?.toFixed(0)}ms
              </span>
              <span class="metric-label">Ears→Mouth</span>
            </div>
            <div class="metric">
              <span class="metric-value">{metrics.totalLatency?.toFixed(0)}ms</span>
              <span class="metric-label">Total</span>
            </div>
            <div class="metric">
              <span class="metric-value">{metrics.llmFirstToken?.toFixed(0)}ms</span>
              <span class="metric-label">First Token</span>
            </div>
            <div class="metric">
              <span class="metric-value">{snapshot?.totalTurns || 0}</span>
              <span class="metric-label">Total Turns</span>
            </div>
          </div>

          {#if metrics && metrics.costUsd !== undefined}
            <h3>Cost</h3>
            <div class="metric-grid">
              <div class="metric">
                <span class="metric-value">${metrics.costUsd < 0.001 ? '< $0.001' : '$' + metrics.costUsd.toFixed(4)}</span>
                <span class="metric-label">This turn</span>
              </div>
              <div class="metric">
                <span class="metric-value">${snapshot?.totalCostUsd ? (snapshot.totalCostUsd < 0.001 ? '< $0.001' : '$' + snapshot.totalCostUsd.toFixed(4)) : '$0.0000'}</span>
                <span class="metric-label">Session total</span>
              </div>
              <div class="metric">
                <span class="metric-value">{metrics.pricingLabel || '—'}</span>
                <span class="metric-label">Pricing</span>
              </div>
            </div>
          {/if}

          {#if snapshot?.perProvider}
            <h3>Per Provider</h3>
            <div class="provider-stats">
              {#each snapshot.perProvider as ps}
                <div class="provider-stat">
                  <span class="ps-name">{ps.provider}</span>
                  <span class="ps-value">{ps.avgEarsToMouth?.toFixed(0)}ms avg</span>
                  <span class="ps-count">({ps.turnCount} turns</span>
                  {#if ps.totalCostUsd !== undefined}
                    <span class="ps-cost">${ps.totalCostUsd < 0.001 ? '< $0.001' : '$' + ps.totalCostUsd.toFixed(4)})</span>
                  {:else}
                    <span class="ps-cost">)</span>
                  {/if}
                </div>
              {/each}
            </div>
          {/if}

          {#if snapshot?.percentiles}
            <h3>Percentiles</h3>
            <div class="percentiles">
              <span>p50: {snapshot.percentiles.p50.toFixed(0)}ms</span>
              <span>p95: {snapshot.percentiles.p95.toFixed(0)}ms</span>
              <span>p99: {snapshot.percentiles.p99.toFixed(0)}ms</span>
            </div>
          {/if}
        {:else}
          <p class="placeholder">Waiting for metrics...</p>
        {/if}
      </aside>
    {/if}
  </main>

  <footer class="footer">
    <button class="ptt-btn" class:active={pushToTalkActive} onclick={togglePushToTalk}>
      {pushToTalkActive ? '🔴 Release' : '🎤 Push to Talk'}
    </button>
    <button class="interrupt-btn" onclick={interrupt}>
      ⏹ Interrupt
    </button>
    <span class="shortcuts">
      Space: PTT &middot; Esc: Interrupt
    </span>
  </footer>
</div>

<style>
  :global(*) { box-sizing: border-box; margin: 0; padding: 0; }
  :global(body) {
    font-family: system-ui, -apple-system, sans-serif;
    background: #1a1b2e;
    color: #e0e0f0;
    height: 100vh;
    overflow: hidden;
  }

  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }

  .header {
    background: #222340;
    border-bottom: 1px solid #3a3b58;
    padding: 8px 16px;
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }

  .header h1 { font-size: 1.1rem; color: #4fc3b7; }

  .status-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
  }

  .state-indicator {
    width: 10px; height: 10px;
    border-radius: 50%;
    display: inline-block;
  }

  .state-text { text-transform: capitalize; font-size: 0.85rem; }

  .connection-status {
    font-size: 0.75rem;
    color: #666;
  }
  .connection-status.connected { color: #4caf50; }

  .controls {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .provider-select {
    padding: 4px 8px;
    border: 1px solid #3a3b58;
    border-radius: 4px;
    background: #1a1b2e;
    color: #e0e0f0;
    font-size: 0.85rem;
  }

  .latency-toggle {
    padding: 4px 12px;
    border: 1px solid #3a3b58;
    border-radius: 4px;
    background: #2a2b48;
    color: #e0e0f0;
    cursor: pointer;
    font-size: 0.85rem;
  }
  .latency-toggle:hover { background: #33345a; }

  .main {
    flex: 1;
    display: flex;
    overflow: hidden;
  }

  .transcript-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 16px;
    overflow: hidden;
  }

  .transcript-panel h2, .latency-panel h2 {
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #707090;
    margin-bottom: 8px;
  }

  .transcript {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .entry {
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 0.9rem;
    line-height: 1.4;
  }

  .entry.user { background: #1a3a2a; }
  .entry.assistant { background: #2a2a48; }
  .entry.system { background: #3a1a1a; }

  .time { font-size: 0.7rem; color: #707090; margin-right: 8px; }
  .badge {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    padding: 1px 6px;
    border-radius: 3px;
    margin-right: 8px;
  }
  .entry.user .badge { background: #2e7d32; color: #fff; }
  .entry.assistant .badge { background: #1565c0; color: #fff; }
  .entry.system .badge { background: #c62828; color: #fff; }

  .placeholder {
    color: #707090;
    font-style: italic;
    text-align: center;
    margin-top: 40px;
  }

  .latency-panel {
    width: 320px;
    background: #222340;
    border-left: 1px solid #3a3b58;
    padding: 16px;
    overflow-y: auto;
    flex-shrink: 0;
  }

  .metric-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 12px;
  }

  .metric {
    background: #1a1b2e;
    border: 1px solid #3a3b58;
    border-radius: 6px;
    padding: 8px;
    text-align: center;
  }

  .metric-value {
    display: block;
    font-size: 1.4rem;
    font-weight: 700;
    color: #4fc3b7;
  }
  .metric-value.good { color: #4caf50; }
  .metric-value.ok { color: #ff9800; }
  .metric-value.bad { color: #f44336; }

  .metric-label {
    display: block;
    font-size: 0.7rem;
    color: #707090;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .latency-panel h3 {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #707090;
    margin: 12px 0 4px;
  }

  .provider-stat {
    display: flex;
    gap: 8px;
    font-size: 0.85rem;
    padding: 2px 0;
  }
  .ps-name { color: #4fc3b7; }
  .ps-value { color: #e0e0f0; }
  .ps-count { color: #707090; }
  .ps-cost { color: #ff9800; font-size: 0.75rem; }

  .percentiles {
    display: flex;
    gap: 12px;
    font-size: 0.85rem;
    color: #a0a0c0;
  }

  .footer {
    background: #222340;
    border-top: 1px solid #3a3b58;
    padding: 8px 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .ptt-btn, .interrupt-btn {
    padding: 8px 20px;
    border: 1px solid #3a3b58;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 600;
  }

  .ptt-btn {
    background: #1a3a2a;
    color: #4caf50;
  }
  .ptt-btn.active {
    background: #c62828;
    color: #fff;
  }

  .interrupt-btn {
    background: #3a1a1a;
    color: #ef5350;
  }

  .shortcuts {
    margin-left: auto;
    font-size: 0.75rem;
    color: #707090;
  }
</style>
