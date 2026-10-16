<script lang="ts">
  import { onMount } from 'svelte';
  import type { ThemeName } from './frame.svelte';
  
  interface Personality {
    name: string;
    description: string;
  }

  interface Props {
    isOpen?: boolean;
    currentTheme?: ThemeName;
    currentPersonality?: string;
    onClose?: () => void;
    onThemeChange?: (theme: ThemeName) => void;
    onPersonalityChange?: (personality: string) => void;
  }

  let {
    isOpen = false,
    currentTheme = 'minimal',
    currentPersonality = 'hacker',
    onClose = () => {},
    onThemeChange = () => {},
    onPersonalityChange = () => {},
  }: Props = $props();

  let personalities: Personality[] = $state([]);
  let activeSection: 'personality' | 'theme' | 'provider' | 'avatar' = $state('personality');
  let loading = $state(false);
  let error = $state<string | null>(null);

  // Provider settings
  let sttProvider = $state('sherpa-onnx');
  let ttsProvider = $state('kokoro');
  let llmProvider = $state('ollama');
  let llmModel = $state('llama3.2:7b-q4_K_M');

  // Avatar settings
  let selectedAvatar = $state('random');

  const themes: ThemeName[] = ['minimal', 'cyberpunk', 'retro-terminal', 'glassmorphism'];

  onMount(async () => {
    await loadPersonalities();
  });

  async function loadPersonalities() {
    try {
      loading = true;
      const res = await fetch('/api/personalities');
      if (!res.ok) throw new Error('Failed to load personalities');
      const data = await res.json();
      personalities = [
        ...data.built_in.map((p: Personality) => ({ ...p, name: p.name })),
        ...data.custom.map((p: Personality) => ({ ...p, name: p.name })),
      ];
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load personalities';
    } finally {
      loading = false;
    }
  }

  async function handlePersonalityChange(name: string) {
    try {
      loading = true;
      error = null;
      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ personality: { active: name } }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error?.message || 'Failed to update personality');
      }
      onPersonalityChange(name);
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to change personality';
    } finally {
      loading = false;
    }
  }

  async function handleProviderChange(provider: string, value: string) {
    try {
      error = null;
      const update: Record<string, Record<string, string>> = {};
      
      if (provider === 'stt') {
        update.stt = { provider: value };
      } else if (provider === 'tts') {
        update.tts = { provider: value };
      } else if (provider === 'llm') {
        update.llm = { provider: value, model: llmModel };
      }

      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(update),
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error?.message || 'Failed to update provider');
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to change provider';
    }
  }

  function handleThemeChange(theme: ThemeName) {
    onThemeChange(theme);
  }

  function getPersonalityIcon(name: string): string {
    const icons: Record<string, string> = {
      hacker: '💻',
      seductive: '✨',
      butler: '🎩',
      'drill-sergeant': '📢',
      'stoner-philosopher': '🌿',
      custom: '⚙️',
    };
    return icons[name] || '👤';
  }

  function getPersonalityDescription(name: string): string {
    const descriptions: Record<string, string> = {
      hacker: 'Tech-savvy with concise, technical language',
      seductive: 'Charming, flirtatious, and engaging',
      butler: 'Formal British etiquette and attentiveness',
      'drill-sergeant': 'Aggressive, motivational, and commanding',
      'stoner-philosopher': 'Laid-back and contemplative',
      custom: 'Your custom-defined personality',
    };
    return descriptions[name] || 'Custom personality';
  }
</script>

{#if isOpen}
  <div class="settings-overlay" onclick={onClose} role="presentation">
    <div class="settings-panel" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
      <div class="settings-header">
        <h2>Settings</h2>
        <button class="close-btn" onclick={onClose} aria-label="Close settings">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      {#if error}
        <div class="error-banner">
          <span>{error}</span>
          <button onclick={() => error = null} aria-label="Dismiss error">×</button>
        </div>
      {/if}

      <div class="settings-tabs">
        <button
          class="tab"
          class:active={activeSection === 'personality'}
          onclick={() => activeSection = 'personality'}
        >
          👤 Personality
        </button>
        <button
          class="tab"
          class:active={activeSection === 'theme'}
          onclick={() => activeSection = 'theme'}
        >
          🎨 Theme
        </button>
        <button
          class="tab"
          class:active={activeSection === 'provider'}
          onclick={() => activeSection = 'provider'}
        >
          ⚡ Providers
        </button>
        <button
          class="tab"
          class:active={activeSection === 'avatar'}
          onclick={() => activeSection = 'avatar'}
        >
          🦄 Avatar
        </button>
      </div>

      <div class="settings-content">
        {#if activeSection === 'personality'}
          <div class="section">
            <h3>Active Personality</h3>
            <p class="section-desc">Choose how Echo-Node speaks and interacts</p>
            
            <div class="personality-grid">
              {#each personalities as personality}
                <button
                  class="personality-card"
                  class:active={currentPersonality === personality.name}
                  onclick={() => handlePersonalityChange(personality.name)}
                  disabled={loading}
                >
                  <span class="personality-icon">{getPersonalityIcon(personality.name)}</span>
                  <span class="personality-name">{personality.name}</span>
                  <span class="personality-desc">{getPersonalityDescription(personality.name)}</span>
                </button>
              {/each}
            </div>

            {#if loading}
              <div class="loading-indicator">Updating personality...</div>
            {/if}
          </div>

        {:else if activeSection === 'theme'}
          <div class="section">
            <h3>UI Theme</h3>
            <p class="section-desc">Choose the visual style for the interface</p>
            
            <div class="theme-grid">
              {#each themes as theme}
                <button
                  class="theme-card"
                  class:active={currentTheme === theme}
                  onclick={() => handleThemeChange(theme)}
                >
                  <span class="theme-name">{theme}</span>
                </button>
              {/each}
            </div>
          </div>

        {:else if activeSection === 'provider'}
          <div class="section">
            <h3>AI Providers</h3>
            <p class="section-desc">Configure speech recognition, synthesis, and LLM</p>
            
            <div class="provider-list">
              <div class="provider-item">
                <label for="stt-provider">Speech-to-Text (STT)</label>
                <select
                  id="stt-provider"
                  bind:value={sttProvider}
                  onchange={(e) => handleProviderChange('stt', (e.target as HTMLSelectElement).value)}
                >
                  <option value="sherpa-onnx">Sherpa-ONNX (Fast, local)</option>
                  <option value="faster-whisper">Faster-Whisper (Accurate, GPU)</option>
                  <option value="vibevoice-asr">VibeVoice ASR (Cloud)</option>
                </select>
              </div>

              <div class="provider-item">
                <label for="tts-provider">Text-to-Speech (TTS)</label>
                <select
                  id="tts-provider"
                  bind:value={ttsProvider}
                  onchange={(e) => handleProviderChange('tts', (e.target as HTMLSelectElement).value)}
                >
                  <option value="kokoro">Kokoro (Natural, local)</option>
                  <option value="piper">Piper (Lightweight, local)</option>
                  <option value="chatterbox">Chatterbox (Expressive)</option>
                  <option value="orpheus">Orpheus (High-fidelity)</option>
                </select>
              </div>

              <div class="provider-item">
                <label for="llm-provider">Language Model (LLM)</label>
                <select
                  id="llm-provider"
                  bind:value={llmProvider}
                  onchange={(e) => handleProviderChange('llm', (e.target as HTMLSelectElement).value)}
                >
                  <option value="ollama">Ollama (Local models)</option>
                  <option value="openai-compat">OpenAI-Compatible (Cloud)</option>
                </select>
              </div>

              <div class="provider-item">
                <label for="llm-model">Model</label>
                <input
                  id="llm-model"
                  type="text"
                  bind:value={llmModel}
                  placeholder="e.g., llama3.2:7b-q4_K_M"
                />
              </div>
            </div>
          </div>

        {:else if activeSection === 'avatar'}
          <div class="section">
            <h3>Avatar Selection</h3>
            <p class="section-desc">Choose a 3D avatar model or use random rotation</p>
            
            <div class="avatar-options">
              <label class="avatar-option">
                <input type="radio" bind:group={selectedAvatar} value="random" />
                <span>Random rotation from pool</span>
              </label>
              <label class="avatar-option">
                <input type="radio" bind:group={selectedAvatar} value="fixed" />
                <span>Select specific avatar</span>
              </label>
            </div>
            
            <p class="hint">Avatar VRM files should be placed in /models/avatars/</p>
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .settings-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(4px);
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .settings-panel {
    background: rgba(15, 23, 42, 0.95);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 16px;
    width: 90%;
    max-width: 600px;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
  }

  .settings-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 24px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  }

  .settings-header h2 {
    font-size: 18px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.9);
  }

  .close-btn {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    border: none;
    background: rgba(255, 255, 255, 0.1);
    color: rgba(255, 255, 255, 0.7);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
  }

  .close-btn:hover {
    background: rgba(255, 255, 255, 0.2);
    color: white;
  }

  .close-btn svg {
    width: 18px;
    height: 18px;
  }

  .error-banner {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 24px;
    background: rgba(239, 68, 68, 0.2);
    border-bottom: 1px solid rgba(239, 68, 68, 0.3);
    color: #f87171;
    font-size: 14px;
  }

  .error-banner button {
    background: none;
    border: none;
    color: inherit;
    cursor: pointer;
    font-size: 18px;
  }

  .settings-tabs {
    display: flex;
    gap: 4px;
    padding: 12px 24px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    overflow-x: auto;
  }

  .tab {
    padding: 8px 16px;
    border-radius: 8px;
    border: none;
    background: transparent;
    color: rgba(255, 255, 255, 0.6);
    font-size: 14px;
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;
  }

  .tab:hover {
    background: rgba(255, 255, 255, 0.05);
    color: rgba(255, 255, 255, 0.8);
  }

  .tab.active {
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
  }

  .settings-content {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
  }

  .section h3 {
    font-size: 16px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.9);
    margin-bottom: 4px;
  }

  .section-desc {
    font-size: 13px;
    color: rgba(255, 255, 255, 0.5);
    margin-bottom: 20px;
  }

  .personality-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 12px;
  }

  .personality-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    padding: 16px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    background: rgba(255, 255, 255, 0.03);
    cursor: pointer;
    transition: all 0.2s ease;
    text-align: center;
  }

  .personality-card:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.2);
  }

  .personality-card.active {
    background: rgba(59, 130, 246, 0.15);
    border-color: #3b82f6;
  }

  .personality-card:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .personality-icon {
    font-size: 28px;
  }

  .personality-name {
    font-size: 14px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.9);
    text-transform: capitalize;
  }

  .personality-desc {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.5);
    line-height: 1.4;
  }

  .loading-indicator {
    margin-top: 12px;
    text-align: center;
    font-size: 13px;
    color: rgba(255, 255, 255, 0.5);
  }

  .theme-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
  }

  .theme-card {
    padding: 16px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    background: rgba(255, 255, 255, 0.03);
    cursor: pointer;
    transition: all 0.2s ease;
    text-align: center;
    font-size: 14px;
    color: rgba(255, 255, 255, 0.8);
    text-transform: capitalize;
  }

  .theme-card:hover {
    background: rgba(255, 255, 255, 0.08);
  }

  .theme-card.active {
    background: rgba(59, 130, 246, 0.15);
    border-color: #3b82f6;
    color: #60a5fa;
  }

  .provider-list {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .provider-item {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .provider-item label {
    font-size: 13px;
    color: rgba(255, 255, 255, 0.7);
  }

  .provider-item select,
  .provider-item input {
    padding: 10px 12px;
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.15);
    background: rgba(0, 0, 0, 0.3);
    color: rgba(255, 255, 255, 0.9);
    font-size: 14px;
  }

  .provider-item select:focus,
  .provider-item input:focus {
    outline: none;
    border-color: #3b82f6;
  }

  .avatar-options {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
  }

  .avatar-option {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    color: rgba(255, 255, 255, 0.8);
    cursor: pointer;
  }

  .avatar-option input {
    accent-color: #3b82f6;
  }

  .hint {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.4);
  }
</style>

<!-- avatar selection added -->
