# Echo-Node v2 — Implementation Status

## ✅ COMPLETED (Live)

### Core Pipeline
- [x] Phase-4 modularization completed: `assistant_v2.py` entry point imports from `echo_node/components/` + `echo_node/pipeline/` (16 classes extracted from the old monolith; `validate_config` enforced, `_GOTIT_WAV` defined, dead `@dataclass` decorator removed)
- [x] Parakeet TDT v3 0.6B STT (onnx-asr, INT8; v2 auto-fallback) — faster-whisper still available
- [x] dots.tts TTS (GPU, SOTA quality, ~2s gen)
- [x] Kokoro TTS fallback (CPU, faster for short responses)
- [x] OpenWakeWord VAD + barge-in support (was mislabeled "Silero VAD"; class renamed, alias kept)
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

### Phase A — Pluggable Slots + Provider Registry (ROADMAP.md)
- [x] `echo_node/slots/` package: SlotType enum (8 slots), Capability dataclass, per-slot ABCs mirroring existing call patterns
- [x] `echo_node/slots/registry.py`: explicit in-code registration, `working(slot)` dropdown source, `validate_all()` report; experimental opt-in via `ECHO_INCLUDE_EXPERIMENTAL`
- [x] `echo_node/slots/validation.py`: graceful probes (imports, binaries, model files, short-timeout HTTP) — never downloads, never raises
- [x] All existing components migrated as first-party providers with zero behavior change: faster-whisper/parakeet/onnx-asr (STT), kokoro/dots/cosyvoice3[exp]/espeak-ng (TTS), all 8 backends incl. gemini_live/openai_realtime[exp], openwakeword (VAD + wake), alsa/sounddevice (audio I/O), vad_gated (barge-in, extracted verbatim from InterruptibleSpeaker), rhubarb + musetalk[exp] (avatar)
- [x] `validate_config()` and `InterruptibleSpeaker`/`Assistant` dispatch now resolve through the registry; unknown names keep historical fallbacks (STT→parakeet, TTS→espeak-ng, backend→hermes)
- [x] Settings dropdowns read from registry: avatar popup STT/TTS combos, `BACKEND_OPTIONS`, incarnations chooser (`backend.provider`/`tts.provider`/`stt.model` regenerated at load, YAML kept as fallback)
- [x] Conformance suite `echo_node/tests/test_phase_a.py`: 93 checks pass on bare VM (selection equivalence, ABC conformance, experimental exclusion, no config key renamed, graceful validation)
- [ ] Real-hardware validation pass on Aaron's machine (GPU/audio/models) — the true gate for Phase A

### Phase B — Subprocess Adapters (ROADMAP.md)
- [x] `echo_node/adapters/protocol.py`: shared JSON-RPC 2.0 framing, child main loop (`run_adapter`), PCM/wav helpers; importable without the echo_node package
- [x] `echo_node/adapters/subprocess_adapter.py`: host with lazy spawn, initialize handshake + version check, per-call timeouts (`AdapterTimeout`), transparent restart-on-crash (`max_restarts` → `AdapterCrashed`), kill-on-idle reaping, malformed child lines logged-and-ignored, stderr drained; per-slot classes for stt/tts/vad/wake_word/agent_backend (`chat` method)
- [x] `echo_node/adapters/__init__.py`: `register_external_providers()` — config-schema validation, `builtin:` allowlist resolution (traversal-proof), name-collision/unknown-slot startup errors; `ProviderInfo.external` flag
- [x] Three executable reference adapters: `stt_whispercpp.py` (wraps whisper.cpp CLI), `tts_piper.py` (wraps Piper binary + voice model), `stt_reference.py` (faster-whisper shim, never downloads models) — all report missing binaries/models honestly
- [x] Startup wiring in `assistant_v2.py` (`register_external_providers` after `load_config`, before `validate_config`); config file is the trust boundary — no executable paths in any settings UI
- [x] Dropdown marking: validated externals get " (external)" suffix in STT/TTS combos (label/userData split, config keys untouched) and `BACKEND_OPTIONS`
- [x] `echo_node/adapters/PROTOCOL.md` (protocol spec + trust model); `config.example.yaml` `external_providers:` commented examples
- [x] Conformance suite `echo_node/tests/test_phase_b.py`: 37 checks pass on bare VM (fake adapter modes echo/hang/crash-once/crash-always/garbage; handshake, round-trips, timeout, restart, exhaustion, idle-reap, traversal rejection, schema errors, honest self-probes)
- [ ] Real-hardware validation: run a whisper.cpp or Piper adapter end-to-end on Aaron's machine — the true gate for Phase B

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
wake word (OpenWakeWord) → VAD (OpenWakeWord) → STT (Parakeet v3)
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
  InterruptibleSpeaker → dots.tts (GPU) / CosyVoice 3 (GPU, experimental) / Kokoro (CPU) / espeak-ng
       ↓
  Avatar (async Rhubarb lip-sync → PyQt6 sidecar)
```

## Phase C (e-f)

Implemented 2026-10-01 (branch muse/polish-pass, local only).

### e. STT A/B test harness — `v2/tools/stt_ab.py`
- CLI: `python3 tools/stt_ab.py --a parakeet --b faster-whisper [--c onnx-asr] file1.wav [file2.wav ...] [--out report.json] [--csv report.csv]`; `--list` prints available STT providers. Executable bit set.
- Loads WAVs with stdlib `wave`; rejects anything that isn't 16 kHz mono PCM16 with a clear `ValueError` message (also catches `EOFError`, which `wave.open` raises on non-RIFF junk).
- Providers come from `get_registry().get(SlotType.STT, name)`; construct/load/transcribe failures are recorded as errors in the report, never crash the harness.
- JSON report: per-provider class + error, per-file transcripts with `latency_s` + error, per-file `winner` (lowest latency among successful transcribers, else null). Optional CSV: `file,provider,latency_s,transcript,error`.
- Defaults unchanged: provider selection and default STT provider untouched.
- Verified on VM: `--list` works; providers honestly report `construct/load failed` (no onnx_asr/faster_whisper modules here); corrupt WAV → `error: ... not a readable WAV file`, exit 2.

### f. llama-swap as local model router — `LlamaSwapBackend`
- New `AgentBackend` in `v2/echo_node/backends.py`, REGISTRY key `"llama-swap"`; follows the existing backend pattern exactly (`__init__(config)`, `is_available()`, `chat(text, system)`, `capabilities()`, `validate()` classmethod).
- Talks to llama-swap's OpenAI-compatible endpoint: `POST {base_url}/v1/chat/completions` with the configured `model`; reads `llama_swap.base_url` (default `http://127.0.0.1:8080`) from the new `llama_swap:` config section (added to `config.example.yaml` — new keys only, nothing renamed).
- `validate()`: `GET {base_url}/v1/models` with 5s timeout; ok when reachable, honest missing-result on connection refused/timeout, never raises.
- Registered in `backends.REGISTRY` and `EXPERIMENTAL_BACKENDS` (gated behind `ECHO_INCLUDE_EXPERIMENTAL=1` in settings dropdowns via the slot registry loop); needs a running llama-swap server, not validated on target hardware yet.
- Verified on VM: validate() returns `ok: False` with "not reachable" against nothing listening on 127.0.0.1:8080; fake-server tests prove the URL is built as `{base}/v1/models` and chat posts to `{base}/v1/chat/completions`.

### Tests (no GPU/audio/network needed)
- `v2/echo_node/tests/test_stt_ab.py` — 17 tests with stub STT providers: arg parsing, WAV acceptance/rejection (16k/mono/PCM16, EOFError junk), report structure, winner selection, error recording without crash (broken construct, broken transcribe, unknown provider), CSV writing, `main()` end-to-end.
- `v2/echo_node/tests/test_llamaswap.py` — 12 tests with a fake `http.server` in a thread: validator ok when up, honest False on connection refused, URL-shape assertion on the recorded request path, chat payload/URL building, registration in both registries + experimental marking.
- Results: 29/29 new tests pass; `test_phase_a.py` and `test_phase_b.py` conformance suites green (Phase A expected experimental set updated for llama-swap plus the concurrent Phase C(a–d) worker's providers: silero, qwen3-tts, voxcpn, aec-webrtc, musetalk-livetalking).
- `python3 -m compileall echo_node tools` clean. Not committed/pushed (parent handles that).

---

## Phase C (a–d) — substitution providers (2026-10-01)

Built by the Phase C(a–d) worker; all experimental, hardware validation pending.
Conformance: `v2/echo_node/tests/test_phase_c.py` — 40/40 pass on a bare VM;
`test_phase_a.py` / `test_phase_b.py` stay green. Not committed/pushed (parent handles that).

### Done
- **a. Silero v6 VAD** — `echo_node/components/vad.py::SileroVAD`, registry key
  `vad/silero`. Wraps `silero-vad` 6.x (`load_silero_vad(onnx=True)`, 512-sample
  windows, max window probability + RMS floor). Validator probes module presence
  only — never loads (first load downloads weights). Old `SileroVad` alias still
  points at OpenWakeWordVad for historical config compat.
- **b. Echo cancellation** — `echo_node/components/aec.py::AecAudioIO`, registry key
  `audio_io/aec-webrtc`. WebRTC AEC3 via `pywebrtc-audio` (wheels, no build
  toolchain). Wraps `MicStream` capture; far-end reference via `feed_far_end()`.
  Honest validator; docstring states full-duplex AEC needs hardware testing.
- **c. TTS tiers** — `Qwen3TTS` (`tts/qwen3-tts`, `qwen_tts.Qwen3TTSModel`,
  streaming) and `VoxCPMTTS` (`tts/voxcpn`, `voxcpm.VoxCPM`) in
  `echo_node/components/tts.py`. Constructor presence-checks, lazy model load,
  CUDA-required validators that never download. Exact synthesis kwargs marked
  unverified (no GPU on this VM). VoxCPM 0.5B HF id (`openbmb/VoxCPM`) is a guess;
  override via `model_id`.
- **d. LiveTalking harness** — `avatar_video/livetalking_musetalk.py::LiveTalkingMuseTalk`,
  registry key `avatar/musetalk-livetalking`. Implements `preload/play/stop` around the
  MuseTalk prototype. Heavy deps imported lazily; lifecycle safe without them.
- Incidental fix: added no-op `load()` to `EspeakTTS` — the Phase-A ABC migration left
  it out, making the class abstract and breaking `create_tts()`'s historical
  espeak-ng fallback (TypeError on any fallback path).
- Config examples added (commented) to `v2/config.example.yaml`: `vad.provider: silero`,
  `tts` qwen3-tts/voxcpn blocks, `audio` aec-webrtc note, `avatar` musetalk-livetalking.

### Open / needs Aaron's hardware
- [ ] Silero v6: verify windowing + thresholds on real mic audio (16% error reduction claim).
- [ ] AEC3: needs mic + speakers + a room. `feed_far_end()` is now wired
  (orchestrator → `InterruptibleSpeaker.far_end_callback` when `audio_io`
  is `aec-webrtc`); validate echo removal on real hardware.
- [ ] Qwen3-TTS 0.6B: verify quantized path fits 6GB VRAM; verify `generate_custom_voice`
  kwargs and 97ms first-packet claim; test Base voice-clone variant.
- [ ] VoxCPM: confirm the 0.5B checkpoint HF id; verify `generate()` kwargs and 16kHz output.
- [ ] LiveTalking: port the real harness (WebRTC, interruption protocol, task tracking);
  wire a real frame sink (Qt avatar window); chunked streaming instead of per-WAV batch.
- [ ] Items e–f of Phase C (STT A/B, llama-swap, wakeword A/B, LivePortrait):
  separate scope — see the sibling worker's TASKS.md entries, not this list.

---

## Phase D — Wyoming TCP adapters (2026-10-01)

Delivered on branch `muse/polish-pass` (uncommitted):

- `v2/echo_node/adapters/wyoming.py` (new): stdlib-only Wyoming TCP
  client — `WyomingAdapter` base (per-call TCP connect with timeout,
  deadline-bounded event send/receive, clean close) +
  `WyomingSTT` / `WyomingTTS` / `WyomingWakeWord` implementing the
  Wyoming event flows (`transcribe`+audio→`transcript`;
  `synthesize`→audio stream→WAV; `detect`+audio→`detection`/
  `not-detected`). Framing and event names verified against the
  upstream wyoming source (OHF-Voice/wyoming main, 2026-10-01).
- Config schema: `external_providers:` entries accept
  `transport: tcp` (default `subprocess`, unchanged); tcp entries take
  `host` (default 127.0.0.1) + `port` (required) and reject
  `command`/`args` with a startup-fatal `ExternalProviderError`.
  Wyoming providers register `external=True` → " (external)" in the
  existing registry-driven dropdowns. No existing config keys renamed;
  defaults unchanged.
- Tests: `v2/echo_node/tests/test_phase_d.py` (new, 35 checks) — fake
  Wyoming TCP servers (threading socketserver) assert framing
  round-trips, STT/TTS/wake round-trips, streaming `transcript-chunk`
  tolerance, refused-connection `validate()` returning honest-missing
  without raising, schema violations raising `ExternalProviderError`,
  and registry registration with `external=True`.
  `test_phase_a.py` / `test_phase_b.py` still green.
- Docs: ROADMAP.md Phase D status, PROTOCOL.md Wyoming transport
  section, commented wyoming examples in `v2/config.example.yaml`.

Honest gaps (the VM could not verify these):
- No real Wyoming server on this machine — round-trips are against
  fake servers only. Run against wyoming-faster-whisper (:10300),
  wyoming-piper (:10200), wyoming-openwakeword (:10400) on real
  hardware; that pass is the real gate.
- The conventional ports are the projects' documented defaults, not
  re-verified against live servers in this session.
- `wyoming` PyPI package was not installed and is intentionally not
  used (stdlib-only client). If a future change adopts it, re-verify
  framing against the pinned version.
- Wyoming `vad` slot not implemented (protocol has no per-chunk VAD
  query); tcp serves stt/tts/wake_word only. Avatar slot and
  capability-intersection UI filtering are still open in Phase D.
- `Detection` carries no confidence score upstream: wake `detect()`
  returns 1.0/0.0 presence flags, not calibrated confidences.
