# Echo-Node Voice Agent — Bugbear Scratchpad

> **Project:** Echo-Node (Voice AI Interface)
> **Cycle:** 1
> **Date:** 2026-03-29
> **Source folder:** `~/code/buttplug/voice-agent/`

---

## Phase 1: Inventory & Triage

### Existing Infrastructure Check

**Workspace scan result:** No existing voice-agent codebase found. The `voice-agent/` folder contains ONLY planning documents — no `package.json`, no `src/`, no Python files, no config. This is a **greenfield project**. The "stitch, don't rebuild" constraint applies to the COMPONENT level (use existing libraries), not the project level.

**Related infrastructure:** User has `~/code/agents/` with 94 skills, `sync.sh`, and `skillshare` — but these are for agent skill management, not voice. No overlap.

### File Inventory

| # | File | Size | Source Agent | Type | Verdict | Unique? |
|---|------|------|-------------|------|---------|---------|
| 1 | `claude-plan.md` | 15KB | Claude (Opus 4) | Structured plan | ✅ Useful — sherpa-onnx + TalkingHead pivot | YES |
| 2 | `kimi-trans.md` | 13KB | Kimi (k2) | Tiered plan | ✅ **BEST for modularity** — flexible provider system | YES |
| 3 | `kimi-plan.md` | 47KB | Kimi (k2) | 5-agent synthesis | ✅ Useful — unified architecture + config.yaml | YES |
| 4 | `prd-audit.md` | 18KB | Claude (Opus 4, "Sliither") | Audit/gap analysis | ✅ **BEST for corrections** — most current TTS, identifies critical gaps | YES |
| 5 | `transcript.md` | 63KB | Multiple (Sliither audit + Agent Zero corrections) | Conversation log | ✅ Useful — contains Agent Zero corrections and pipeline critique | PARTIAL |
| 6 | `transcrupt2.md` | 36KB | Kimi (k2) | Paste dump | ❌ **DUPLICATE** of kimi-plan.md (open-source revision section) | DISCARD |
| 7 | `transcript3.md` | 56KB | Kimi (k2) | Paste dump | ❌ **DUPLICATE** of kimi-plan.md + z-transcript.md | DISCARD |
| 8 | `z-transcript.md` | 107KB | Gemini 3 Flash | Full conversation | ⚠️ Mostly duplicate content, but contains the **origin statement** | ORIGIN ONLY |

**Duplicates discarded:** Files 6, 7, 8 are near-identical copies of content in files 2-5. Only z-transcript.md is consulted for the original user prompt (lines 8-49, 204-207).

**Working with 5 unique sources:** claude-plan, kimi-trans, kimi-plan, prd-audit, transcript

### Per-File Notes

#### 1. claude-plan.md — "The Sherpa Pivot"
- **Key contributions:**
  - Recommends `sherpa-onnx` as unified STT runtime (streaming, all-in-one)
  - Identifies `TalkingHead` (met4citizen) as production-proven avatar solution
  - Recommends `Kokoro-82M` v1.0 with phoneme timing data
  - Provides concrete VRAM budget for RTX 4050 (6GB)
- **Red flags:**
  - Some import paths are approximate (not verified against actual package APIs)
  - Proposes `Kokoro v1.0` but doesn't mention Chatterbox/Orpheus alternatives

#### 2. kimi-trans.md — "The Modular Blueprint"
- **Key contributions:**
  - Best provider interface design: abstract `STTProvider`, `TTSProvider`, `WakeWordProvider` classes
  - YAML-based model switching (hot-swap without code changes)
  - 3-tier implementation: Tier 1 (CLI-only), Tier 2 (+Web UI), Tier 3 (+avatar+integrations)
  - Proposes `sherpa-onnx` as unified runtime (convergent with claude-plan)
- **Red flags:**
  - Slightly dated TTS list (Kokoro + Piper + Coqui — misses Chatterbox/Orpheus)

#### 3. kimi-plan.md — "The Synthesis PRD"
- **Key contributions:**
  - 5-model synthesis with explicit change tracking (what was kept/discarded from each)
  - Unified 5-state machine: DORMANT → TRIGGERED → LISTENING → PROCESSING → SPEAKING
  - config.yaml example covering ALL components (wake word, VAD, STT, TTS, LLM, integrations, UI)
  - Frame system with 5 themes (none, minimal, cyberpunk, retro-terminal, glassmorphism)
  - Hermes Bot + OpenClaw integration skeleton code
  - Headless mode design
- **Red flags:**
  - Uses `export let` (Svelte 4 pattern, should be `$props()` for Svelte 5)
  - Uses `FastAPI` for Python worker (unnecessary; pure WebSocket is lighter)
  - Hermes integration uses HTTP webhooks instead of WebSocket channel registration
  - OpenClaw integration misunderstands the actual API (capability registration doesn't match current OpenClaw)

#### 4. prd-audit.md — "The Truth Bomb" ⭐
- **Key contributions:**
  - **TalkingHead** identified as solving 80% of avatar requirements out-of-box (MIT, 1k+ stars)
  - **TalkMateAI** (TalkingHead + Kokoro + WebSocket) = the closest existing implementation
  - Updated TTS landscape: **Chatterbox-Turbo** (sub-200ms, beats ElevenLabs), **Orpheus TTS** (emotion control, 25-50ms streaming)
  - Critical gaps identified: echo cancellation, streaming TTS from LLM, wake word false positive handling, MCP integration, PipeWire audio sharing
  - Correct Hermes integration: register as channel (WebSocket), not webhooks
  - Correct OpenClaw integration: create as skill file, not capability endpoint
  - Hardware reality check: RTX 4050 = 6GB VRAM, Intel Arc = CPU-only or OpenVINO
- **Red flags:** None — this is the most accurate and current document

#### 5. transcript.md — "The Corrections Layer"
- **Key contributions:**
  - Documents Agent Zero's implementation attempt and its 6 critical failures
  - Real import paths: `from kokoro import KPipeline`, NOT `from kokoro import KokoroTTS`
  - Streaming TTS pattern: sentence-boundary chunking for parallel synthesis
  - Echo cancellation approaches: mute mic (MVP) → SpeexDSP AEC (production)
  - WSL2 audio: PipeWire via WSLg (Fedora 43+), PulseAudio forwarding for older setups
- **Red flags:**
  - Contains lots of paste-dump noise around the useful content

---

## Phase 2: Intent Extraction

### Origin Statement (from z-transcript.md, lines 8-49)

> "What I want is to trigger the app with a wake word or keyboard trigger; and have something like Siri, but with agnostic model selection; and ideally a configuration enabling a visual representation that appears to 'talk' by rotating the mouth animation; and moves and does random stuff while in 'listening' mode. I want to have the voice transcription able to use whisper.cpp (with accelerated GPU options available) and parakeet v3/v2. For the voice TTS again; variety is the spice of life."

### Intent Evolution

| Stage | File | Change |
|-------|------|--------|
| 1. Initial | z-transcript | Siri-like assistant, wake word, animated avatar, modular STT/TTS |
| 2. Expanded | kimi-plan | Added: open-source only, Hermes/OpenClaw integration, headless mode, frames |
| 3. Corrected | prd-audit | Shifted: Use TalkingHead library (don't rebuild avatar), updated TTS picks, fix integration patterns |
| 4. Refined | transcript | Added: streaming TTS, echo cancellation, correct API paths, VRAM constraints |

### Immutable Constraints (Never Changed)

1. **Open-source only** — all components must be OSS (with API-key override for cloud LLMs)
2. **Tech stack** — Svelte 5 + Bun + Hono gateway + Python audio worker
3. **Hardware** — RTX 4050 (6GB VRAM) on Fedora 43/WSL2, also Intel Arc (CPU-only)
4. **Modularity** — every pipeline component swappable via config, no hardcoded providers
5. **Dual mode** — Web UI (avatar) + CLI/headless (no screen)
6. **Agent integration** — must work with Hermes Agent and OpenClaw
7. **Platform** — Linux/macOS primary, Windows via WSL2

### User Intent Statement

> A modular, open-source voice AI interface ("Echo-Node") that provides a Siri-like always-on voice assistant with wake word activation, animated 3D avatar with lip-sync, and pluggable STT/TTS/LLM backends — all configurable via YAML without code changes. The system operates in dual mode: Web UI with avatar frames OR headless CLI. It integrates as a voice channel for Hermes Agent and as a skill for OpenClaw. Primary hardware is RTX 4050 (6GB VRAM) on Fedora 43, with Intel Arc CPU-only fallback. The architecture is Svelte 5 frontend + Bun/Hono gateway + Python audio worker, prioritizing existing libraries (TalkingHead, sherpa-onnx) over building from scratch.

---

## Phase 3: Idea Harvest

### Synthesis Matrix

| Component | claude-plan | kimi-trans | kimi-plan | prd-audit | transcript | **Verdict** |
|-----------|-------------|------------|-----------|-----------|------------|-------------|
| **STT** | sherpa-onnx (primary) | sherpa-onnx (unified) | whisper.cpp + alternatives | sherpa-onnx (promoted) | sherpa-onnx | ✅ **sherpa-onnx** primary, faster-whisper fallback |
| **TTS** | Kokoro-82M v1.0 | Kokoro + Piper | Kokoro + GPT-SoVITS | Chatterbox-Turbo + Orpheus + Kokoro | Real Kokoro import paths | ✅ **Kokoro-82M** (edge), **Chatterbox-Turbo** (real-time), **Orpheus** (quality) |
| **Wake Word** | OpenWakeWord + sherpa KWS | OpenWakeWord | OpenWakeWord + livekit-wakeword | OpenWakeWord | OpenWakeWord | ✅ **OpenWakeWord** (all agree) |
| **VAD** | sherpa-onnx VAD | Silero-VAD | Silero-VAD | WebRTC VAD mention | Silero-VAD | ✅ **Silero-VAD** (consensus) or sherpa-onnx built-in |
| **Avatar** | TalkingHead | @pixiv/three-vrm | @pixiv/three-vrm | ⭐ **TalkingHead** (proven) | TalkingHead | ✅ **TalkingHead** (saves weeks of work) |
| **Lip Sync** | TalkingHead built-in | Amplitude-based | Rhubarb + amplitude | TalkingHead built-in (real-time) | — | ✅ **TalkingHead built-in** (no external engine) |
| **Architecture** | Bun+Hono + Python | Bun+Hono + Python | Bun+Hono + Python (FastAPI) | Bun+Hono + Python (pure WS) | Drop FastAPI, use websockets only | ✅ **Bun/Hono gateway + Python pure WebSocket worker** |
| **State Machine** | 5 states | 5 states | 5 states | Single owner (Python) | — | ✅ **5 states, Python owns, events to gateway** |
| **Hermes Integration** | WebSocket channel | — | HTTP webhook | ⭐ WebSocket channel (correct) | Webhook is wrong | ✅ **Register as Hermes channel via WebSocket** |

### Reinforced Ideas (High Confidence — 3+ sources agree)

1. **OpenWakeWord** — universal consensus
2. **Bun + Hono gateway + Python audio worker** — all sources agree on split architecture
3. **sherpa-onnx as unified STT runtime** — claude-plan, kimi-trans, prd-audit
4. **Kokoro-82M for TTS** — all sources include it (though prd-audit properly tiers it)
5. **5-state machine** (DORMANT → TRIGGERED → LISTENING → PROCESSING → SPEAKING)
6. **YAML config for hot-swapping** — kimi-trans, kimi-plan
7. **Headless mode** — kimi-plan, prd-audit
8. **Frame system** — kimi-plan (5 themes)

### Unique Good Ideas (Single Source)

| Idea | Source | Value |
|------|--------|-------|
| TalkingHead as complete avatar solution | prd-audit | ⭐ Saves weeks of Three.js/VRM work |
| Chatterbox-Turbo as real-time TTS | prd-audit | Sub-200ms, beats ElevenLabs in blind tests |
| Orpheus TTS for emotion control | prd-audit | Human-level emotion, 25-50ms streaming |
| Streaming TTS from LLM sentence boundaries | transcript | Essential for sub-500ms perceived latency |
| Echo cancellation (3 tiers) | transcript | Critical missing piece |
| State machine lives in Python worker only | prd-audit | Prevents race conditions |
| MCP integration for tool use | prd-audit | Enables voice-controlled tools |
| PipeWire audio source sharing | prd-audit | Linux multi-app mic access |
| Provider interface pattern | kimi-trans | Cleanest abstraction for swappability |
| config.yaml with full example | kimi-plan | Best reference for configuration schema |

### Contradictions Resolved

| # | Contradiction | Source A | Source B | Resolution |
|---|-------------|---------|---------|------------|
| 1 | Avatar: build custom VRM vs use TalkingHead | kimi-plan (VRM from scratch) | prd-audit (TalkingHead) | **Use TalkingHead** — proven solution, MIT, handles lip-sync + idle animations |
| 2 | Python worker: FastAPI HTTP vs pure WebSocket | kimi-plan (FastAPI) | prd-audit/transcript (websockets lib) | **Pure WebSocket** — gateway already handles HTTP, don't duplicate |
| 3 | Hermes: HTTP webhook vs WebSocket channel | kimi-plan (webhook) | prd-audit (channel registration) | **WebSocket channel** — matches how Hermes v0.3.0 actually works |
| 4 | State machine: split across gateway+worker vs single owner | kimi-plan (dual state) | prd-audit (Python owns) | **Python owns state** — audio worker drives transitions, emits events |
| 5 | TTS tier: Kokoro-only vs tiered selection | most sources (Kokoro default) | prd-audit (3-tier) | **3-tier**: Kokoro (edge), Chatterbox-Turbo (real-time), Orpheus (quality) |
| 6 | STT: whisper.cpp primary vs sherpa-onnx primary | kimi-plan (whisper.cpp) | claude-plan/prd-audit (sherpa-onnx) | **sherpa-onnx** — streaming, all-in-one, better for real-time assistant |

---

## Phase 4: Ground Truth Research

### Existing Projects (Don't Rebuild)

| Project | What It Solves | Use How |
|---------|---------------|---------|
| **TalkingHead** (met4citizen) | VRM avatar + lip-sync + idle animations + eye tracking | **Use as-is** for avatar system |
| **TalkMateAI** (kiranbaby14) | TalkingHead + Kokoro TTS + WebSocket streaming | **Study as reference** for integration pattern |
| **ollama-STT-TTS** (sancliffe) | Complete headless voice pipeline (OWW + WebRTC VAD + faster-whisper + Ollama + Piper) | **Study for headless mode** architecture |
| **voice-chat-ai** (bigsk1) | Full web UI, 60+ characters, multiple providers | **Study for provider switching** UI pattern |

### TTS Landscape (March 2026 — corrected)

| Model | Params | Latency | Quality | License | Use For |
|-------|--------|---------|---------|---------|---------|
| Kokoro-82M | 82M | <0.3s | Good | MIT | Edge/lightweight, default |
| Chatterbox-Turbo | 350M | <200ms | Excellent (beats ElevenLabs) | MIT | Real-time conversational |
| Orpheus TTS | 3B/1B/400M/150M | 25-50ms streaming | Human-level emotion | Apache 2.0 | Quality tier (emotion) |
| Piper | Various | Very fast | Good | MIT | Fallback, Raspberry Pi |
| ~~Coqui TTS~~ | — | — | — | — | ❌ **DEAD** (company shut down 2023) |
| ~~GPT-SoVITS~~ | — | — | — | — | ❌ **DEPRIORITIZED** (bad real-time performance) |

### Hardware VRAM Budget (RTX 4050, 6GB)

| Component | VRAM | Model |
|-----------|------|-------|
| STT | ~0.5GB | sherpa-onnx (base model) |
| TTS | ~0.3GB | Kokoro-82M (ONNX) |
| LLM (Ollama) | ~4-5GB | 7B 4-bit quantized |
| **Total** | **~5-6GB** | ✅ Fits |

> ⚠️ Orpheus 3B will NOT fit alongside the LLM. Use Orpheus 150M/400M variant, or run Orpheus only when LLM is not in VRAM.

### Gap Analysis

| Need | Existing Solution | Build? |
|------|-----------------|--------|
| VRM avatar + lip-sync | TalkingHead | ❌ Use as-is |
| STT (streaming) | sherpa-onnx | ❌ Use as-is |
| TTS (lightweight) | Kokoro-82M | ❌ Use as-is |
| Wake word | OpenWakeWord | ❌ Use as-is |
| VAD | Silero-VAD / sherpa-onnx | ❌ Use as-is |
| Bun/Hono gateway | — | ✅ Build (glue code) |
| Python audio worker | — | ✅ Build (orchestration) |
| Svelte 5 frontend | — | ✅ Build (UI shell) |
| Provider abstraction | — | ✅ Build (interfaces) |
| Config system (YAML) | — | ✅ Build (schema) |
| Hermes channel adapter | — | ✅ Build (WebSocket) |
| OpenClaw skill adapter | — | ✅ Build (skill file) |
| Echo cancellation | SpeexDSP | ✅ Integrate |
| Streaming TTS | — | ✅ Build (sentence chunking) |
| Frame system | — | ✅ Build (CSS themes) |
