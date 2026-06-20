# Echo-Node v2 — Implementation Status

## ✅ COMPLETED (Live)

### Core Pipeline
- [x] Faster-whisper STT (tiny model, CPU, ~0.35s) — replaced Parakeet
- [x] dots.tts TTS (GPU, SOTA quality, ~2s gen)
- [x] Kokoro TTS fallback (CPU, faster for short responses)
- [x] Silero VAD + barge-in support
- [x] OpenWakeWord detection (hey rhasspy)
- [x] Silence timeout reduced to 0.5s
- [x] Speech formatting — tables summarized, code described, 4-sentence cap

### LLM Routing
- [x] Hermes API server at `:8642` (OpenCode Zen, nemotron-ultra-free)
- [x] Fast path: OpenRouter → nex-agi/nex-n2-pro:free (~1.3s)
- [x] Agent path: Hermes API → full agent loop with tools (~4-9s)
- [x] Nemotron Ultra path: OpenCode Zen → 550B free model
- [x] GPT Audio Mini/Audio routes defined (needs OR credits)
- [x] SmartRouter — keyword-based classification with persistent cost tracking

### Keyboard Hotkeys
- [x] Terminal Enter to trigger manual turn
- [x] Escape key toggle (Linux /dev/input, macOS pynput)
- [x] Non-blocking threaded listener

### Native Integrations
- [x] Hermes — direct API integration via `:8642` with "ask hermes ..." voice command
- [x] Pi agent — subprocess integration with "ask pi ..." voice command
- [x] Ollama — local llama3.2:3b available
- [x] Claude Code / Codex — CLI via Clutch Gateway

### Speech Formatting
- [x] Table summarization ("The table has 5 rows with columns...")
- [x] Code block descriptions ("Code block with 12 lines")
- [x] Markdown stripping for speech
- [x] Configurable max sentences (default: 4)
- [x] Voice toggle: "be verbose" / "be concise"

### Security & Config
- [x] API keys loaded from .env file (not hardcoded in config.yaml)
- [x] .env.example template provided
- [x] SmartRouter cost tracking persists across calls

### Avatar
- [x] 5 characters preprocessed (raccoon-hacker, owl-wizard, axolotl-astronaut, axolotl-helmet, raccoon-cyber)
- [x] Async Rhubarb preload (non-blocking speech)
- [x] PyQt6 sidecar with stdin JSON protocol
- [x] 9 visemes (A-H, X) per character

---

## 📋 REMAINING TASKS

### Priority 1: Streaming TTS
- [ ] Wire dots.tts `generate_stream()` into InterruptibleSpeaker for first-token latency
- [ ] Kokoro chunked synthesis for long responses

### Priority 2: Smart Router Improvements
- [ ] LLM-based classification (tiny model or free API call)
- [ ] Confidence thresholds — fallback if confidence < 0.6
- [ ] Session-aware routing — remember last agent, prefer for follow-ups

### Priority 3: Session Management
- [ ] Persistent agent sessions in tmux
- [ ] "Continue my Claude session" voice command
- [ ] Unified session list

### Priority 4: Paid Model Integration
- [ ] Test gpt-audio-mini ($0.14/hr) — native audio I/O
- [ ] Test gpt-audio ($0.56/hr) — premium voice quality
- [ ] Cost cap: auto-switch to free model if session > $X

### Priority 5: API Keys
- [ ] Renew Gemini API key ($20 plan exists)
- [ ] Fix Anthropic key ($20 plan exists)
- [ ] Add Gemini 2.5 Flash route ($0.16/hr)

### Priority 6: Polish
- [ ] Config validation at startup
- [ ] Graceful degradation if Hermes is down → fall through to OpenRouter
- [ ] Latency dashboard (real-time pipeline stage display)
- [ ] 4-bit dots.tts quantization via bitsandbytes

### Priority 7: Long-term
- [ ] Local LLM fallback (llama.cpp) when offline
- [ ] Custom wake word training via OpenWakeWord fine-tuning
- [ ] Voice cloning via dots.tts reference audio

---

## Architecture

```
wake word (OpenWakeWord) → VAD (Silero) → STT (faster-whisper)
       ↓
  KeyboardHotkey (Enter/Escape toggle)
       ↓
  SmartRouter.classify()
       ↓
  ┌─────────┼──────────────┼──────────────┐
  ↓         ↓              ↓              ↓
  "tool"   "code"       "complex"     default
  ↓         ↓              ↓              ↓
  Hermes   Claude/Codex   Nemotron      Fast/OpenRouter
  (native) (CLI)          (OC Zen)      (free)
       ↓
  SpeechFormatter (tables→summary, code→desc, 4-sentence cap)
       ↓
  InterruptibleSpeaker → dots.tts (GPU) / Kokoro (CPU) / espeak-ng
       ↓
  Avatar (async Rhubarb lip-sync → PyQt6 sidecar)
```
