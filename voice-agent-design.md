# Echo-Node — Software Design Document

> **Version:** 1.1.0-draft
> **Date:** 2026-03-29
> **Companion to:** voice-agent-requirements.md
> **Status:** Draft — synthesized from 5 source documents + user answers

---

## 1. Architecture Overview

Echo-Node is a **3-layer split-stack** system. Each layer runs as a separate process, connected via WebSocket.

```
┌──────────────────────────────────────────────────────────────┐
│                    Layer 3: Frontend                          │
│                    (Svelte 5 SPA)                             │
│                                                              │
│   ┌────────────┐ ┌────────────┐ ┌──────────────────────┐    │
│   │ TalkingHead│ │ Waveform   │ │ Transcript Panel     │    │
│   │ Avatar     │ │ Visualizer │ │ + Settings           │    │
│   └────────────┘ └────────────┘ └──────────────────────┘    │
└──────────────────────┬───────────────────────────────────────┘
                       │ ws://localhost:3000/ws (JSON events)
┌──────────────────────▼───────────────────────────────────────┐
│                    Layer 2: Gateway                            │
│                    (Bun + Hono)                                │
│                                                               │
│   ┌──────────┐ ┌──────────────┐ ┌─────────────────────┐     │
│   │ Session  │ │ REST API     │ │ Integration Adapters│     │
│   │ Manager  │ │ /api/config  │ │ Hermes · OpenClaw   │     │
│   └──────────┘ └──────────────┘ └─────────────────────┘     │
└──────────────────────┬───────────────────────────────────────┘
                       │ ws://localhost:9001 (binary audio + JSON)
┌──────────────────────▼───────────────────────────────────────┐
│                    Layer 1: Audio Worker                       │
│                    (Python 3.11+)                              │
│                                                               │
│   ┌───────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐   │
│   │ State     │ │ Provider │ │ Pipeline │ │ Streaming  │   │
│   │ Machine   │ │ Manager  │ │ (Pipeline│ │ TTS Engine │   │
│   │ (5-state) │ │ (ABCs)   │ │  Chain)  │ │            │   │
│   └───────────┘ └──────────┘ └──────────┘ └────────────┘   │
│                                                               │
│   ┌───────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐   │
│   │ Mic       │ │ Wake     │ │ VAD      │ │ Echo       │   │
│   │ Capture   │ │ Word     │ │ (Silero) │ │ Cancel     │   │
│   └───────────┘ └──────────┘ └──────────┘ └────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Python owns audio** — All mic capture, ML inference, and audio playback happens in Python. The gateway never touches raw audio.
2. **Python owns state** — The 5-state machine lives exclusively in the Python worker. The gateway relays state events; it doesn't make decisions.
3. **Gateway is a relay** — It connects frontends, integration adapters, and the Python worker. It adds session management and REST API, nothing more.
4. **Frontend is a visualizer** — It renders state events. Avatar lip-sync is driven by audio data from the gateway. It never calls ML models.
5. **Config is the control plane** — Everything is driven by `config.yaml`. No pipeline behavior is hard-coded.

---

## 2. Project Structure

```
echo-node/
├── config.yaml                      # User configuration (all components)
├── config.example.yaml              # Documented default config
├── README.md                        # Setup + usage documentation
├── setup.sh                         # Install Python deps + download models
├── package.json                     # Bun deps (gateway + frontend)
├── bunfig.toml
│
├── gateway/                         # Layer 2: Bun + Hono
│   ├── src/
│   │   ├── index.ts                # Hono server entry point
│   │   ├── websocket.ts            # WebSocket hub (frontend ↔ worker relay)
│   │   ├── routes/
│   │   │   ├── health.ts           # GET /api/health
│   │   │   ├── config.ts           # GET/PUT /api/config
│   │   │   └── status.ts           # GET /api/status (current state)
│   │   ├── integrations/
│   │   │   ├── hermes-adapter.ts   # Hermes channel registration (Phase 3)
│   │   │   ├── openclaw-adapter.ts # OpenClaw skill file management (Phase 3)
│   │   │   └── mcp-bridge.ts       # MCP tool invocation relay (Phase 3)
│   │   ├── sessions/
│   │   │   └── session-manager.ts  # Multi-client session tracking
│   │   └── utils/
│   │       ├── config-loader.ts    # Parse + validate config.yaml
│   │       ├── logger.ts           # pino structured logging
│   │       └── types.ts            # Shared TypeScript types
│   └── tsconfig.json
│
├── worker/                          # Layer 1: Python audio worker
│   ├── main.py                     # Entry point, WebSocket server
│   ├── state_machine.py            # 5-state machine
│   ├── pipeline.py                 # Orchestrates wake → VAD → STT → LLM → TTS
│   ├── config.py                   # Load + validate config.yaml
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                 # Abstract base classes (ABCs)
│   │   ├── stt/
│   │   │   ├── __init__.py
│   │   │   ├── sherpa_stt.py       # sherpa-onnx streaming STT
│   │   │   └── faster_whisper_stt.py  # faster-whisper fallback
│   │   ├── tts/
│   │   │   ├── __init__.py
│   │   │   ├── kokoro_tts.py       # Kokoro-82M (default)
│   │   │   ├── chatterbox_tts.py   # Chatterbox-Turbo
│   │   │   ├── orpheus_tts.py      # Orpheus (150M/400M)
│   │   │   └── piper_tts.py        # Piper fallback
│   │   ├── vad/
│   │   │   ├── __init__.py
│   │   │   └── silero_vad.py       # Silero-VAD
│   │   ├── wake_word/
│   │   │   ├── __init__.py
│   │   │   └── openwakeword.py     # OpenWakeWord
│   │   └── llm/
│   │       ├── __init__.py
│   │       ├── ollama_llm.py       # Ollama (default)
│   │       └── openai_compat_llm.py  # OpenAI-compatible API
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── capture.py              # Mic capture (PyAudio/sounddevice)
│   │   ├── playback.py             # Speaker playback
│   │   ├── echo_cancel.py          # SpeexDSP AEC wrapper
│   │   └── vram_calculator.py      # Check available VRAM before loading
│   ├── streaming/
│   │   ├── __init__.py
│   │   └── sentence_chunker.py     # Split LLM stream at sentence boundaries
│   │   ├── conversation/
│   │   │   ├── __init__.py
│   │   │   └── memory.py             # 15-turn sliding window
│   ├── personalities/                 # Personality preset YAML files
│   │   ├── hacker.yaml
│   │   ├── seductive.yaml
│   │   ├── butler.yaml
│   │   ├── drill-sergeant.yaml
│   │   └── stoner-philosopher.yaml
│   ├── sounds/                        # Activation sound files
│   │   ├── beep.wav
│   │   ├── chime.wav
│   │   └── silent.wav                # 0-length placeholder
│   ├── requirements.txt
│   └── pyproject.toml
│
├── frontend/                        # Layer 3: Svelte 5
│   ├── src/
│   │   ├── app.html
│   │   ├── app.css                 # Global styles + CSS custom properties
│   │   ├── routes/
│   │   │   └── +page.svelte        # Main page
│   │   ├── lib/
│   │   │   ├── components/
│   │   │   │   ├── avatar-display.svelte   # TalkingHead wrapper
│   │   │   │   ├── waveform.svelte         # Audio waveform visualizer
│   │   │   │   ├── transcript.svelte       # Conversation history
│   │   │   │   ├── status-indicator.svelte # State machine indicator
│   │   │   │   ├── settings-panel.svelte   # Config UI
│   │   │   │   └── frame.svelte            # Theme frame wrapper
│   │   │   ├── stores/
│   │   │   │   ├── websocket.svelte.ts     # WebSocket connection state
│   │   │   │   └── pipeline-state.svelte.ts # Pipeline state ($state)
│   │   │   ├── themes/
│   │   │   │   ├── minimal.css
│   │   │   │   ├── cyberpunk.css
│   │   │   │   ├── retro-terminal.css
│   │   │   │   └── glassmorphism.css
│   │   │   └── utils/
│   │   │       └── talking-head-loader.ts  # Dynamic TalkingHead import
│   │   └── static/
│   │       └── models/                     # VRM avatar files
│   ├── svelte.config.js
│   ├── vite.config.ts
│   └── package.json
│
├── models/                          # Downloaded ML models (gitignored)
│   ├── stt/
│   ├── tts/
│   ├── vad/
│   └── wake_word/
│
└── docs/
    ├── setup-fedora.md
    ├── setup-wsl2.md
    ├── setup-macos.md
    └── provider-guide.md           # How to add a new STT/TTS provider
```

---

## 3. Component Design

### 3.1 State Machine (Python Worker)

The audio worker owns a 5-state machine. All transitions originate from audio events.

```
                ┌──────────────────┐
                │     DORMANT      │
                │  (wake word on)  │
                └────────┬─────────┘
                         │ wake word detected OR keyboard trigger
                ┌────────▼─────────┐
                │    TRIGGERED     │
                │  (beep/visual)   │
                └────────┬─────────┘
                         │ immediate (100ms)
                ┌────────▼─────────┐
       ┌───────▶│    LISTENING     │◀───── barge-in
       │        │  (VAD active)    │
       │        └────────┬─────────┘
       │                 │ silence ≥ endpointing threshold
       │        ┌────────▼─────────┐
       │        │   PROCESSING     │
       │        │  (STT→LLM→TTS)  │
       │        └────────┬─────────┘
       │                 │ TTS audio ready
       │        ┌────────▼─────────┐
       └────────│    SPEAKING      │
  (barge-in)    │  (TTS playback)  │
                └────────┬─────────┘
                         │ playback complete
                         ▼
                   → DORMANT
```

```python
# worker/state_machine.py
from enum import Enum
from typing import Callable
import asyncio

class State(Enum):
    DORMANT = "dormant"
    TRIGGERED = "triggered"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"

class StateMachine:
    def __init__(self, on_transition: Callable[[State, State], None]):
        self._state = State.DORMANT
        self._on_transition = on_transition
        self._lock = asyncio.Lock()

    @property
    def state(self) -> State:
        return self._state

    async def transition(self, target: State) -> bool:
        """Attempt state transition. Returns True if valid."""
        async with self._lock:
            if not self._is_valid(self._state, target):
                return False
            old = self._state
            self._state = target
            self._on_transition(old, target)
            return True

    def _is_valid(self, current: State, target: State) -> bool:
        valid_transitions = {
            State.DORMANT: {State.TRIGGERED},
            State.TRIGGERED: {State.LISTENING},
            State.LISTENING: {State.PROCESSING, State.DORMANT},  # timeout → dormant
            State.PROCESSING: {State.SPEAKING, State.DORMANT},   # error → dormant
            State.SPEAKING: {State.DORMANT, State.LISTENING},     # barge-in → listening
        }
        return target in valid_transitions.get(current, set())
```

### 3.2 Provider Interfaces (Python ABCs)

All pipeline components implement abstract base classes. Adding a new provider means subclassing and registering in `config.yaml`.

```python
# worker/providers/base.py
from abc import ABC, abstractmethod
from typing import AsyncIterator
import numpy as np

class STTProvider(ABC):
    """Speech-to-Text provider interface."""

    @abstractmethod
    async def initialize(self, model_path: str, device: str = "cuda") -> None:
        """Load model into memory."""

    @abstractmethod
    async def transcribe_stream(self, audio_chunks: AsyncIterator[np.ndarray]) -> AsyncIterator[str]:
        """Stream audio chunks, yield partial transcripts."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Release model resources."""

    @property
    @abstractmethod
    def vram_requirement_mb(self) -> int:
        """VRAM needed by this provider's current model."""


class TTSProvider(ABC):
    """Text-to-Speech provider interface."""

    @abstractmethod
    async def initialize(self, model_path: str, voice: str, device: str = "cuda") -> None:
        """Load model into memory."""

    @abstractmethod
    async def synthesize(self, text: str) -> np.ndarray:
        """Synthesize full text to audio array (16kHz mono float32)."""

    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncIterator[np.ndarray]:
        """Stream audio chunks as they're generated."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Release model resources."""

    @property
    @abstractmethod
    def vram_requirement_mb(self) -> int:
        """VRAM needed by this provider's current model."""


class VADProvider(ABC):
    """Voice Activity Detection provider interface."""

    @abstractmethod
    async def initialize(self, model_path: str) -> None:
        """Load model."""

    @abstractmethod
    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """Returns True if audio chunk contains speech."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Release resources."""


class WakeWordProvider(ABC):
    """Wake Word Detection provider interface."""

    @abstractmethod
    async def initialize(self, model_path: str, threshold: float = 0.5) -> None:
        """Load wake word model."""

    @abstractmethod
    def detect(self, audio_chunk: np.ndarray) -> bool:
        """Returns True if wake word detected in chunk."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Release resources."""


class LLMProvider(ABC):
    """LLM provider interface."""

    @abstractmethod
    async def initialize(self, model: str, base_url: str, api_key: str = "") -> None:
        """Configure connection. api_key is optional (blank for Ollama, required for OpenRouter/OpenAI)."""

    @abstractmethod
    async def chat_stream(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[str]:
        """Stream response tokens from LLM."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup."""
```

### 3.3 Provider Registry

```python
# worker/providers/__init__.py
from worker.providers.base import STTProvider, TTSProvider, VADProvider, WakeWordProvider, LLMProvider
from worker.providers.stt.sherpa_stt import SherpaSTT
from worker.providers.stt.faster_whisper_stt import FasterWhisperSTT
from worker.providers.tts.kokoro_tts import KokoroTTS
from worker.providers.tts.chatterbox_tts import ChatterboxTTS
from worker.providers.tts.orpheus_tts import OrpheusTTS
from worker.providers.tts.piper_tts import PiperTTS
from worker.providers.vad.silero_vad import SileroVAD
from worker.providers.wake_word.openwakeword import OpenWakeWordProvider
from worker.providers.llm.ollama_llm import OllamaLLM
from worker.providers.llm.openai_compat_llm import OpenAICompatLLM

PROVIDER_REGISTRY: dict[str, dict[str, type]] = {
    "stt": {
        "sherpa-onnx": SherpaSTT,
        "faster-whisper": FasterWhisperSTT,
    },
    "tts": {
        "kokoro": KokoroTTS,
        "chatterbox": ChatterboxTTS,
        "orpheus": OrpheusTTS,
        "piper": PiperTTS,
    },
    "vad": {
        "silero": SileroVAD,
    },
    "wake_word": {
        "openwakeword": OpenWakeWordProvider,
    },
    "llm": {
        "ollama": OllamaLLM,
        "openai-compat": OpenAICompatLLM,
    },
}

def create_provider(category: str, name: str) -> STTProvider | TTSProvider | VADProvider | WakeWordProvider | LLMProvider:
    """Factory: create a provider by category and name."""
    if category not in PROVIDER_REGISTRY:
        raise ValueError(f"Unknown provider category: {category}")
    if name not in PROVIDER_REGISTRY[category]:
        raise ValueError(f"Unknown {category} provider: {name}. Available: {list(PROVIDER_REGISTRY[category].keys())}")
    return PROVIDER_REGISTRY[category][name]()
```

### 3.4 Configuration Schema

```yaml
# config.yaml — Full example
echo_node:
  name: "Gimp"
  version: "1.0.0"

audio:
  sample_rate: 16000
  channels: 1
  chunk_size: 512                    # frames per buffer
  device: null                       # null = system default

wake_word:
  provider: openwakeword
  model: "yo_gimp"                   # model name or path to .onnx
  threshold: 0.5
  cooldown_ms: 2000                  # ignore wake words for 2s after activation

activation_sound:
  enabled: true
  sound: beep                        # beep | chime | silent | path/to/custom.wav

vad:
  provider: silero
  threshold: 0.5
  min_speech_ms: 250
  max_silence_ms: 1500               # endpointing: silence this long → stop listening

stt:
  provider: sherpa-onnx              # sherpa-onnx | faster-whisper
  model: "sherpa-onnx-streaming-zipformer-en-2023-06-26"
  device: cuda                       # cuda | cpu | openvino
  language: en

tts:
  provider: kokoro                   # kokoro | chatterbox | orpheus | piper
  model: "kokoro-v1.0"
  voice: "af_heart"
  device: cuda
  streaming: true                    # sentence-boundary chunking
  sample_rate: 24000

llm:
  provider: openai-compat            # ollama | openai-compat
  model: "llama3.2:7b-q4_K_M"       # or "gpt-4o", "claude-sonnet-4-20250514", etc.
  base_url: "http://localhost:11434/v1"  # Ollama, OpenRouter, OpenAI, Hermes — any OpenAI-compat URL
  api_key: ""                        # Optional — blank for Ollama, required for OpenRouter/OpenAI
  temperature: 0.7
  max_tokens: 256
  tools: []                          # MCP tool definitions (Phase 3)

personality:
  active: hacker                     # name of preset file (without .yaml) or "custom"
  custom_prompt: ""                  # used if active == "custom"

conversation:
  memory_turns: 15                   # sliding window of conversation history
  persist_across_sessions: false     # agent handles cross-session memory

echo_cancellation:
  mode: mute                         # mute | speexdsp | none
  speexdsp:
    filter_length: 4096
    frame_size: 512

integrations:
  hermes:
    enabled: false
    url: "ws://localhost:8765"
    channel_name: "echo-node-voice"
  openclaw:
    enabled: false
    skill_dir: "~/.openclaw/skills/echo-node"
  mcp:
    enabled: false
    servers: []                      # MCP server configs

ui:
  mode: web                          # web | headless
  theme: minimal                     # none | minimal | cyberpunk | retro-terminal | glassmorphism
  avatar:
    model: random                    # "random" | specific VRM filename | path to custom .vrm
    pool:                            # 10-15 default VRM avatars for rotation
      - "avatar-01-casual.vrm"
      - "avatar-02-punk.vrm"
      - "avatar-03-corporate.vrm"
      - "avatar-04-anime.vrm"
      - "avatar-05-robot.vrm"
      - "avatar-06-witch.vrm"
      - "avatar-07-pirate.vrm"
      - "avatar-08-cyborg.vrm"
      - "avatar-09-elf.vrm"
      - "avatar-10-scientist.vrm"
      - "avatar-11-ninja.vrm"
      - "avatar-12-steampunk.vrm"
    idle_animations: true
    eye_tracking: true
  port: 3000

gateway:
  port: 3000
  worker_url: "ws://localhost:9001"

worker:
  port: 9001
  log_level: info                    # debug | info | warn | error
```

### 3.5 Configuration Loader (TypeScript)

```typescript
// gateway/src/utils/config-loader.ts
import { readFileSync } from 'fs';
import { parse } from 'yaml';
import { join } from 'path';

export interface EchoNodeConfig {
  echo_node: { name: string; version: string };
  audio: { sample_rate: number; channels: number; chunk_size: number; device: string | null };
  wake_word: { provider: string; model: string; threshold: number; cooldown_ms: number };
  activation_sound: { enabled: boolean; sound: string };
  vad: { provider: string; threshold: number; min_speech_ms: number; max_silence_ms: number };
  stt: { provider: string; model: string; device: string; language: string };
  tts: { provider: string; model: string; voice: string; device: string; streaming: boolean; sample_rate: number };
  llm: { provider: string; model: string; base_url: string; api_key: string; temperature: number; max_tokens: number; tools: unknown[] };
  personality: { active: string; custom_prompt: string };
  conversation: { memory_turns: number; persist_across_sessions: boolean };
  echo_cancellation: { mode: string; speexdsp?: { filter_length: number; frame_size: number } };
  integrations: {
    hermes: { enabled: boolean; url: string; channel_name: string };
    openclaw: { enabled: boolean; skill_dir: string };
    mcp: { enabled: boolean; servers: unknown[] };
  };
  ui: {
    mode: 'web' | 'headless';
    theme: string;
    avatar: { model: string; pool: string[]; idle_animations: boolean; eye_tracking: boolean };
    port: number;
  };
  gateway: { port: number; worker_url: string };
  worker: { port: number; log_level: string };
}

export function loadConfig(configPath?: string): EchoNodeConfig {
  const path = configPath ?? join(process.cwd(), 'config.yaml');
  const raw = readFileSync(path, 'utf-8');
  const config = parse(raw) as EchoNodeConfig;
  validateConfig(config);
  return config;
}

function validateConfig(config: EchoNodeConfig): void {
  const errors: string[] = [];
  if (!config.stt?.provider) errors.push('stt.provider is required');
  if (!config.tts?.provider) errors.push('tts.provider is required');
  if (!config.llm?.provider) errors.push('llm.provider is required');
  if (!config.wake_word?.provider) errors.push('wake_word.provider is required');
  if (errors.length > 0) {
    throw new Error(`Config validation failed:\n${errors.map(e => `  - ${e}`).join('\n')}`);
  }
}
```

### 3.6 WebSocket Protocol

All communication between layers uses WebSocket with JSON messages (events) and binary frames (audio).

```typescript
// gateway/src/utils/types.ts

/** Events from Python worker → Gateway → Frontend */
export type WorkerEvent =
  | { type: 'state_change'; from: string; to: string; timestamp: number }
  | { type: 'transcript_partial'; text: string }
  | { type: 'transcript_final'; text: string }
  | { type: 'llm_token'; token: string }
  | { type: 'llm_complete'; text: string }
  | { type: 'tts_audio'; data: ArrayBuffer; sample_rate: number }  // binary frame
  | { type: 'tts_complete' }
  | { type: 'error'; message: string; code: string }
  | { type: 'vram_report'; total_mb: number; used_mb: number; available_mb: number };

/** Events from Frontend → Gateway → Python worker */
export type ClientEvent =
  | { type: 'keyboard_trigger' }        // manual activation
  | { type: 'barge_in' }               // interrupt speaking
  | { type: 'config_update'; config: Partial<EchoNodeConfig> }
  | { type: 'stop' };                  // halt pipeline
```

### 3.7 Streaming TTS Pipeline

The most latency-critical path. LLM response text is chunked at sentence boundaries, and each sentence is synthesized in parallel with playback of the previous sentence.

```python
# worker/streaming/sentence_chunker.py
import re
from typing import AsyncIterator

SENTENCE_END = re.compile(r'(?<=[.!?])\s+')

async def chunk_sentences(token_stream: AsyncIterator[str]) -> AsyncIterator[str]:
    """
    Buffer LLM tokens and yield complete sentences.
    Yields each sentence as soon as a sentence-ending boundary is detected.
    """
    buffer = ""
    async for token in token_stream:
        buffer += token
        parts = SENTENCE_END.split(buffer)
        # Yield all complete sentences, keep the last (possibly incomplete) part
        while len(parts) > 1:
            sentence = parts.pop(0).strip()
            if sentence:
                yield sentence
            buffer = " ".join(parts)
    # Yield any remaining text
    if buffer.strip():
        yield buffer.strip()
```

```python
# worker/pipeline.py (streaming orchestration — simplified)
async def process_utterance(self, transcript: str) -> None:
    """Main pipeline: transcript → LLM → streaming TTS → playback."""
    await self.state_machine.transition(State.PROCESSING)

    # 1. Stream LLM response
    messages = self._build_messages(transcript)
    token_stream = self.llm.chat_stream(messages)

    # 2. Chunk into sentences
    sentence_stream = chunk_sentences(token_stream)

    # 3. Synthesize and play each sentence as it arrives
    await self.state_machine.transition(State.SPEAKING)

    async for sentence in sentence_stream:
        # Emit text to frontend for display
        await self._emit_event({"type": "llm_token", "token": sentence + " "})

        # Synthesize audio for this sentence
        audio = await self.tts.synthesize(sentence)

        # Play audio (blocking until this sentence finishes)
        await self.audio_playback.play(audio)

        # Check for barge-in between sentences
        if self._barge_in_requested:
            break

    await self._emit_event({"type": "tts_complete"})
    await self.state_machine.transition(State.DORMANT)
```

### 3.8 TalkingHead Integration (Frontend)

TalkingHead is loaded as an external module. The Svelte component wraps it and feeds audio data for lip-sync.

```svelte
<!-- frontend/src/lib/components/avatar-display.svelte -->
<script lang="ts">
  import { onMount } from 'svelte';

  let { audioData = $bindable<Float32Array | null>(null), isIdle = true } = $props();

  let container: HTMLDivElement;
  let talkingHead: any = $state(null);

  onMount(async () => {
    // Dynamic import — TalkingHead is a large module
    const { TalkingHead } = await import('talkinghead');

    talkingHead = new TalkingHead(container, {
      ttsEndpoint: null, // We provide audio directly, not via TalkingHead's TTS
      cameraView: 'upper',
      cameraDistance: 0.4,
    });

    // Load default VRM model
    await talkingHead.showAvatar({
      url: '/models/default.vrm',
      body: 'F',
      avatarMood: 'neutral',
      lipsyncLang: 'en',
    });
  });

  // React to audio data for lip-sync
  $effect(() => {
    if (talkingHead && audioData) {
      talkingHead.speakAudio(audioData);
    }
  });

  // Idle animations when not speaking
  $effect(() => {
    if (talkingHead && isIdle) {
      talkingHead.setMood('neutral');
    }
  });
</script>

<div bind:this={container} class="avatar-container"></div>

<style>
  .avatar-container {
    width: 100%;
    height: 100%;
    border-radius: var(--radius-lg);
    overflow: hidden;
  }
</style>
```

---

## 4. Integration Adapters

### 4.1 Hermes Channel Adapter

Hermes v0.3.0+ supports WebSocket channel registration. Echo-Node registers as a voice input/output channel.

```typescript
// gateway/src/integrations/hermes-adapter.ts

export class HermesAdapter {
  private ws: WebSocket | null = null;

  async connect(url: string, channelName: string): Promise<void> {
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      // Register as a voice channel
      this.ws!.send(JSON.stringify({
        type: 'channel.register',
        channel: {
          name: channelName,
          type: 'voice',
          capabilities: ['input', 'output'],
          format: 'text',  // We handle STT/TTS; Hermes gets text
        },
      }));
    };

    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data as string);
      if (msg.type === 'channel.message') {
        // Hermes wants to speak through us
        this.onHermesMessage(msg.content);
      }
    };
  }

  /** Send user's transcribed speech to Hermes */
  async sendTranscript(text: string): Promise<void> {
    if (!this.ws) return;
    this.ws.send(JSON.stringify({
      type: 'channel.input',
      content: text,
      source: 'voice',
    }));
  }

  /** Receive Hermes response for TTS */
  onHermesMessage: (content: string) => void = () => {};

  async disconnect(): Promise<void> {
    this.ws?.close();
    this.ws = null;
  }
}
```

### 4.2 OpenClaw Skill Adapter

OpenClaw uses skill files. Echo-Node generates a skill file that OpenClaw discovers.

```typescript
// gateway/src/integrations/openclaw-adapter.ts
import { writeFileSync, mkdirSync } from 'fs';
import { join } from 'path';

const SKILL_TEMPLATE = `---
name: echo-node-voice
description: Voice input/output channel via Echo-Node
version: 1.0.0
triggers:
  - "voice"
  - "speak"
  - "listen"
  - "say"
---

# Echo-Node Voice Skill

This skill provides voice input and output capabilities via the Echo-Node voice agent.

## Capabilities

- **Voice Input**: Transcribe user speech to text
- **Voice Output**: Synthesize text to speech for the user
- **Conversation**: Full voice conversation loop

## API

Echo-Node exposes a WebSocket at \`ws://localhost:3000/ws\` for real-time voice events.

### Send text to speech
\`\`\`json
{"type": "tts_request", "text": "Hello, I am OpenClaw speaking through Echo-Node."}
\`\`\`

### Receive transcribed speech
Listen for \`transcript_final\` events on the WebSocket.
`;

export function installOpenClawSkill(skillDir: string): void {
  mkdirSync(skillDir, { recursive: true });
  writeFileSync(join(skillDir, 'SKILL.md'), SKILL_TEMPLATE, 'utf-8');
}
```

---

## 5. Cross-Platform Support

### 5.1 Device Detection (Python)

```python
# worker/audio/vram_calculator.py
import subprocess
from dataclasses import dataclass

@dataclass
class GPUInfo:
    name: str
    vram_total_mb: int
    vram_available_mb: int
    backend: str  # "cuda" | "openvino" | "cpu"

def detect_gpu() -> GPUInfo:
    """Detect available GPU and backend."""
    # Try CUDA first (NVIDIA)
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            free, total = torch.cuda.mem_get_info(0)
            return GPUInfo(
                name=props.name,
                vram_total_mb=total // (1024 * 1024),
                vram_available_mb=free // (1024 * 1024),
                backend="cuda",
            )
    except ImportError:
        pass

    # Try OpenVINO (Intel Arc)
    try:
        import openvino
        return GPUInfo(
            name="Intel Arc (OpenVINO)",
            vram_total_mb=0,  # OpenVINO uses system RAM
            vram_available_mb=0,
            backend="openvino",
        )
    except ImportError:
        pass

    # CPU fallback
    return GPUInfo(
        name="CPU",
        vram_total_mb=0,
        vram_available_mb=0,
        backend="cpu",
    )

def check_vram_budget(providers: dict, gpu: GPUInfo) -> tuple[bool, str]:
    """Check if all providers fit in available VRAM."""
    total_needed = sum(p.vram_requirement_mb for p in providers.values())
    if gpu.backend == "cpu":
        return True, f"CPU mode: models use system RAM ({total_needed}MB estimated)"
    if total_needed > gpu.vram_available_mb:
        return False, (
            f"VRAM budget exceeded: {total_needed}MB needed, "
            f"{gpu.vram_available_mb}MB available on {gpu.name}"
        )
    return True, f"VRAM OK: {total_needed}MB / {gpu.vram_available_mb}MB on {gpu.name}"
```

### 5.2 WSL2 Audio Setup

```bash
#!/bin/bash
# setup.sh — WSL2 audio detection + model download

echo "=== Echo-Node Setup ==="

# 1. Detect WSL2
if grep -qi microsoft /proc/version 2>/dev/null; then
    echo "[WSL2] Detected WSL2 environment"
    
    # Check PipeWire (Fedora 43+ / WSLg)
    if command -v pw-cli &>/dev/null; then
        echo "[WSL2] PipeWire detected ✓"
    elif command -v pulseaudio &>/dev/null; then
        echo "[WSL2] PulseAudio detected ✓"
    else
        echo "[WSL2] ⚠ No audio server detected. Install pipewire or pulseaudio."
        echo "  Fedora: sudo dnf install pipewire pipewire-pulseaudio"
        echo "  Ubuntu: sudo apt install pulseaudio"
    fi
    
    # Check mic access
    if [ -e /dev/snd ]; then
        echo "[WSL2] Audio devices accessible ✓"
    else
        echo "[WSL2] ⚠ /dev/snd not found. Ensure WSLg is enabled."
    fi
else
    echo "[Native] Linux/macOS detected"
fi

# 2. Install Python dependencies
echo ""
echo "=== Installing Python dependencies ==="
pip install -r worker/requirements.txt

# 3. Download models
echo ""
echo "=== Downloading models ==="
python -c "
from worker.providers.stt.sherpa_stt import SherpaSTT
from worker.providers.tts.kokoro_tts import KokoroTTS
from worker.providers.wake_word.openwakeword import OpenWakeWordProvider
from worker.providers.vad.silero_vad import SileroVAD

print('Downloading STT model...')
SherpaSTT.download_default_model()
print('Downloading TTS model...')
KokoroTTS.download_default_model()
print('Downloading wake word model...')
OpenWakeWordProvider.download_default_model()
print('Downloading VAD model...')
SileroVAD.download_default_model()
print('✓ All models downloaded')
"

echo ""
echo "=== Setup complete ==="
echo "Run: bun run dev (gateway) + python worker/main.py (worker)"
```

---

## 6. Implementation Phases

### Phase 1: CLI MVP (Weeks 1-3)

**Build:**
- Python audio worker: mic → VAD → wake word → STT → LLM → TTS → speaker
- State machine (5 states)
- Provider ABCs + Kokoro TTS + sherpa-onnx STT + Silero VAD + OpenWakeWord
- Mic mute echo cancellation
- config.yaml loader + validator
- Bun/Hono gateway (health endpoint + WebSocket relay)
- Terminal transcript display (Python stdout)
- Setup script (deps + model download)
- VRAM calculator

**Acceptance:**
- `python worker/main.py` starts listening
- Say "hey echo" → hear beep → speak → hear TTS response
- Transcript printed to terminal
- `GET /api/health` returns `{ "status": "ok", "worker": "connected" }`

### Phase 2: Web UI + Avatar (Weeks 4-6)

**Build:**
- Svelte 5 frontend (SvelteKit)
- TalkingHead integration (VRM avatar + lip-sync)
- Frame theme system (5 CSS themes)
- Waveform visualizer (LISTENING state)
- Conversation transcript panel
- Status indicator component
- Alternative providers: Chatterbox TTS, faster-whisper STT
- Barge-in support
- VRAM usage display

**Acceptance:**
- Open `http://localhost:3000` → see avatar
- Speak → avatar responds with lip-synced speech
- Change theme → UI updates
- Switch `stt.provider` in config → restart → new STT active

### Phase 3: Integrations (Weeks 7-9)

**Build:**
- Hermes channel adapter (WebSocket registration)
- OpenClaw skill file generator
- MCP tool calling via LLM function calling
- SpeexDSP echo cancellation
- Settings panel in frontend
- Multi-session support in gateway

**Acceptance:**
- Hermes Agent receives voice input through Echo-Node
- OpenClaw discovers Echo-Node as an available skill
- Voice command "search the web for X" invokes MCP tool

### Phase 4: Polish (Weeks 10+)

**Build:**
- OpenVINO backend for Intel Arc
- Custom wake word training guide
- Provider plugin discovery (auto-register from directory)
- Performance profiling + latency optimization
- Documentation (setup guides for Fedora, WSL2, macOS)

---

## 7. Technology Stack

| Component | Package | Version | Purpose |
|-----------|---------|---------|---------|
| **Gateway runtime** | Bun | 1.1+ | Server runtime |
| **Gateway framework** | Hono | 4.x | HTTP + WebSocket server |
| **Frontend** | SvelteKit | 2.x (Svelte 5) | Web UI |
| **Avatar** | talkinghead | latest | VRM avatar + lip-sync |
| **Config** | yaml (npm) | 2.x | YAML parsing |
| **Logging** | pino | 9.x | Structured logging (gateway) |
| **Python** | Python | 3.11+ | Audio worker runtime |
| **STT** | sherpa-onnx | 1.x | Streaming speech-to-text |
| **TTS** | kokoro | 1.0+ | Text-to-speech (default) |
| **TTS alt** | chatterbox | latest | Real-time TTS |
| **VAD** | silero-vad | latest | Voice activity detection |
| **Wake word** | openwakeword | latest | Custom keyword detection |
| **LLM** | ollama | latest | Local LLM inference |
| **Audio** | sounddevice | 0.5+ | Mic capture + playback |
| **AEC** | speexdsp | latest | Echo cancellation (Phase 3) |
| **WebSocket** | websockets | 12+ | Python WebSocket server |
| **Logging** | structlog | 24+ | Structured logging (Python) |

---

## 8. Extension Points

1. **New STT/TTS/VAD/wake word provider** — Subclass the ABC, register in `PROVIDER_REGISTRY`
2. **New LLM provider** — Implement `LLMProvider` (Anthropic, Google, local vLLM)
3. **New frame theme** — Add CSS file to `frontend/src/lib/themes/`
4. **New integration adapter** — Add to `gateway/src/integrations/`
5. **Custom VRM avatar** — Drop `.vrm` file in `frontend/src/static/models/`, reference in config
6. **Custom wake word** — Train with OpenWakeWord toolkit, reference `.onnx` in config
