# Data Model: Echo-Node

**Date**: 2026-03-29
**Branch**: 001-echo-node-core

---

## Core Entities

### 1. Session

**Lifecycle**: Single continuous interaction from system start to shutdown.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique session identifier |
| `started_at` | datetime | Session start timestamp |
| `personality` | string | Active personality preset name |
| `conversation_history` | list[Turn] | Sliding window of up to 15 turns |
| `current_state` | State | Current pipeline state (DORMANT, TRIGGERED, etc.) |
| `client_id` | string | ID of connected client (browser, terminal, ESP32) |

**Validation Rules**:
- `conversation_history` max length: 15 turns
- No persistence across restarts (in-memory only)
- One active session at a time (MVP)

**State Transitions**:
```
DORMANT → TRIGGERED → LISTENING → PROCESSING → SPEAKING → DORMANT
                     ↑              ↓                          │
                     └──────────────┴──────────────────────────┘
                           (barge-in from SPEAKING)
```

---

### 2. Turn (Conversation History)

**Purpose**: Single exchange in conversation history.

| Field | Type | Description |
|-------|------|-------------|
| `turn_number` | int | Sequential turn number within session |
| `user_transcript` | string | User's spoken input (from STT) |
| `assistant_response` | string | Assistant's text response (from LLM) |
| `timestamp` | datetime | When turn occurred |

**Validation Rules**:
- Oldest turns discarded when history exceeds 15 turns
- Both `user_transcript` and `assistant_response` required

---

### 3. Provider

**Purpose**: Interchangeable implementation of a pipeline component.

| Field | Type | Description |
|-------|------|-------------|
| `category` | enum | One of: `stt`, `tts`, `vad`, `wake_word`, `llm` |
| `name` | string | Provider identifier (e.g., `sherpa-onnx`, `kokoro`) |
| `class` | type | Python class implementing ABC |
| `vram_requirement_mb` | int | VRAM needed by this provider's model |
| `config_schema` | dict | JSON Schema for provider-specific config |

**Supported Providers**:
```python
PROVIDER_REGISTRY = {
    "stt": {
        "sherpa-onnx": SherpaSTT,           # Default, Apache 2.0
        "faster-whisper": FasterWhisperSTT, # Fallback, MIT
        "vibevoice-asr": VibeVoiceASR,      # Optional (7B, 51 langs), MIT
    },
    "tts": {
        "kokoro": KokoroTTS,           # Default (82M), MIT
        "chatterbox": ChatterboxTTS,   # Quality tier, MIT
        "orpheus": OrpheusTTS,         # Emotion tier (150M/400M), Apache 2.0
        "piper": PiperTTS,             # Fallback, MIT
        # VibeVoice-TTS deferred (code removed Sept 2025)
    },
    "vad": {
        "silero": SileroVAD,  # MIT
    },
    "wake_word": {
        "openwakeword": OpenWakeWordProvider,  # Apache 2.0
    },
    "llm": {
        "ollama": OllamaLLM,           # Default (local), MIT
        "openai-compat": OpenAICompatLLM,  # OpenRouter, OpenAI, Hermes
    },
}
```

---

### 4. Personality

**Purpose**: Preset defining AI's tone and behavioral rules.

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Personality identifier (e.g., `hacker`, `butler`) |
| `description` | string | Short description of personality traits |
| `system_prompt` | string | Full system prompt injected into LLM |

**Default Personalities**:
1. `hacker` — Tech-savvy, concise, uses hacker slang
2. `seductive` — Flirtatious, playful, charming
3. `butler` — Formal, polite, British
4. `drill-sergeant` — Aggressive, motivational, military
5. `stoner-philosopher` — Laid-back, deep thoughts, stoner humor

**Custom Personalities**:
- Users can create custom `.yaml` files in `personalities/` directory
- Must include `name`, `description`, `system_prompt` fields

---

### 5. Avatar

**Purpose**: 3D VRM character model for visual display.

| Field | Type | Description |
|-------|------|-------------|
| `model_path` | string | Path to `.vrm` file |
| `display_name` | string | Human-readable name |
| `idle_animations` | bool | Whether idle animations are enabled |
| `eye_tracking` | bool | Whether eye tracking is enabled |

**Bundled Avatars** (10-15 default):
- `avatar-01-casual.vrm`
- `avatar-02-punk.vrm`
- `avatar-03-corporate.vrm`
- `avatar-04-anime.vrm`
- `avatar-05-robot.vrm`
- `avatar-06-witch.vrm`
- `avatar-07-pirate.vrm`
- `avatar-08-cyborg.vrm`
- `avatar-09-elf.vrm`
- `avatar-10-scientist.vrm`
- `avatar-11-ninja.vrm`
- `avatar-12-steampunk.vrm`

**Custom Avatars**:
- Users can add `.vrm` files to `frontend/src/static/models/`
- Appear in avatar selection list automatically

---

### 6. Configuration

**Purpose**: Single YAML file defining all pipeline behavior.

**Schema**:
```yaml
echo_node:
  name: string                    # Assistant name (e.g., "Gimp")
  version: string                 # Version string

audio:
  sample_rate: int                # Default: 16000
  channels: int                   # Default: 1
  chunk_size: int                 # Default: 512
  device: string | null           # null = system default

pipeline_mode: enum               # "local" | "cloud"

wake_word:
  provider: string                # "openwakeword"
  model: string                   # Model name or path
  threshold: float                # 0.0-1.0
  cooldown_ms: int                # Ignore period after activation

activation_sound:
  enabled: bool
  sound: string                   # "beep" | "chime" | "silent" | path

vad:
  provider: string                # "silero"
  threshold: float
  min_speech_ms: int
  max_silence_ms: int             # Endpointing threshold

stt:
  provider: string                # "sherpa-onnx" | "faster-whisper" | "vibevoice-asr"
  model: string
  device: string                  # "cuda" | "cpu" | "openvino"
  language: string

tts:
  provider: string                # "kokoro" | "chatterbox" | "orpheus" | "piper"
  model: string
  voice: string
  device: string
  streaming: bool
  sample_rate: int

llm:
  provider: string                # "ollama" | "openai-compat"
  model: string
  base_url: string
  api_key: string                 # Optional (blank for Ollama)
  temperature: float
  max_tokens: int
  tools: list                     # MCP tool definitions

personality:
  active: string                  # Personality name or "custom"
  custom_prompt: string           # Used if active == "custom"

conversation:
  memory_turns: int               # Default: 15
  persist_across_sessions: bool   # Default: false

echo_cancellation:
  mode: string                    # "mute" | "speexdsp" | "none"
  speexdsp:
    filter_length: int
    frame_size: int

integrations:
  hermes:
    enabled: bool
    url: string
    channel_name: string
  openclaw:
    enabled: bool
    skill_dir: string
  mcp:
    enabled: bool
    servers: list

ui:
  mode: enum                      # "web" | "headless"
  theme: string
  avatar:
    model: string                 # "random" | VRM filename | path
    pool: list[string]
    idle_animations: bool
    eye_tracking: bool
  port: int

gateway:
  port: int
  worker_url: string

worker:
  port: int
  log_level: string               # "debug" | "info" | "warn" | "error"
```

**Validation Rules**:
- `stt.provider`, `tts.provider`, `llm.provider`, `wake_word.provider` required
- Provider names must exist in `PROVIDER_REGISTRY`
- `llm.api_key` optional (blank for Ollama, required for OpenRouter/OpenAI)
- VRAM check before model load (warn if exceeds available)

---

### 7. Pipeline State

**Purpose**: 5-state lifecycle for voice pipeline.

| State | Description | Valid Transitions |
|-------|-------------|-------------------|
| `DORMANT` | Waiting for wake word | → TRIGGERED |
| `TRIGGERED` | Wake word detected, playing activation sound | → LISTENING |
| `LISTENING` | VAD active, capturing audio | → PROCESSING, → DORMANT (timeout) |
| `PROCESSING` | STT→LLM→TTS pipeline running | → SPEAKING, → DORMANT (error) |
| `SPEAKING` | TTS playback active | → DORMANT, → LISTENING (barge-in) |

**State Machine Rules**:
- All transitions originate from Python worker
- Gateway relays state events to frontend
- Invalid transitions rejected (return false)

---

### 8. Remote Client

**Purpose**: Device connecting to gateway over LAN.

| Field | Type | Description |
|-------|------|-------------|
| `client_type` | enum | "browser" | "terminal" | "esp32" |
| `ip_address` | string | Client IP on LAN |
| `protocol` | enum | "websocket-pcm" | "binary" (ESP32 fallback) |
| `wake_word_local` | bool | Whether client runs local wake word detection |

**Protocol Details**:
- Browser/Terminal: WebSocket with JSON events + binary PCM frames (16kHz)
- ESP32: Binary protocol with frame headers (fallback if raw PCM infeasible)
- All clients trigger independently (local wake word or hotkey)

---

## Relationships

```
Session (1) ── owns ──> Turn (0..15)
Session (1) ── uses ──> Personality (1)
Session (1) ── has ──> PipelineState (1)
Session (1) ── connected to ──> RemoteClient (0..1, MVP: max 1 active)

Configuration (1) ── selects ──> Provider (5: stt, tts, vad, wake_word, llm)
Configuration (1) ── selects ──> Avatar (1)
Configuration (1) ── selects ──> Personality (1)

Provider (1) ── implements ──> ABC (STTProvider, TTSProvider, etc.)
```

---

## Validation Rules Summary

| Entity | Rule | Error Message |
|--------|------|---------------|
| Configuration | `stt.provider` required | "stt.provider is required. Available: [list]" |
| Configuration | Provider name invalid | "Unknown {category} provider: {name}. Available: [list]" |
| Configuration | VRAM exceeded | "Selected models require {X}MB VRAM, but only {Y}MB available. Suggest: [alternatives]" |
| Session | Conversation history full | (Silent: oldest turn discarded) |
| Pipeline | Invalid state transition | (Silent: transition rejected, log warning) |
| Remote Client | Unauthorized LAN connection | (Log connection, no auth MVP) |
