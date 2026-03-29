---
date: 2026-03-26 14:30:00 PST
ver: 1.0.0
author: Sliither
model: claude-opus-4-6
tags: [voice-ai, prd-audit, echo-node, tts, stt, avatar, open-source, hermes-agent, openclaw, pipeline-review]
---
# Echo-Node PRD Audit: Due Diligence & Gap Analysis

## Understanding

This audit examines the "Echo-Node" PRD (produced by Gemini via multi-agent synthesis) for a fully open-source, hands-free voice AI interface with wake word activation, modular STT/TTS, 3D avatar with lip-sync, and integrations for Hermes Agent and OpenClaw. The analysis identifies outdated recommendations, missed alternatives, architectural risks, and alignment issues with Ice-ninja's established stack and hardware.

---

## 1. Critical Missed Prior Art

The PRD's biggest oversight is failing to identify existing projects that already implement 60-80% of the described pipeline. Building from scratch is unnecessary when these can serve as foundations or reference implementations.

**TalkingHead (met4citizen/TalkingHead)** is a production-proven JavaScript class providing real-time lip-sync with full-body VRM avatars, built-in viseme generation from any TTS audio, idle animations (blinking, breathing, head tracking), and direct integration with Google TTS and OpenAI function calling. MIT licensed, 1k+ stars, 263 commits, featured at the 2025 Cannes AI Film Awards and used in MIT/Harvard research. This single library solves the avatar + lip-sync + idle animation problem the PRD dedicates two full sections to architecting from scratch.

**TalkMateAI (kiranbaby14/TalkMateAI)** combines TalkingHead with Kokoro TTS native timing data for perfect lip-sync, uses pnpm for package management, and includes WebSocket bidirectional audio streaming. It demonstrates the exact architecture Echo-Node proposes but already works.

**ollama-STT-TTS (sancliffe/ollama-STT-TTS)** provides the complete voice pipeline in a single Python script: OpenWakeWord for wake word, WebRTC VAD for silence detection, faster-whisper for STT, Ollama for LLM, and Piper for TTS. Dockerized, configurable via config.ini. This is the headless mode the PRD describes in Section 3.

**voice-chat-ai (bigsk1/voice-chat-ai)** offers a full web UI with 60+ character personalities, supports Ollama/OpenAI/Anthropic/xAI model providers, Kokoro/SparkTTS/ElevenLabs TTS providers, and faster-whisper STT. Already handles the modular provider switching the PRD specifies.

The PRD should have started from one of these as a base rather than designing a greenfield architecture.

---

## 2. TTS Selection: Severely Outdated

The PRD lists Kokoro-82M, GPT-SoVITS, and Coqui TTS as the TTS options. This was already outdated when the document was written, and the landscape has shifted dramatically.

**Models the PRD misses entirely:**

**Orpheus TTS** (Canopy Labs, Apache 2.0) is built on Llama-3b with 100k+ hours training data, supports zero-shot voice cloning, guided emotion control via simple tags, and streaming latency of 25-50ms. Available in 3B/1B/400M/150M parameter variants for deployment flexibility. This is the highest-quality open-source option for emotive, conversational voice output, which is exactly what an always-on assistant needs.

**Chatterbox** (Resemble AI, MIT license) is a 0.5B parameter model that beats ElevenLabs in blind tests at 63.75% preference rate. Chatterbox-Turbo (350M params) reduces diffusion from 10 steps to 1, achieving sub-200ms latency. Chatterbox Multilingual supports 23 languages. Features emotion exaggeration control and paralinguistic tags ([laugh], [cough], [chuckle]). This should be the default recommendation for real-time voice agent use.

**Dia2** (Nari Labs) features streaming architecture that begins synthesizing from the first few tokens, making it ideal for real-time conversational agents. 1B and 2B parameter variants available.

**Qwen3-TTS** (Alibaba, 1.7B params) includes a voice design mode where you describe the voice you want in natural language, supports 10 languages, and offers streaming output.

**F5-TTS** achieves 7x real-time speed (33x with Fast variant) with zero-shot voice cloning under MIT license.

**GPT-SoVITS should be deprioritized.** While it excels at voice cloning, its real-time streaming performance is poor compared to Chatterbox or Orpheus for conversational use cases.

**Coqui TTS is effectively legacy.** The company shut down in late 2023; while the code is still available, active development has ceased. Recommending it alongside actively developed alternatives is misleading.

**Revised TTS tier:**
- Speed-first (real-time agents): Chatterbox-Turbo (350M, 1-step diffusion, sub-200ms)
- Quality-first (expressiveness): Orpheus TTS (3B, human-level emotion, 25-50ms streaming)
- Lightweight/edge: Kokoro-82M (82M, sub-0.3s across all input lengths)
- Voice cloning: Chatterbox Multilingual (23 languages, zero-shot)
- Fallback: Piper (Raspberry Pi capable, broadest language support)

---

## 3. STT Selection: Mostly Sound, One Key Gap

The PRD's STT recommendations (whisper.cpp, faster-whisper, sherpa-onnx, Parakeet v3, FunASR) are reasonable but miss the most important consideration for real-time voice assistants: streaming/incremental transcription.

**whisper.cpp and faster-whisper are batch processors.** They require the complete utterance before transcription begins. For a conversational assistant targeting sub-500ms latency, this adds the entire utterance duration to the pipeline.

**Streaming STT alternatives the PRD should prioritize:**

**sherpa-onnx** (correctly identified but underweighted) is the strongest choice because it provides real-time streaming ASR, VAD, and speaker diarization in a single ONNX runtime. It supports Whisper, Paraformer, and transducer models with C/C++/Python/JS bindings. This should be promoted to the primary recommendation for the voice pipeline.

**Parakeet-TDT v3** supports streaming mode via NVIDIA NIM, which matters for the always-on agent use case. The PRD notes this but doesn't emphasize the streaming capability as the primary reason to select it.

**RealtimeSTT** (dismissed by the PRD as "too specific") is actually a well-maintained Python library that wraps faster-whisper with real-time streaming, automatic silence detection, and wake word integration. For a Python audio worker, this eliminates significant custom code.

**Recommendation:** sherpa-onnx as primary (streaming, all-in-one), faster-whisper as batch fallback, Parakeet v3 for premium accuracy.

---

## 4. Avatar & Lip-Sync: Overengineered Solution

The PRD proposes building a custom @pixiv/three-vrm integration with Rhubarb Lip Sync and amplitude-based visemes. This is reinventing what TalkingHead already provides as a mature, tested library.

**TalkingHead provides:**
- Full VRM model loading and rendering via Three.js
- Built-in viseme generation from any audio source (no external lip-sync engine needed)
- Dynamic bones with built-in physics engine
- Idle animations (blinking, breathing, micro-movements, head tracking)
- AI-controllable movements via function calling
- Mixamo animation support for custom poses
- MIT licensed, browser-native, no server-side rendering required

**The PRD's Rhubarb Lip Sync recommendation is suboptimal.** Rhubarb requires pre-processing (it analyzes audio files, not streams), making it unsuitable for real-time TTS output. TalkingHead's built-in viseme generator works in real-time from audio streams, which is what the pipeline actually needs.

**wawa-lipsync** is another browser-native alternative that provides real-time viseme detection using Web Audio API with no server dependencies, specifically designed for React Three Fiber integration.

**Recommended approach:** Use TalkingHead as-is for the avatar system. It's battle-tested, handles all the idle animation and lip-sync requirements, and eliminates weeks of custom Three.js/VRM integration work.

---

## 5. Architecture: The Bun+Python Split is Correct, But...

The PRD's decision to split between a Bun/Hono gateway and a Python audio worker is architecturally sound. Python's ML ecosystem (ONNX, torch, whisper bindings, OpenWakeWord) is dramatically more mature than equivalent JS bindings. The gateway handles routing, state management, and WebSocket coordination while Python handles the heavy ML inference.

**However, several issues:**

**Inter-process communication is underspecified.** The PRD mentions "Unix Socket / localhost" but doesn't address the audio streaming protocol. Raw PCM over WebSocket is the obvious choice, but the chunk size, sample rate negotiation, and backpressure handling matter enormously for latency. The PRD's skeleton code shows `receive_bytes()` without specifying the frame format, which will cause integration headaches.

**The state machine location is ambiguous.** The PRD places state management in the gateway (TypeScript) but the audio worker (Python) also tracks state. This dual-state architecture will create race conditions. State should live in exactly one place. Given that the audio worker drives the primary transitions (wake word detected, VAD silence, STT complete), the Python worker should own state and emit events to the gateway.

**Docker deployment contradicts the headless use case.** The PRD provides a Dockerfile that exposes the gateway and audio worker as separate containers, but audio device passthrough in Docker is notoriously fragile. For always-on agent deployment on a Raspberry Pi or dedicated machine, a systemd service file pair is more appropriate than Docker.

**Missing: Audio device multiplexing.** If Echo-Node runs as a voice interface for Hermes Agent and simultaneously monitors for wake words, the microphone is exclusively claimed. The PRD doesn't address PulseAudio/PipeWire source sharing, which is essential for Linux deployments where other applications (Home Assistant Assist, for example) might also want microphone access.

---

## 6. Integration Architecture: Hermes Agent & OpenClaw

**Hermes Agent integration is conceptually correct but mechanically wrong.** The PRD proposes a webhook-based integration where Echo-Node POSTs voice commands to Hermes and receives text responses. However, Hermes Agent v0.3.0 (released March 17, 2026) now supports a multi-platform messaging gateway with unified session management, including Home Assistant integration. It already has TTS output support and voice transcription hooks. Rather than building a custom webhook adapter, Echo-Node should register as a Hermes Agent platform/channel, following the same pattern as the Telegram, Discord, and Slack integrations. This gives you session management, memory persistence, and skill execution for free.

The PRD's Hermes webhook code also hardcodes `HERMES_BOT_URL` as if Hermes is a remote service. Hermes Agent runs locally and communicates via its gateway WebSocket at `ws://127.0.0.1:PORT`. The integration should use the Hermes gateway's WebSocket protocol, not HTTP POST webhooks.

**OpenClaw integration is more problematic.** The PRD proposes registering Echo-Node as an OpenClaw "capability" via a REST API, but OpenClaw's actual architecture is a local gateway with channel-based messaging (WhatsApp, Telegram, Discord, etc.) and a skills system. OpenClaw already has "Voice Wake + Talk Mode" built in as of its current release, supporting wake words on macOS/iOS and continuous voice on Android with ElevenLabs and system TTS fallback. The PRD's proposed integration duplicates functionality OpenClaw already provides.

A more productive integration would be creating an OpenClaw skill (a SKILL.md file with associated tooling) that lets OpenClaw delegate voice synthesis and avatar rendering to Echo-Node's TTS/avatar pipeline, rather than trying to make Echo-Node a separate capability endpoint.

**Security note:** OpenClaw has disclosed significant security vulnerabilities (CVE-2026-25253, 512 vulnerabilities found in audit, 41% of marketplace skills containing vulnerabilities). Any integration should use NemoClaw's OpenShell sandboxing if available, and the PRD should address this explicitly.

---

## 7. Hardware Requirements: Misaligned with Ice-ninja's Setup

The PRD specifies minimum 8GB RAM with CUDA GPU. Ice-ninja's primary machines are:
- HP Spectre x360 16 (i7-1360P, Intel Arc A370M, 16GB) -- Intel GPU, not NVIDIA
- Surface Laptop Studio 2 (i7-13800H, RTX 4050, 16GB on Fedora 43)

The Intel Arc A370M on the Spectre won't run CUDA workloads. The PRD should specify SYCL/oneAPI support for Intel GPUs via whisper.cpp's `WHISPER_OPENVINO=1` build flag, or acknowledge that the Spectre will run CPU-only inference.

The RTX 4050 on the Surface has 6GB VRAM. Running Orpheus TTS (3B params) alongside whisper.cpp and an LLM via Ollama will exceed VRAM. The PRD's "Recommended: RTX 3060+ (12GB VRAM)" doesn't match the available hardware.

**Practical configuration for Ice-ninja's hardware:**
- Surface (RTX 4050, 6GB VRAM): Kokoro-82M TTS + faster-whisper (tiny/base model) + Ollama with 4-bit quantized 7B model. Total VRAM ~5-6GB.
- Spectre (Arc A370M): CPU-only or OpenVINO for STT, cloud API for LLM, Kokoro for TTS.

---

## 8. Missing Pipeline Components

**Barge-in / echo cancellation.** The PRD mentions barge-in support (user interrupts AI speech) in the state machine but provides zero implementation guidance. This is one of the hardest problems in duplex voice systems. Without acoustic echo cancellation (AEC), the microphone will pick up the TTS output and create feedback loops. SpeexDSP provides open-source AEC, and WebRTC's audio processing module includes AEC3. Neither is mentioned.

**Audio streaming to TTS.** The PRD doesn't address streaming TTS output. For sub-500ms perceived latency, the TTS engine must begin generating audio from the first sentence of the LLM response while the LLM is still generating subsequent sentences. This requires: (a) sentence-boundary detection on the LLM output stream, (b) parallel TTS synthesis, and (c) audio chunk queuing. Home Assistant solved this with their Piper streaming integration. The PRD's pipeline is strictly sequential: LLM completes, then TTS runs.

**Wake word false positive handling.** OpenWakeWord's false activation rate in noisy environments is a known pain point. The PRD sets a threshold of 0.5 but doesn't implement a confirmation mechanism (brief chime + "yes?" before recording) or custom verifier models that OpenWakeWord v0.3.0+ supports.

**No MCP integration.** Both Hermes Agent and OpenClaw support MCP (Model Context Protocol). The PRD's LLM integration should route through MCP for tool use, not just raw chat completion endpoints. This enables the voice assistant to control Home Assistant devices, browse the web, access files, and use any MCP-compatible tool.

---

## 9. Stack Alignment Issues

The PRD specifies Svelte 5 for the frontend (correct per Ice-ninja's preferences) and Hono/Bun for the gateway (also correct). But the skeleton code has issues:

**The Avatar.svelte component uses deprecated patterns.** It uses `export let` props instead of Svelte 5 runes (`$props()`). The `onMount` lifecycle hook is fine, but the reactive state should use `$state()` and `$derived()`.

**The Python audio worker uses FastAPI but the PRD calls it "Python + FastAPI" in some places and just "Python" in others.** Given that the gateway already handles HTTP/WebSocket routing via Hono, the Python worker should be a pure WebSocket consumer, not a separate HTTP server. A lightweight approach using `websockets` library directly (already in the install list) eliminates the FastAPI dependency and reduces complexity.

**Missing: pnpm.** The PRD uses `bun install` throughout but Ice-ninja's preferred package manager is pnpm. The setup commands should use `pnpm` with Bun as the runtime.

---

## 10. Recommendations Summary

**Do first:** Survey TalkingHead, TalkMateAI, and ollama-STT-TTS as candidate foundations. Forking TalkMateAI and adapting it to Svelte 5 + Hono is likely the fastest path to a working prototype.

**Replace immediately:** Coqui TTS with Chatterbox-Turbo for real-time, Kokoro-82M for lightweight. Add Orpheus TTS as the quality tier. Drop GPT-SoVITS to optional voice cloning add-on.

**Adopt as-is:** TalkingHead library for all avatar + lip-sync + idle animation needs. Stop trying to build this from scratch.

**Fix architecture:** Single state machine in the Python audio worker, events emitted to gateway. Replace HTTP webhooks with WebSocket for Hermes Agent integration. Build OpenClaw integration as a skill, not a capability endpoint.

**Add missing pieces:** Acoustic echo cancellation (SpeexDSP or WebRTC AEC3), streaming TTS from LLM sentence boundaries, MCP tool routing, PipeWire audio source sharing.

**Address hardware:** Add OpenVINO/SYCL paths for Intel Arc GPU. Size model selections to 6GB VRAM budget for RTX 4050.

---

## Verdict

The PRD demonstrates competent synthesis of the open-source voice AI landscape as it existed circa mid-2025, but it's designing a system from first principles when mature implementations already exist. The TTS recommendations are 6-12 months stale (missing Orpheus, Chatterbox, Dia2, Qwen3-TTS), the avatar section reinvents what TalkingHead provides out of the box, and the agent integrations misunderstand how both Hermes Agent and OpenClaw actually work in their current versions. The core architecture (Bun gateway + Python ML worker + Svelte frontend) is sound, but the execution plan needs significant revision before it's worth implementing.