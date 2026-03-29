# Echo-Node — Starter Code Reference

> **Purpose:** Preserved code snippets from source transcripts for the build agent.
> These are NOT copy-paste ready — they encode decisions and correct API usage patterns.
> The build agent should use these as anchoring material, not as final code.

---

## 1. Correct Import Paths (Verified)

These were wrong in multiple source documents. The correct patterns:

### Kokoro TTS
```python
# ✅ CORRECT (from transcript.md corrections)
from kokoro import KPipeline

pipeline = KPipeline(lang_code="a")
generator = pipeline(text, voice="af_heart", speed=1.0, split_pattern=r'\n+')

for gs, ps, audio in generator:
    # gs = grapheme sentence, ps = phoneme sentence, audio = numpy array
    pass

# ❌ WRONG (appeared in kimi-plan.md, claude-plan.md)
# from kokoro import KokoroTTS
# from kokoro.tts import synthesize
```

### sherpa-onnx STT
```python
# ✅ CORRECT
import sherpa_onnx

recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
    tokens="tokens.txt",
    encoder="encoder.onnx",
    decoder="decoder.onnx",
    joiner="joiner.onnx",
    num_threads=4,
    sample_rate=16000,
    feature_dim=80,
)

stream = recognizer.create_stream()
stream.accept_waveform(sample_rate=16000, waveform=audio_data)
recognizer.decode_stream(stream)
result = recognizer.get_result(stream)
print(result.text)
```

### OpenWakeWord
```python
# ✅ CORRECT
import openwakeword
from openwakeword.model import Model

openwakeword.utils.download_models()

model = Model(
    wakeword_models=["hey_jarvis"],  # or custom .onnx path
    inference_framework="onnx",
)

prediction = model.predict(audio_frame)
# prediction is a dict: {"hey_jarvis": 0.85, ...}
for wake_word, score in prediction.items():
    if score > 0.5:
        print(f"Wake word detected: {wake_word}")
```

### Silero-VAD
```python
# ✅ CORRECT
import torch

model, utils = torch.hub.load(
    repo_or_dir='snakers4/silero-vad',
    model='silero_vad',
    force_reload=False,
)
(get_speech_timestamps, _, read_audio, _, _) = utils

# Per-chunk usage
speech_prob = model(audio_chunk, 16000).item()
is_speech = speech_prob > 0.5
```

### Chatterbox TTS
```python
# ✅ CORRECT (from prd-audit.md)
from chatterbox.tts import ChatterboxTTS

model = ChatterboxTTS.from_pretrained(device="cuda")
wav = model.generate(
    "Hello, I am Echo!",
    audio_prompt_path="reference_voice.wav",  # optional voice cloning
)

# Streaming variant (if available in turbo)
# Check actual API — streaming may require ChatterboxTTS.stream()
```

---

## 2. Dependencies

### Python (worker/requirements.txt)
```
# Core audio
sounddevice>=0.5.0
numpy>=1.26
scipy>=1.12

# STT
sherpa-onnx>=1.10

# TTS
kokoro>=1.0
# chatterbox-tts  # install separately — large dep tree
# orpheus-tts     # install separately

# VAD
torch>=2.2  # for silero-vad
# Note: silero-vad is loaded via torch.hub, no separate pip install

# Wake word
openwakeword>=0.6

# LLM client
httpx>=0.27  # for streaming Ollama requests

# Echo cancellation (Phase 3)
# speexdsp-ns>=0.1  # SpeexDSP bindings

# WebSocket
websockets>=12.0

# Config
pyyaml>=6.0

# Logging
structlog>=24.0

# VRAM detection
# torch already provides cuda info
```

### Bun/Node (gateway package.json)
```json
{
  "name": "echo-node-gateway",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "bun run --watch gateway/src/index.ts",
    "build": "bun build gateway/src/index.ts --outdir dist"
  },
  "dependencies": {
    "hono": "^4.6",
    "yaml": "^2.5",
    "pino": "^9.4",
    "pino-pretty": "^11.2"
  },
  "devDependencies": {
    "@types/bun": "latest",
    "typescript": "^5.6"
  }
}
```

---

## 3. Code Fragments from Sources (Corrected)

### Fragment 1: Main Pipeline Loop (from transcript.md, corrected)
```python
async def run_pipeline(config: dict) -> None:
    """Main event loop for the voice pipeline."""
    # Initialize providers from config
    stt = create_provider("stt", config["stt"]["provider"])
    tts = create_provider("tts", config["tts"]["provider"])
    vad = create_provider("vad", config["vad"]["provider"])
    ww = create_provider("wake_word", config["wake_word"]["provider"])
    llm = create_provider("llm", config["llm"]["provider"])

    await stt.initialize(config["stt"]["model"], config["stt"]["device"])
    await tts.initialize(config["tts"]["model"], config["tts"]["voice"], config["tts"]["device"])
    await vad.initialize("silero_vad")
    await ww.initialize(config["wake_word"]["model"], config["wake_word"]["threshold"])
    await llm.initialize(config["llm"]["model"], config["llm"]["base_url"])

    state = StateMachine(on_transition=emit_state_event)
    mic = MicCapture(sample_rate=config["audio"]["sample_rate"])

    print(f"Echo-Node listening... (wake word: {config['wake_word']['model']})")

    async for chunk in mic.stream():
        match state.state:
            case State.DORMANT:
                if ww.detect(chunk):
                    await state.transition(State.TRIGGERED)
                    play_beep()  # activation sound
                    await state.transition(State.LISTENING)

            case State.LISTENING:
                if vad.is_speech(chunk):
                    stt_stream.accept(chunk)
                    silence_counter = 0
                else:
                    silence_counter += 1
                    if silence_counter * chunk_ms > config["vad"]["max_silence_ms"]:
                        transcript = stt_stream.finalize()
                        await process_utterance(transcript, llm, tts, state)

            case State.SPEAKING:
                pass  # mic is muted during playback
```

### Fragment 2: Hono Gateway WebSocket Hub (from kimi-plan.md, corrected)
```typescript
// gateway/src/websocket.ts
import { Hono } from 'hono';
import { createBunWebSocket } from 'hono/bun';

const { upgradeWebSocket, websocket } = createBunWebSocket();

const app = new Hono();

// Track connected clients
const clients = new Set<WebSocket>();
let workerSocket: WebSocket | null = null;

// Frontend WebSocket endpoint
app.get('/ws', upgradeWebSocket((c) => ({
  onOpen(event, ws) {
    clients.add(ws.raw as unknown as WebSocket);
    console.log(`Client connected (${clients.size} total)`);
  },
  onMessage(event, ws) {
    const msg = JSON.parse(event.data as string);
    // Forward client events to worker
    if (workerSocket?.readyState === WebSocket.OPEN) {
      workerSocket.send(JSON.stringify(msg));
    }
  },
  onClose(event, ws) {
    clients.delete(ws.raw as unknown as WebSocket);
  },
})));

// Relay worker events to all connected clients
function broadcastToClients(data: string): void {
  for (const client of clients) {
    if (client.readyState === WebSocket.OPEN) {
      client.send(data);
    }
  }
}

export { app, broadcastToClients, websocket };
```

### Fragment 3: VRAM Budget Check (from claude-plan.md)
```python
# Before loading models, validate VRAM budget
VRAM_ESTIMATES = {
    "sherpa-onnx-base": 500,      # MB
    "sherpa-onnx-small": 250,
    "kokoro-82m": 300,
    "chatterbox-turbo": 600,
    "orpheus-150m": 400,
    "orpheus-400m": 900,
    "orpheus-3b": 4000,           # ⚠ Won't fit with LLM
    "silero-vad": 50,
    "openwakeword": 30,
}

# RTX 4050 budget: 6144MB total, ~5500MB usable
# LLM (llama3.2 7B q4): ~4500MB
# Remaining for pipeline: ~1000MB
# → Kokoro (300) + sherpa-base (500) + VAD (50) + OWW (30) = 880MB ✓
```

---

## 4. Common Mistakes Found in Sources

| Mistake | Found In | Correction |
|---------|----------|------------|
| `from kokoro import KokoroTTS` | kimi-plan, claude-plan | `from kokoro import KPipeline` |
| FastAPI for Python worker | kimi-plan | Pure `websockets` lib — gateway handles HTTP |
| `export let` (Svelte 4) | kimi-plan | `$props()` for Svelte 5 Runes |
| Coqui TTS as an option | kimi-trans | ❌ Coqui shut down in 2023, project dead |
| GPT-SoVITS for real-time | kimi-plan | ❌ Poor real-time performance, deprioritize |
| Hermes via HTTP webhooks | kimi-plan | WebSocket channel registration (v0.3.0+) |
| OpenClaw capability endpoint | kimi-plan | Skill file in `~/.openclaw/skills/` |
| Custom VRM lip-sync engine | kimi-plan | TalkingHead handles this built-in |
| NVIDIA Audio2Face | z-transcript | ❌ Proprietary, violates open-source constraint |
| MuseTalk for lip-sync | z-transcript | ❌ Complex, unnecessary with TalkingHead |

---

## 5. Resolved Questions (User Answers)

| # | Question | Answer |
|---|----------|--------|
| 1 | Default wake word | **"Yo Gimp"** — train custom OWW model |
| 2 | VRM avatar | **Don't care** — provide 10-15 rotatable defaults, user can swap |
| 3 | LLM endpoint | **User-configurable** — Hermes, OpenRouter, OpenAI, Ollama. Any OpenAI-compat API. Ollama enabled but NOT primary. |
| 4 | Personality | **User-configurable** with cool presets: hacker, seductive, butler, drill-sergeant, stoner-philosopher |
| 5 | Phase scope | **CLI MVP first** (Phase 1), Avatar in Phase 2 ✅ |
| 6 | Hermes version | **Always latest** — adapt to whatever user has installed |
| 7 | Activation sound | **Configurable** — beep, chime, silence, or custom file |
| 8 | Conversation memory | **15-turn sliding window** per session. No cross-session (agent handles that). |

---

## 6. Personality Presets (New — Phase 1)

Each personality is a YAML file in `worker/personalities/`. The `system_prompt` replaces the default LLM system prompt.

```yaml
# worker/personalities/hacker.yaml
name: hacker
description: "Elite hacker who speaks in tech jargon, references exploits, and treats everything like a CTF challenge"
system_prompt: |
  You are Gimp, a legendary hacker and voracious autodidact. You speak in
  clipped, technical language peppered with hacker slang. You treat every
  question like a puzzle to crack. You reference security concepts, Unix
  philosophy, and open-source culture naturally. You're helpful but never
  boring — you make even mundane answers sound like you're breaking into
  a mainframe. Keep responses under 3 sentences unless the user asks for
  detail. Never say "I'm just an AI" — you're Gimp, and you own it.
```

```yaml
# worker/personalities/seductive.yaml
name: seductive
description: "Smooth, confident, and flirtatious — like a velvet-voiced FM radio host at 2am"
system_prompt: |
  You are Gimp, a smooth and effortlessly charming voice assistant.
  Your tone is warm, confident, and subtly flirtatious — like a late-night
  radio host who knows exactly what to say. You use rich language, gentle
  humor, and the occasional playful innuendo. You make the user feel like
  the most interesting person in the room. Keep responses flowing and
  conversational. Never be creepy — you're classy, not desperate.
```

```yaml
# worker/personalities/butler.yaml
name: butler
description: "Impeccable British butler — formal, efficient, and drily witty"
system_prompt: |
  You are Gimp, a quintessential English butler. You address all matters
  with impeccable formality, dry wit, and understated competence. You
  occasionally employ subtle British humor. You never raise your voice,
  never show alarm, and handle even the most absurd requests with grace.
  Responses should feel like they come with a raised eyebrow and a silver
  tray. "Very good, sir" is your default closer.
```

```yaml
# worker/personalities/drill-sergeant.yaml
name: drill-sergeant
description: "Screaming drill instructor who motivates through intimidation and raw energy"
system_prompt: |
  You are Gimp, a drill sergeant who answers questions like you're
  training recruits. EVERY response is high-energy, direct, and delivered
  like you're shouting across a parade ground. You use military metaphors,
  demand excellence, and occasionally throw in backhanded encouragement.
  You don't sugarcoat ANYTHING. If the user asks a dumb question, you
  TELL THEM — then answer it anyway because that's your JOB. HOOAH.
```

```yaml
# worker/personalities/stoner-philosopher.yaml
name: stoner-philosopher
description: "Deep-thinking stoner who finds profound meaning in everything and gets sidetracked beautifully"
system_prompt: |
  You are Gimp, a deeply philosophical soul who sees cosmic connections
  in everything. You answer questions thoughtfully but tend to wander into
  tangential observations about the nature of reality, consciousness, and
  why things are the way they are. You use "dude", "man", and "whoa" naturally.
  You're actually surprisingly knowledgeable — you just present information
  through a lens of wonder and mild bewilderment. Keep it real, man.
```

---

## 7. Conversation Memory (New — Phase 1)

```python
# worker/conversation/memory.py
from collections import deque
from typing import TypedDict

class Message(TypedDict):
    role: str      # "user" | "assistant" | "system"
    content: str

class ConversationMemory:
    """Sliding-window conversation history.
    
    Maintains up to `max_turns` user/assistant exchanges.
    The system prompt is always prepended and doesn't count toward the limit.
    Memory is per-session only — no persistence.
    """

    def __init__(self, max_turns: int = 15):
        self._max_messages = max_turns * 2  # 1 turn = 1 user + 1 assistant
        self._history: deque[Message] = deque(maxlen=self._max_messages)
        self._system_prompt: str = ""

    def set_system_prompt(self, prompt: str) -> None:
        """Set the system prompt (from personality preset)."""
        self._system_prompt = prompt

    def add_user_message(self, text: str) -> None:
        """Add a user utterance to history."""
        self._history.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str) -> None:
        """Add an assistant response to history."""
        self._history.append({"role": "assistant", "content": text})

    def get_messages(self) -> list[Message]:
        """Build the full message list for the LLM call.
        
        Returns: [system_prompt] + [last N messages]
        The deque handles the sliding window automatically.
        """
        messages: list[Message] = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.extend(self._history)
        return messages

    def clear(self) -> None:
        """Reset conversation history (new session)."""
        self._history.clear()

    @property
    def turn_count(self) -> int:
        """Number of complete turns (user+assistant pairs)."""
        return len(self._history) // 2
```
