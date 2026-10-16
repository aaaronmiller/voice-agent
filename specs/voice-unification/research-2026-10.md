---
date: 2026-10-16
ver: 1.0.0
author: research synthesis (4 scout agents + direct survey)
tags: [strata, research, voice-unification, component-survey, 2026-10]
---

# Component survey (Oct 2026) — 50+ primary sources

Method: 4 parallel scout agents (STT / TTS / VAD+wake+AEC / dialogue+S2S) plus
direct survey of avatars, transports (LiveKit vs Pipecat vs Wyoming), and
registry/profile/test-matrix patterns. Quarantine rule honored: every entry is
a *candidate with swap criteria*, never a mandate. Existing repo pins get an
explicit CONFIRM / CHALLENGE / REMOVE verdict grounded in 2026 evidence.

## 1. STT — streaming + local (15 sources)

Key sources: sherpa-onnx Zipformer streaming docs + model index + v1.13.x
releases (bundled Moonshine-tiny, Parakeet-TDT-v2/v3, Whisper-tiny, FireRed,
SenseVoice); QNN/quantized-edge commit; NVIDIA ASR NIM docs; Parakeet-TDT
0.6B v2/v3 model cards; NeMo streaming RNN-T discussion; x2q Whisper backend
shootout 2026; GigaGPU serving bench; Pipecat STT benchmark Aug 2026 (1000
clips, TTFS + semantic-WER); pipecat stt-benchmark repo; Cartesia ink-whisper
profile; Deepgram Nova-3 launch/pricing/latency + Flux; AssemblyAI
Universal-3.6/3.5-Pro + Universal-Streaming pricing/benchmarks; Moonshine v2
paper + repo + streaming-tiny HF.

| Slot | Candidate | Latency | Accuracy | License | Offline | Verdict |
|---|---|---|---|---|---|---|
| offline streamer | sherpa-onnx Zipformer transducer | streaming-native | strong | Apache-2.0 | YES | CONFIRM runtime; refresh model zoo |
| offline batch-acc | Parakeet-TDT-0.6B v2 (EN) / v3 (25 EU) | single-pass ≤24min | SOTA batch | open weights (NIM: offline-only) | YES | CONFIRM for batch; NOT a streamer (needs NeMo stateful pipe) |
| offline tiny streamer | Moonshine streaming-tiny 34M (~50ms) / small 123M / medium 245M | 50–258ms | good | MIT | YES | ADD as tiny-streamer candidate |
| GPU server | faster-whisper + large-v3-turbo (~56xRT RTX4070Ti) | best RTF | = quality | MIT (CTranslate2) | YES (self-host) | CONFIRM GPU pick over whisper.cpp |
| hosted accuracy | AssemblyAI Universal-3.6-Pro (~0.8–0.96% sem-WER, ~307ms) | sub-300ms | leader | proprietary $0.45/hr | NO | ADD hosted-accuracy option |
| hosted streaming | Deepgram Nova-3 (~247ms, 1.37–1.62%) / Flux conv. model | sub-300ms | strong | proprietary $0.29–0.39/hr | NO | ADD hosted-streaming option |
| hosted fast | Cartesia ink-whisper (turbo+chunking) / ink-2 (~1.0%) | vendor 66ms / indep. 266ms | mid→strong | proprietary | NO | ADD hosted-fast option |

Swap criteria: TTFS p50/p95 on target hardware, streaming-vs-batch nature,
semantic-WER on agent-like audio, VRAM/RAM, license class, offline flag,
language coverage. Adopt pipecat stt-benchmark as the swap-test rig.

## 2. TTS — streaming/quality/edge (11 slots)

| Slot | Candidate | First-byte | Quality | License | Offline | Verdict |
|---|---|---|---|---|---|---|
| offline default | Kokoro-82M (warmed ~50ms TTFB) | fast | good, 54 voices | Apache-2.0 | YES | CONFIRM default self-host |
| quality challenger | Chatterbox-Turbo 350M (~75ms, stream() API, paralinguistics) | fast | strong + clone | MIT + watermark | YES | ADD challenger; watch VRAM |
| expressive | Orpheus (~180–280ms, emotion tags) | mid | very human | Apache-2.0 | partial (GPU) | ADD expressive option |
| low-power | Piper (CPU 150–250ms, RPi-capable) | mid | flat | GPL-ish | YES | KEEP fallback only |
| clone (open) | Coqui XTTS v2/v3 | <200ms chunk | strong multi clone | CPML (NOT OSI-open) | YES | ADD with license flag |
| clone+SOTA open | CoSyVoice 3 (bi-stream ~150ms) | fast | SOTA zero-shot | Apache-2.0 | YES (GPU) | ADD best open clone/stream combo |
| newest open | DOTS.tts (54–85ms first-packet, WER 0.94–1.3%) | fastest open | SOTA stability | Apache-2.0 | YES (GPU) | ADD; verify maturity/VRAM |
| hosted latency | Cartesia Sonic-3/3.6 (sub-100ms vendor) | fastest | high | proprietary | NO | ADD hosted-latency option |
| hosted quality | ElevenLabs v3 / Flash-Turbo (P50 ~266–323ms, WER 1.4%) | fast | SOTA | proprietary | NO | ADD hosted-quality option |
| runtime harness | Sherpa-ONNX TTS (Matcha/VITS/Kokoro/Kitten/ZipVoice, onProgress chunks) | CPU RTF<<1 | utilitarian | Apache-2.0 | YES | CONFIRM as runtime, refresh voices |
| prototype only | Edge-TTS (unofficial MS scrape) | network-bound | natural online | gray-zone | partial | REMOVE from any production path |

Required TTS interface: synthesize_stream(text) -> PCM chunks + viseme/boundary
events + cancel(); sentence-chunk fallback for non-streamers.

## 3. VAD + wake-word + AEC (12 sources)

- VAD: Silero v5→v6(.2.3) CONFIRM, move pin to v6 (MIT, ~2MB, <1ms/chunk).
  webrtcvad = cheap gate only (F1 0.669 vs 0.738). sherpa ships Silero
  v4/v5/int8 + Ten-VAD (A/B candidate, near-tie 0.985 vs 0.981 AUC).
  Picovoice Cobra = paid-only option. LiveKit silero plugin = CPU default.
- Wake: OpenWakeWord server-side CONFIRM + microWakeWord on-device ADD (ESP32/
  Android, 2025.5 per-model toggles). Wyoming protocol ≥v1.10.x CONFIRM
  (VAD+audio prefs in ASR; satellite FSM states). Porcupine v3 = paid accuracy
  option. Snowboy = REMOVE (dead since 2020, archived).
- AEC/denoise: WebRTC AEC3 CONFIRM default (SpeexDSP demoted to legacy
  fallback). RNNoise = cheap NS only. DeepFilterNet3 ADD as preferred OSS NS
  upgrade. Krisp SDK = premium optional, never default.

## 4. Dialogue backends + realtime S2S (9 slots)

| Backend | Interface | Latency | Cost | Offline | Tools | Verdict |
|---|---|---|---|---|---|---|
| OpenAI Realtime GA | WS + SIP + remote-MCP, 60-min sessions | ~1.1s E2E | $32–64/1M audio | NO | GA function calling | KEEP cloud flagship |
| Gemini Live 2.5/3.x | Live WS bidi PCM, VAD, barge-in, ADK | streaming-low | $0.50–12/1M | NO | search grounding | KEEP cheapest quality + grounding |
| Qwen Omni-Realtime 3.5/3.8 (OSS 2.5-Omni-7b) | WS/WebRTC/AOQ-QUIC, MCP no extra fee | tuned variable-net | token billing | partial (OSS) | session+MCP tools | ADD low-cost/CN-region alt |
| xAI Grok Voice 3.0 | WS full-duplex, ephemeral tokens | sub-second class | $0.08/min | NO | web_search + tools | EVALUATE, not default |
| Groq Whisper-turbo + PlayAI Dialog | OpenAI-compat cascade (216xRTF STT, ~200ms LLM, ~350ms TTS) | fast cascade | $0.04/hr + ~$50/1M | NO | LLM-stage tools | KEEP fastest/cheapest cascade |
| Cartesia Sonic+Ink+Line | WS TTS/STT + Line agent host; self-host opt | ~90ms claimed TTFA | $299/mo scale | self-host opt | hosted LLMs | KEEP for TTS-slot latency |
| Daily/Pipecat framework+Cloud | OSS Python pipelines, WebRTC transport | P99 start <1s, E2E ~1s | ~$0.01/tick + models | self-hostable | any-provider tools | KEEP vendor-neutral orchestrator |
| LiveKit Agents + Inference + SIP | OSS SDK + Cloud, media <250ms | E2E model-dominated | $0.01/min + provider | self-hostable | realtime/cascade tools | KEEP transport/agent runtime |
| Wyoming/HA local | JSONL-over-TCP, satellites | LAN sub-second | $0 self-host | YES (only offline path) | HA intents + Ollama | KEEP offline/must-work-local path |

Repo registry verdicts: gemini-live KEEP, openai-realtime KEEP,
hermes/pi-agent KEEP (local text paths), ADD qwen + groq-cascade +
wyoming-local profiles to the registry.

## 5. Avatars, transports, registry/profile/test patterns (20+ sources)

- Avatars: TalkingHead (met4citizen, MIT, full-body + TTS-timestamp lipsync)
  CONFIRM current pin; Talking Avatar OSS (MIT, audio-only face, 1MB model,
  10KB code) ADD as lightweight alt; talking-head-studio ADD as
  backend-agnostic framework (FaceControl/AgentVisemePayload, GaussianBackend
  roadmap for viseme-less models). Note: Ready Player Me portal changes affect
  RPM pipelines — prefer portable .glb/VRM.
- Transports: LiveKit Agents (turnkey, managed scaling, Apache-2.0 server)
  vs Pipecat (pipeline-first, transport-agnostic, own TURN/SIP) — keep BOTH
  as deployment options behind the transport boundary; Wyoming stays the LAN/
  offline transport. Scenario/voicetest AgentGraph pattern informs the test
  matrix: normalize configs to one IR, run one suite across combos.
- Registry/profile/test patterns: Agent Definition as registry entry;
  persona+scenario matrices as saved profiles; Auto-Generate Graph
  (20–5000 scenarios) + LiveKit Agent Simulations + run_agent_scenario_matrix
  as the test-matrix model; Langfuse-style immutable prompt registry.

## 6. Supersession map (old pin -> current posture)

- whisper.cpp-tiny default -> faster-whisper large-v3-turbo (GPU) /
  sherpa-Zipformer (streaming) / Moonshine-tiny (edge); whisper.cpp stays a
  CoreML/edge fallback only.
- Kokoro-82M default -> CONFIRMED as offline default; challengers
  Chatterbox-Turbo / CoSyVoice3 / DOTS registered, GPU-gated.
- Silero v5 -> v6(.2.3); SpeexDSP AEC -> AEC3 default; RNNoise -> DeepFilterNet3.
- OpenWakeWord-only -> OWW server + microWakeWord on-device.
- Snowboy, Edge-TTS-prod, Piper-as-quality-lead -> REMOVED from production paths.
- Single hardcoded provider -> registry + saved profiles + test matrix (this plan).
