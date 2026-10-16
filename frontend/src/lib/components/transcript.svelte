<script lang="ts">
  import { pipelineStateStore, type TranscriptEntry } from '$lib/stores/pipeline-state.svelte';
  import { onMount } from 'svelte';

  interface Props {
    maxHeight?: string;
    showTimestamps?: boolean;
  }

  let { maxHeight = '300px', showTimestamps = true }: Props = $props();

  const transcript = $derived(pipelineStateStore.transcript);
  const partialTranscript = $derived(pipelineStateStore.partialTranscript);
  let transcriptContainer: HTMLDivElement | null = null;

  function formatTime(timestamp: number): string {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function scrollToBottom(): void {
    if (transcriptContainer) {
      transcriptContainer.scrollTop = transcriptContainer.scrollHeight;
    }
  }

  onMount(() => {
    scrollToBottom();
  });

  $effect(() => {
    // Auto-scroll when new messages arrive
    if (transcript.length > 0 || partialTranscript) {
      scrollToBottom();
    }
  });
</script>

<div class="transcript-container" bind:this={transcriptContainer} style="max-height: {maxHeight}">
  {#if transcript.length === 0 && !partialTranscript}
    <div class="empty-state">
      <p>No conversation yet</p>
      <span>Start speaking to begin</span>
    </div>
  {/if}

  <div class="transcript">
    {#each transcript as entry (entry.id)}
      <div class="message" class:user={entry.role === 'user'}>
        <div class="message-header">
          <span class="role">{entry.role === 'user' ? 'You' : 'Echo'}</span>
          {#if showTimestamps}
            <span class="timestamp">{formatTime(entry.timestamp)}</span>
          {/if}
        </div>
        <p class="message-text">{entry.text}</p>
      </div>
    {/each}

    {#if partialTranscript}
      <div class="message user partial">
        <div class="message-header">
          <span class="role">You</span>
          <span class="timestamp typing">listening...</span>
        </div>
        <p class="message-text">{partialTranscript}<span class="cursor">▌</span></p>
      </div>
    {/if}
  </div>
</div>

<style>
  .transcript-container {
    width: 100%;
    overflow-y: auto;
    padding: 16px;
    scrollbar-width: thin;
    scrollbar-color: rgba(255, 255, 255, 0.3) transparent;
  }

  .transcript-container::-webkit-scrollbar {
    width: 6px;
  }

  .transcript-container::-webkit-scrollbar-track {
    background: transparent;
  }

  .transcript-container::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.3);
    border-radius: 3px;
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 200px;
    color: rgba(255, 255, 255, 0.4);
    text-align: center;
  }

  .empty-state p {
    font-size: 16px;
    margin: 0 0 4px 0;
  }

  .empty-state span {
    font-size: 14px;
    opacity: 0.7;
  }

  .transcript {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .message {
    max-width: 85%;
    padding: 12px 16px;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.1);
    align-self: flex-start;
    animation: fadeIn 0.3s ease;
  }

  .message.user {
    background: rgba(59, 130, 246, 0.2);
    align-self: flex-end;
    border-bottom-right-radius: 4px;
  }

  .message.partial {
    opacity: 0.8;
  }

  .message-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }

  .role {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: rgba(255, 255, 255, 0.6);
  }

  .message.user .role {
    color: rgba(147, 197, 253, 0.8);
  }

  .timestamp {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.4);
  }

  .timestamp.typing {
    color: rgba(16, 185, 129, 0.6);
    animation: blink 1s ease-in-out infinite;
  }

  .message-text {
    margin: 0;
    font-size: 14px;
    line-height: 1.5;
    color: rgba(255, 255, 255, 0.9);
    white-space: pre-wrap;
    word-break: break-word;
  }

  .cursor {
    animation: blink 1s ease-in-out infinite;
    color: rgba(16, 185, 129, 0.6);
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  @keyframes blink {
    0%, 100% {
      opacity: 1;
    }
    50% {
      opacity: 0.3;
    }
  }
</style>
