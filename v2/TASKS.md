# Voice Agent — Implementation Status & Remaining Tasks

## ✅ COMPLETED (Live)

### Core Pipeline
- [x] Faster-whisper STT (tiny model, CPU, ~0.35s) — replaced Parakeet
- [x] dots.tts TTS (GPU, SOTA quality, ~2s gen)
- [x] Kokoro TTS fallback (CPU, faster for short responses)
- [x] Silero VAD + barge-in support
- [x] OpenWakeWord detection (hey rhasspy)
- [x] Silence timeout reduced to 0.5s

### LLM Routing
- [x] Hermes API server at `:8642` (OpenCode Zen, nemotron-ultra-free)
- [x] Fast path: OpenRouter → nex-agi/nex-n2-pro:free (~1.3s)
- [x] Agent path: Hermes API → full agent loop with tools (~4-9s)
- [x] Nemotron Ultra path: OpenCode Zen → 550B free model
- [x] GPT Audio Mini/Audio routes defined (needs OR credits)

### Modular Architecture
- [x] `echo_node/agent_profiles.py` — 8 agents (HTTP + CLI), unified interface
- [x] `SmartRouter.classify()` — keyword-based query classification
- [x] CostTracker — live dollar tracking for paid routes
- [x] `voice_wizard.py` — interactive test harness for all agents

### Ollama/GPU Fixes
- [x] Ollama CPU-only systemd override (removed — back on GPU)
- [x] Systemd override for Hermes gateway env vars

---

## ⏳ IN PROGRESS

### Smart Router Refinements
- [ ] Classification is keyword-based — misses context ("can you code this?" vs "write code")
- [ ] No confidence scoring — first match wins regardless of quality
- [ ] No way to override routing by voice ("use Hermes for this")

### Cost Tracking
- [ ] Cost displayed after each call but not persisted across sessions
- [ ] No cost alerts/warnings when approaching budget
- [ ] No per-agent cost breakdown in a single view

---

## 📋 REMAINING TASKS

### Priority 1: Smart Router Improvements
- [ ] **LLM-based classification**: Use a tiny local model (or free API call) to classify intent instead of keywords
- [ ] **Confidence thresholds**: Route to fallback if confidence < 0.6
- [ ] **Voice override**: "use Hermes" in query forces route to hermes agent
- [ ] **Session-aware routing**: Remember last agent used, prefer it for follow-ups

### Priority 2: Session Management
- [ ] **Persistent agent sessions**: Each agent (Claude, Pi, Codex) gets a tmux session managed by voice
- [ ] **Session resume**: "continue my Claude session" re-attaches to running agent
- [ ] **Headless execution**: Agents run in background tmux panes, voice pushes commands
- [ ] **Unified session list**: `show sessions` voice command lists all active agent sessions

### Priority 3: Paid Model Integration (OR Credits)
- [ ] **Test gpt-audio-mini** ($0.14/hr) once credits land — native audio in/out
- [ ] **Test gpt-audio** ($0.56/hr) — premium voice quality
- [ ] **Cost cap**: Auto-switch to free model if session cost exceeds $X
- [ ] **Daily budget**: Track spend across sessions, alert at 80% of daily cap

### Priority 4: CLI Agent Integration
- [ ] **Claude Code (`xx cip`)**: Test non-interactive `-p` flag works for voice
- [ ] **Pi (`xx pip`)**: Test `--print` mode returns quickly
- [ ] **Codex (`xx xip`)**: Test non-interactive mode
- [ ] **Error handling**: Timeout/dead sessions killed and restarted automatically

### Priority 5: Gemini / Anthropic Keys
- [ ] **Renew Gemini API key** — current key is expired, $20 Gemini plan exists
- [ ] **Fix Anthropic key** — "invalid x-api-key", $20 Anthropic plan exists
- [ ] **Add Gemini 2.5 Flash route** ($0.16/hr, native audio I/O)
- [ ] **Add Claude Sonnet/Opus route** (coding, best reasoning)

### Priority 6: Testing & Polish
- [ ] **Warmup timing**: First call to each agent is slow (model load) — should warm at startup
- [ ] **dots.tts VRAM sharing**: If GPU needed for STT, swap TTS to Kokoro temporarily
- [ ] **Config validation**: `config.yaml` checked for missing keys before runtime
- [ ] **Graceful degradation**: If Hermes is down, fall through to direct OpenRouter
- [ ] **Latency dashboard**: Real-time display of each pipeline stage timing

### Priority 7: Long-term
- [ ] **4-bit dots.tts**: Manual quantization of the Qwen2.5 backbone via bitsandbytes
- [ ] **Local LLM**: When no network available, fallback to llama.cpp or similar
- [ ] **Wake word training**: Custom wake word (user's voice) via OpenWakeWord fine-tuning
- [ ] **Voice cloning**: dots.tts reference audio for personalized TTS voice

---

## Architecture Summary

```
voice_wizard.py (test harness)
       │
echo_node/agent_profiles.py (agent interface + router)
       │
assistant_v2.py (Echo-Node runtime)
       │
       ├── STT: faster-whisper (CPU, 0.35s)
       ├── VAD: Silero
       ├── Wake: OpenWakeWord
       ├── Router: SmartRouter.classify()
       │       ├── "tool" → Hermes API :8642
       │       ├── "code" → Claude/Codex CLI
       │       ├── "complex" → Nemotron/OC Zen
       │       └── "short" → Fast/OpenRouter
       └── TTS: dots.tts (GPU, SOTA) / Kokoro (CPU fallback)
```

**8 agents. 2 STT backends. 3 TTS backends. All swappable. All can delegate to Hermes.**
