---
date: 2026-08-29
ver: 1.0.0
author: OpenAI GPT-5.6 Sol
tags: [spec-prep, requirements, realtime-voice, desktop, android, openai, gemini, qwen, xai]
status: design-baseline
project: realtime-voice-cockpit
---

# Realtime Voice Cockpit — Requirements

## 0. Document role and spec-prep mapping

This document is the human-facing **what / why / contract** layer for Realtime Voice Cockpit (RVC). It intentionally does not prescribe implementation technology except where a platform or provider boundary is itself a requirement.

The requested delivery surface is two files rather than a full spec-prep tree. To preserve spec-prep-style traceability without inventing extra files:

- `REQ-*` identifies a product requirement.
- `EVAL-*` is the one-to-one acceptance binding for that requirement.
- `design.md` derives implementation decisions from these requirements and references the same IDs.
- A later promotion into a full spec-prep corpus may split human intent, formal specification, context, evaluations, standing, plays, and ledger without renumbering these requirements.
- “Included” means required by this design baseline, not already implemented.
- “Future” means intentionally excluded from the first production milestone but retained as continuity.
- “Rejected” means deliberately not part of the architecture.
- “Unknown” is used only where an external provider does not expose a stable public capability as of the verification date.

This baseline is grounded in provider and platform documentation checked on **2026-08-29**.

---

## 1. Product statement

Realtime Voice Cockpit is a small, persistent, keyboard-and-voice-first application that lets one person use multiple realtime speech-to-speech AI providers and transcription engines through one consistent local interface on:

- native Windows 11;
- native Linux desktops using X11 or Wayland;
- Windows machines where development work is performed inside WSL2, while the Windows host owns audio and desktop integration;
- Android.

The application is not a model host by default. OpenAI Realtime, Gemini Live, Alibaba/Qwen hosted Realtime, and xAI Voice execute in their providers’ infrastructure. The **application, wake-word detection, audio metering, credential storage, local VAD, optional local transcription, UI, post-processing, and session routing run locally**.

A local-only speech pipeline is also required for dictation and shall be designed so a future local conversational pipeline can be added without replacing the UI or audio core.

---

## 2. Current provider baseline

The application shall ship with first-party provider adapters for the following current families, while allowing the exact model string to be changed by configuration.

| Provider | Baseline realtime models | Preferred transport | Authentication baseline |
|---|---|---|---|
| OpenAI | `gpt-realtime-2.1`, `gpt-realtime-2.1-mini` | WebRTC for client realtime; WebSocket supported where appropriate | API key in trusted host; short-lived Realtime client secret for untrusted/mobile clients |
| Google Gemini | `gemini-3.1-flash-live-preview` | Live API bidirectional WebSocket | OAuth 2.0 when configured; API/authorization key fallback; ephemeral Live token for client-safe sessions |
| Alibaba/Qwen | `qwen-audio-3.0-realtime-plus`, `qwen-audio-3.0-realtime-flash`; optional `qwen3.5-omni-*-realtime` family | WebSocket broadly; AOQ temporary-token path where selected; WebRTC where account access permits | API key in trusted host; temporary AOQ token from app server for client-safe sessions |
| xAI | `grok-voice-latest` | WebSocket | API key in trusted host; short-lived client secret for browser/mobile-style clients |
| Generic | user-defined | WebSocket, WebRTC, or OpenAI-compatible HTTP as declared by profile | bearer key, static header set, or externally supplied token |

The provider/model catalog must be data-driven. A provider adapter shall expose a capability record rather than causing the rest of the app to infer behavior from a model-name string.

---

## 3. Existing-software decision

No single verified project found on 2026-08-29 satisfies the complete target.

### RoomKit UI

RoomKit UI is the closest desktop reference and already provides Windows/Linux binaries, OpenAI/Gemini realtime voice, interruption, an animated VU meter, global dictation hotkeys, local sherpa-onnx STT, echo cancellation, denoising, system tray behavior, and local TTS options. Its Python/PySide desktop architecture does not provide the requested one-codebase Android path, and its documented realtime speech-to-speech UI path is centered on OpenAI and Gemini. It also does not provide the requested user-facing realtime pitch/time/EQ preset rack.

**Disposition:** reference implementation and behavior benchmark; do not fork as the product base.

### OpenDex

OpenDex provides a strong voice-first desktop interaction model: wake word or hotkey, follow-up conversations, interruption, customizable interface, and integrated OpenAI Realtime/xAI Voice. Its Electron/React implementation and current provider/feature surface do not solve the complete provider matrix, Android, file-transcription workflow, or audio FX rack.

**Disposition:** reference for compact assistant UX and wake/hotkey behavior.

### OpenWhispr

OpenWhispr is a strong cross-platform dictation/transcription reference with native desktop packaging, global dictation, local Whisper/Parakeet and cloud engines.

**Disposition:** reference for dictation, import/transcription, and desktop text-injection behavior; not the conversational realtime base.

### Decision

**REQ-001 / EVAL-001 — Build a dedicated application.**  
The production architecture shall be a new provider-neutral application rather than a thin skin around one existing project.

**Pass condition:** Windows, Linux, and Android builds share the same product state model and provider contracts, and no runtime dependency on RoomKit UI, OpenDex, or OpenWhispr is required.

---

## 4. Platform requirements

**REQ-002 / EVAL-002 — Native Windows audio host.**  
On Windows, the application shall run as a native Windows process and own microphone capture, speaker playback, tray/card UI, global shortcuts, and text injection.

**Pass condition:** a packaged Windows build can complete realtime conversation, PTT dictation, toggle dictation, and file transcription without WSL.

**REQ-003 / EVAL-003 — WSL2 integration without WSL2 audio dependency.**  
A WSL2 shell shall be able to launch/control the Windows application and request dictation or session actions, but WSL2 shall not be required to capture the microphone or register Windows global shortcuts.

**Pass condition:** a WSL command can invoke the installed Windows app or its local IPC/CLI endpoint while the Windows process remains the audio owner.

**REQ-004 / EVAL-004 — Native Linux support.**  
The application shall support current x86-64 Linux desktops and operate under both X11 and Wayland, with explicit capability fallbacks where a compositor forbids synthetic input.

**Pass condition:** microphone, playback, realtime conversation, local dictation, clipboard output, tray/card, and configurable hotkey behavior work on a supported Wayland desktop and an X11 desktop.

**REQ-005 / EVAL-005 — Android support.**  
The same product shall build as an Android application with the same provider profiles, model selection concepts, session state, audio FX presets, transcription modes, and transcript history model.

**Pass condition:** an Android build can establish at least OpenAI, Gemini, Qwen, and xAI sessions using safe client credentials and can run local wake/VAD functions.

**REQ-006 / EVAL-006 — Platform-specific affordances may differ without fragmenting the product.**  
Desktop may expose global shortcuts and tray windows; Android may expose foreground-service controls, notification actions, Quick Settings integration, headset/media-button controls, and launcher shortcuts.

**Pass condition:** platform differences are implemented behind platform capability interfaces rather than separate application forks.

---

## 5. Core interaction modes

**REQ-007 / EVAL-007 — Hands-free conversation.**  
The user shall be able to start a realtime session and converse without holding a key.

**Pass condition:** after activation, normal user turns and model responses continue until explicit stop, session expiry, fatal error, or configured idle timeout.

**REQ-008 / EVAL-008 — Wake-word activation.**  
Hands-free mode shall optionally remain locally armed behind a configurable wake phrase. Ambient audio shall not be sent to a cloud model before activation solely to implement wake-word detection.

**Pass condition:** network capture demonstrates no cloud audio upload while wake mode is armed but not triggered.

**REQ-009 / EVAL-009 — Barge-in / interruption.**  
When the model is speaking, real user speech shall be able to interrupt playback and cancel or truncate the current model response according to provider capability.

**Pass condition:** sustained user speech interrupts audible model output inside the configured local interruption threshold in ten consecutive controlled tests, without the model’s own speaker output repeatedly self-triggering.

**REQ-010 / EVAL-010 — Push-to-talk conversation.**  
The user shall be able to hold a configurable hotkey/button to send a bounded spoken turn and release it to commit the turn.

**Pass condition:** no microphone frames are submitted outside the held interval except the configured pre-roll/post-roll buffer.

**REQ-011 / EVAL-011 — Manual turn mode.**  
The user shall be able to disable server/local automatic turn detection and explicitly commit a turn.

**Pass condition:** a provider that supports manual commit receives no turn commit until the user action occurs.

**REQ-012 / EVAL-012 — Quick mute.**  
One action shall mute/unmute the upstream microphone without ending the provider session.

**Pass condition:** downstream playback continues while upstream frames stop.

**REQ-013 / EVAL-013 — Stop-response control.**  
The user shall be able to immediately stop current output without ending the session.

**Pass condition:** audio playback stops and the provider cancellation action is issued when supported.

---

## 6. Audio visibility and confidence

**REQ-014 / EVAL-014 — Live microphone level.**  
Whenever microphone capture is active, the UI shall display a live audio representation.

**Pass condition:** the card displays RMS level, peak level, and a clipping indication updated at visually smooth cadence.

**REQ-015 / EVAL-015 — Speech-state visualization.**  
The UI shall visually distinguish silence/noise, detected user speech, committed turn, model thinking/processing, and model speech.

**Pass condition:** the five states are distinguishable without opening logs.

**REQ-016 / EVAL-016 — Pre/post processing visibility.**  
Diagnostics shall allow the user to compare raw microphone level with the processed upstream signal so aggressive noise suppression or gain settings are discoverable.

**Pass condition:** diagnostic mode presents both measurements without recording content by default.

**REQ-017 / EVAL-017 — Device selection.**  
The user shall be able to choose input and output devices independently and remember choices per machine.

**Pass condition:** selected devices survive application restart and gracefully fall back if a device disappears.

**REQ-018 / EVAL-018 — Clipping and silence warnings.**  
The card shall warn when input is persistently clipping or effectively silent.

**Pass condition:** test tones below silence threshold and above clipping threshold produce distinct warnings.

---

## 7. Turn detection, echo control, and wake behavior

**REQ-019 / EVAL-019 — Local VAD layer.**  
A local VAD shall run independently of provider-native VAD for UI state, wake gating, interruption confirmation, and local dictation.

**Pass condition:** local speech state works with networking disabled.

**REQ-020 / EVAL-020 — Provider-native turn modes remain usable.**  
Adapters shall expose provider modes such as server VAD, semantic/smart turn, or manual control when offered.

**Pass condition:** selecting a supported provider turn mode changes the session configuration and is reflected in diagnostics.

**REQ-021 / EVAL-021 — Configurable interruption policy.**  
Interruption shall support at least `immediate`, `confirmed`, `provider-smart`, and `disabled`.

**Pass condition:** each mode changes behavior in deterministic audio fixtures.

**REQ-022 / EVAL-022 — Echo cancellation.**  
Hands-free loudspeaker use shall feed a render reference to an acoustic echo canceller when the platform/provider path does not already provide adequate AEC.

**Pass condition:** a controlled speaker-loop test materially reduces false VAD/barge-in activation relative to AEC disabled.

**REQ-023 / EVAL-023 — Noise suppression and gain control.**  
Noise suppression and automatic gain control shall be individually toggleable and shall not be silently forced on.

**Pass condition:** the effective processing graph is visible in diagnostics and each stage can be bypassed.

**REQ-024 / EVAL-024 — Custom wake phrase.**  
The user shall be able to configure at least one English wake phrase without retraining the entire application.

**Pass condition:** changing the phrase changes local keyword spotting after model/token regeneration or configuration update.

**REQ-025 / EVAL-025 — Wake-word false-trigger controls.**  
Wake sensitivity, refractory interval, and optional “wake then beep” confirmation shall be configurable.

**Pass condition:** values persist and affect fixture results.

---

## 8. Provider and model switching

**REQ-026 / EVAL-026 — Provider selector.**  
The compact card and full settings UI shall allow provider selection.

**Pass condition:** provider change is possible without editing a file.

**REQ-027 / EVAL-027 — Model selector.**  
Each provider profile shall expose known models plus a custom model string.

**Pass condition:** a newly released model can be attempted without application recompilation when its protocol is compatible.

**REQ-028 / EVAL-028 — Capability-driven controls.**  
Unsupported controls shall be disabled or adapted based on provider capability records rather than failing after submission.

**Pass condition:** a provider without runtime voice switching does not expose a misleading live-switch action.

**REQ-029 / EVAL-029 — Session-safe switching.**  
Changing provider/model during an active session shall either perform a supported reconfiguration or deliberately start a new session while preserving a local transcript/context handoff according to policy.

**Pass condition:** no provider connection is left orphaned, and the UI reports whether continuity was carried or reset.

**REQ-030 / EVAL-030 — Configurable endpoints.**  
Every provider profile shall permit override of applicable base HTTP, WebSocket, WebRTC/SDP, token-broker, and compatible API endpoints.

**Pass condition:** integration tests can point every adapter at a local mock server without source changes.

**REQ-031 / EVAL-031 — Custom headers.**  
Profiles shall support a bounded set of user-defined non-secret and secret request headers.

**Pass condition:** secrets never appear in normal logs or exported non-secret settings.

**REQ-032 / EVAL-032 — Snapshot/pinned model support.**  
Where providers publish snapshot IDs, the user may pin a snapshot rather than use a moving alias.

**Pass condition:** selected string is preserved exactly.

---

## 9. Provider voice requirements

**REQ-033 / EVAL-033 — Provider voice selector.**  
The user shall be able to choose among voices supported by the selected realtime provider/model.

**Pass condition:** the first session configuration contains the chosen voice where the provider exposes one.

**REQ-034 / EVAL-034 — Voice capability metadata.**  
Adapters shall declare whether voice can change at runtime, only before first output, or only by starting a new session.

**Pass condition:** Qwen-style first-session-only voice behavior can be represented without provider-specific conditionals in the UI.

**REQ-035 / EVAL-035 — Safe voice restart.**  
When a provider requires a restart to change voice, the app shall offer a fast session restart and preserve local transcript/context according to user policy.

**Pass condition:** changing such a voice never leaves UI state claiming a voice that the active provider did not accept.

**REQ-036 / EVAL-036 — Custom/cloned provider voices.**  
Where a provider account exposes custom voice IDs, the profile shall accept the ID without requiring it to be hard-coded into the app.

**Pass condition:** custom voice identifiers round-trip through secure configuration.

---

## 10. Local model-output effects

Provider voice and local audio effects are separate controls. Effects operate on decoded model PCM after network receipt and before the final output device.

**REQ-037 / EVAL-037 — Gain.**  
Output gain shall be adjustable and hard-limited to prevent numeric clipping.

**REQ-038 / EVAL-038 — Equalizer.**  
At minimum, low-shelf, peaking/mid, and high-shelf EQ shall be available.

**REQ-039 / EVAL-039 — Pitch shift.**  
Pitch shall be adjustable independently of speed over a practical voice range.

**REQ-040 / EVAL-040 — Tempo/speed.**  
Playback speed shall be adjustable with pitch preservation.

**REQ-041 / EVAL-041 — Coupled tape-style speed.**  
A separate mode shall intentionally couple speed and pitch.

**REQ-042 / EVAL-042 — Formant compensation.**  
Where the selected stretch engine supports it, formant preservation/shift shall be user-selectable.

**REQ-043 / EVAL-043 — Robot effect.**  
A built-in robot preset shall combine deterministic DSP such as ring modulation, filtering, and optional bit reduction without requiring a generative voice model.

**REQ-044 / EVAL-044 — Bunny effect.**  
A built-in bunny preset shall produce a higher, lighter voice using pitch/formant/EQ settings while remaining intelligible.

**REQ-045 / EVAL-045 — Scary effect.**  
A built-in scary preset shall produce a lower/darker voice using pitch/formant/EQ and restrained modulation/delay while remaining intelligible.

**REQ-046 / EVAL-046 — Pixie effect.**  
A built-in pixie preset shall produce a bright elevated voice with a distinct spectral/space treatment while remaining intelligible.

**REQ-047 / EVAL-047 — User presets.**  
Users shall be able to save, rename, duplicate, reorder, export, and import effect presets.

**REQ-048 / EVAL-048 — Bypass.**  
The entire FX rack shall have one-click bypass and individual stage bypass.

**REQ-049 / EVAL-049 — Realtime safety.**  
No realtime DSP stage may perform blocking disk/network I/O on the audio callback.

**REQ-050 / EVAL-050 — Latency budget.**  
Default effects shall add no more than 40 ms algorithmic buffering beyond the provider/output pipeline on desktop; mobile may use a documented higher buffer under device pressure.

**REQ-051 / EVAL-051 — Preset loudness guard.**  
Factory presets shall be gain-normalized so switching effects does not create hazardous volume jumps.

---

## 11. Dictation and transcription

**REQ-052 / EVAL-052 — Hold-to-dictate.**  
A global desktop hotkey shall begin recording on press and stop/transcribe on release.

**REQ-053 / EVAL-053 — Toggle dictation.**  
A second action shall start recording on first press and stop/transcribe on second press.

**REQ-054 / EVAL-054 — Dictation destination.**  
The result may be copied to clipboard, pasted into the previously focused application when platform permissions allow, appended to an RVC note, or shown for review.

**REQ-055 / EVAL-055 — Local dictation.**  
At least one bundled/downloadable local English STT path shall work without Internet connectivity.

**Pass condition:** an offline fixture and live microphone test produce text with networking disabled.

**REQ-056 / EVAL-056 — Cloud dictation.**  
OpenAI, Gemini, Qwen, and xAI transcription-capable adapters may expose dedicated STT models independently of the selected conversation model.

**REQ-057 / EVAL-057 — Live transcription.**  
A live-caption mode shall show partial/final text while the microphone is active when the selected engine provides partials.

**REQ-058 / EVAL-058 — Audio-file transcription.**  
The user shall be able to import common audio files and transcribe them with a local or cloud engine.

**REQ-059 / EVAL-059 — Common audio decoding.**  
At minimum WAV, MP3, FLAC, AAC/M4A, OGG/Vorbis, and AIFF shall be accepted when the container contains a supported audio stream.

**REQ-060 / EVAL-060 — Long-file segmentation.**  
Long files shall be processed in bounded segments with cancellation and progress reporting rather than loaded as one unbounded in-memory sample array.

**REQ-061 / EVAL-061 — Timestamp preservation.**  
When an STT provider returns segment or word timestamps, the result model shall preserve them.

**REQ-062 / EVAL-062 — Speaker metadata.**  
When a provider/local engine returns diarization, speaker labels shall be preserved; absence of diarization shall not be fabricated.

**REQ-063 / EVAL-063 — Export.**  
Transcriptions shall export as plain text, Markdown, JSON with timing metadata, and SRT when timestamps are available.

**REQ-064 / EVAL-064 — Recording retention policy.**  
The user shall choose per mode whether source recordings are deleted after successful transcription, retained locally, or retained until manual cleanup.

---

## 12. Compact app-card and full UI

**REQ-065 / EVAL-065 — Compact card.**  
The app shall have a small borderless/compact card intended to remain near the edge of the screen without becoming a full chat window.

**REQ-066 / EVAL-066 — Card contents.**  
The card shall show at minimum current state, mic meter/waveform, provider, model, voice/preset, mute, stop-response, and session stop controls.

**REQ-067 / EVAL-067 — Expand/collapse.**  
One action shall expand the card into transcript/settings detail and collapse it again.

**REQ-068 / EVAL-068 — User-defined summon hotkey.**  
Desktop users shall configure the global hotkey that shows/hides/focuses the card.

**REQ-069 / EVAL-069 — Dictation hotkeys are independent.**  
Summon, hold-to-dictate, toggle-dictation, mute, and stop-response bindings shall be independently configurable and conflict-checked.

**REQ-070 / EVAL-070 — Tray behavior.**  
Desktop builds shall optionally minimize to tray and expose session/mute/dictation quick actions.

**REQ-071 / EVAL-071 — Android persistent control.**  
When Android hands-free mode is running in the background, the app shall use a foreground-service notification with explicit visible microphone state and stop/mute actions.

**REQ-072 / EVAL-072 — Accessibility.**  
All state changes conveyed by color/animation shall also have a textual/iconic or accessibility-semantic representation.

---

## 13. Authentication and secret handling

**REQ-073 / EVAL-073 — Never fake provider OAuth.**  
The application shall not present a “Sign in with OpenAI/xAI/Qwen” flow unless that provider publishes an API authorization flow intended for third-party client use.

**Pass condition:** current OpenAI/xAI/Qwen provider plugins expose API-key/token-broker methods, not consumer-account credential scraping.

**REQ-074 / EVAL-074 — Gemini OAuth.**  
Gemini shall support official Google OAuth 2.0 desktop/mobile authorization when the user configures a Google Cloud OAuth client.

**REQ-075 / EVAL-075 — API-key fallback.**  
Every provider that officially supports API keys shall support a BYOK path on trusted desktop hosts.

**REQ-076 / EVAL-076 — Client-safe temporary credentials.**  
Android production connections shall use short-lived/ephemeral credentials or a trusted relay whenever the provider offers them; long-lived master API keys shall not be embedded in the APK.

**REQ-077 / EVAL-077 — Token broker.**  
The product shall include a small optional token-broker service contract capable of minting/returning provider-supported short-lived credentials while keeping master keys server-side.

**REQ-078 / EVAL-078 — Encrypted local secret storage.**  
Credentials persisted by the app shall be stored using an encrypted secret vault or platform credential store, not plaintext JSON/TOML.

**REQ-079 / EVAL-079 — Secret redaction.**  
Logs, crash reports, export bundles, and diagnostic screens shall redact bearer tokens, API keys, OAuth refresh tokens, and secret custom headers.

**REQ-080 / EVAL-080 — Endpoint security.**  
Non-localhost provider endpoints shall require TLS by default. Insecure transport may be enabled only for explicit loopback/LAN development profiles with a warning.

**REQ-081 / EVAL-081 — OAuth PKCE/state.**  
OAuth flows shall use current native-app best practices including state validation and PKCE where the provider flow supports them.

---

## 14. Configuration and extensibility

**REQ-082 / EVAL-082 — Machine-local settings.**  
Audio device IDs, window position, and hotkeys are machine-local.

**REQ-083 / EVAL-083 — Portable profiles.**  
Provider/model preferences, prompts, non-secret endpoints, turn settings, and FX presets shall be exportable/importable independently of machine-local hardware IDs.

**REQ-084 / EVAL-084 — Secret separation.**  
Portable configuration exports shall not include credentials unless the user performs a separate explicit encrypted-secret export flow.

**REQ-085 / EVAL-085 — Provider capability schema.**  
Every provider adapter shall declare supported input/output modalities, transports, auth modes, audio formats, native turn modes, voice semantics, cancellation support, transcription support, and session limits.

**REQ-086 / EVAL-086 — Generic endpoints.**  
A generic profile shall let advanced users connect to compatible self-hosted/gateway endpoints without pretending those endpoints have capabilities they did not declare.

**REQ-087 / EVAL-087 — No vendor leakage into UI state.**  
Core conversation state shall use product concepts such as `listening`, `committing`, `responding`, and `interrupted`, with provider event names translated inside adapters.

**REQ-088 / EVAL-088 — Versioned configuration.**  
Persisted configuration shall include a schema version and deterministic migration path.

---

## 15. Session reliability and diagnostics

**REQ-089 / EVAL-089 — Explicit connection state.**  
The UI shall distinguish disconnected, connecting, ready, listening, responding, reconnecting, rate-limited, auth-failed, and fatal states.

**REQ-090 / EVAL-090 — Bounded reconnect.**  
Transient network failures shall use bounded exponential backoff with jitter and shall not silently create unlimited paid sessions.

**REQ-091 / EVAL-091 — Session-limit handling.**  
Provider-specific turn/duration/session limits shall be represented as capabilities and surfaced before forced expiry when predictable.

**REQ-092 / EVAL-092 — Context handoff on rotation.**  
When a provider session must rotate, the app shall optionally seed the next session from a bounded local text transcript/summary rather than silently losing context.

**REQ-093 / EVAL-093 — Latency telemetry.**  
Diagnostics shall separately measure capture-to-send, turn-end-to-first-model-event, first-audio latency, network jitter/buffer depth, DSP latency, and underruns.

**REQ-094 / EVAL-094 — Cost/usage visibility where possible.**  
When provider events expose token/audio usage, the app shall record and display it per session. It shall not invent cost values when exact provider pricing metadata is unavailable.

**REQ-095 / EVAL-095 — Structured logs.**  
Logs shall be structured, levelled, secret-redacted, and include session/provider correlation IDs without recording raw audio by default.

---

## 16. Privacy and data retention

**REQ-096 / EVAL-096 — Local-first wake path.**  
Wake word, local VAD, level meter, and default diagnostics shall not require cloud upload.

**REQ-097 / EVAL-097 — Recording off by default for conversations.**  
Realtime conversation audio shall not be persistently recorded unless the user enables recording for that session/mode.

**REQ-098 / EVAL-098 — Transcript retention control.**  
Conversation transcripts may be ephemeral, session-only, or persisted locally according to a user preference.

**REQ-099 / EVAL-099 — Delete means local deletion.**  
When the user deletes locally retained audio/transcripts, the app shall delete its own stored copies and indexes. It shall not claim to delete provider-side data it cannot control.

**REQ-100 / EVAL-100 — Privacy status.**  
The card shall make it obvious when microphone audio is being sent to a remote provider versus processed locally only.

---

## 17. Performance targets

These are product budgets, not claims that third-party network latency is under application control.

**REQ-101 / EVAL-101 — Meter responsiveness.**  
Mic level visualization shall begin within 100 ms of capture start and refresh at at least 20 visual updates per second when the UI is visible.

**REQ-102 / EVAL-102 — Local barge-in reaction.**  
In confirmed interruption mode, the default local confirmation window shall be tunable in the 150–500 ms range; playback cancellation shall start immediately after confirmation.

**REQ-103 / EVAL-103 — Audio callback safety.**  
The realtime audio callback shall allocate minimally and shall never await network, filesystem, database, UI, or model operations.

**REQ-104 / EVAL-104 — Startup.**  
On a normal warm desktop launch, the compact card shall become interactive before provider connection establishment completes.

**REQ-105 / EVAL-105 — Idle resource policy.**  
With wake mode disabled and no session active, no continuous microphone capture or inference shall run.

**REQ-106 / EVAL-106 — Wake-mode resource policy.**  
With wake mode enabled, only the minimum local wake/VAD path shall run before activation; the cloud session remains disconnected unless the user chooses an always-connected policy.

---

## 18. Packaging, updates, and installation

**REQ-107 / EVAL-107 — Windows package.**  
Produce a signed-install-capable Windows artifact with optional autostart.

**REQ-108 / EVAL-108 — Linux packages.**  
Produce at least AppImage plus one distro-friendly package format; runtime behavior shall not assume Ubuntu-only paths.

**REQ-109 / EVAL-109 — Android package.**  
Produce an Android APK/AAB build path with microphone/foreground-service permissions declared explicitly.

**REQ-110 / EVAL-110 — Auto-update isolation.**  
Desktop updater failure shall not corrupt the current runnable install.

**REQ-111 / EVAL-111 — Model asset management.**  
Local STT/wake models shall be versioned downloads with checksums and a visible disk-usage/delete control.

---

## 19. Testing and acceptance gates

**REQ-112 / EVAL-112 — Provider contract mocks.**  
Every provider adapter shall have deterministic mock-server/event fixtures so most tests require no paid API call.

**REQ-113 / EVAL-113 — Paid smoke tests.**  
A credential-gated smoke suite shall verify one live conversation and one interruption for each first-party realtime provider.

**REQ-114 / EVAL-114 — Audio loopback suite.**  
A fixture suite shall test VAD, AEC, interruption, resampling, clipping, and DSP presets using known audio samples.

**REQ-115 / EVAL-115 — Cross-platform build gate.**  
CI shall build or compile-check Windows, Linux, and Android targets on every release candidate.

**REQ-116 / EVAL-116 — UI state-machine tests.**  
Provider event ordering, reconnect, cancellation, model switch, and voice restart shall be tested independently of the actual UI rendering library.

**REQ-117 / EVAL-117 — Secret-leak tests.**  
Automated tests shall inject sentinel credentials and assert they do not appear in logs, settings export, panic text, or diagnostic bundles.

**REQ-118 / EVAL-118 — Long-run soak.**  
A release candidate shall complete a multi-session soak that exercises reconnects, repeated wake activation, effect switching, and device changes without unbounded memory/thread growth.

---

## 20. Included, future, rejected, and unknown

### Included in the first production design

- OpenAI Realtime 2.1/2.1-mini adapter.
- Gemini 3.1 Flash Live adapter.
- Qwen Audio 3.0 Realtime adapter and capability path for Qwen3.5 Omni Realtime.
- xAI Grok Voice adapter.
- Generic configurable endpoint profile.
- Hands-free, wake word, interruption, PTT conversation, manual turn.
- Animated mic level/waveform and state visualization.
- Provider voice selection.
- Realtime local output FX with factory presets.
- Hold-to-dictate and toggle dictation.
- Local English STT.
- Cloud STT adapter hooks.
- Audio-file transcription.
- Windows, Linux, Android.
- Windows-host/WSL2 CLI bridge.
- Desktop global hotkeys, tray/card UI.
- Android foreground-service controls.
- Safe secret storage.
- Gemini OAuth.
- Provider ephemeral/temporary-token broker.
- Local VAD/wake path.
- Echo cancellation/noise suppression/AGC.
- Structured diagnostics and per-session usage metadata when providers expose it.

### Future goals retained by design

- Fully local end-to-end Qwen Omni conversation where hardware and local serving stacks can sustain useful latency.
- macOS/iOS packages; Tauri/Rust boundaries should not prevent them, but they are not release gates requested here.
- Voice cloning workflows inside the app. V1 accepts already-created custom voice IDs where providers support them.
- MCP/tool execution from voice.
- Multi-agent handoff.
- SIP/phone calls.
- System-audio capture and meeting transcription.
- Speaker identification.
- On-device neural voice conversion beyond low-latency DSP.
- Optional cloud sync of non-secret preferences.
- WearOS companion controls.

### Rejected

- Storing long-lived provider master API keys in the Android APK.
- Scraping consumer login sessions or browser cookies to simulate unsupported OpenAI/xAI/Qwen OAuth.
- Sending always-on ambient microphone audio to a cloud provider merely to detect the wake phrase.
- Making WSL2 the Windows audio host.
- One giant provider switch statement spread through UI/audio code.
- Blocking network/DSP allocation work inside the audio callback.
- Claiming every voice can change live when providers impose session-level restrictions.
- Coupling model voice identity to local FX presets.
- Requiring Electron or Python runtimes on end-user machines.

### Unknown / provider-controlled

- Future public OAuth availability for OpenAI, xAI, or Alibaba/Qwen API access.
- Future model IDs, voice catalogs, limits, and pricing.
- Whether every Qwen account/region has WebRTC/AOQ access; adapters must expose transport availability rather than assume it.
- Provider-side retention policies and account-specific feature access.
- Android OEM background-execution behavior beyond standard foreground-service guarantees.

---

## 21. Release slices

### R0 — protocol and audio spike

Exit only when:
- one native audio stream works on Windows and Linux;
- Android capture/playback works;
- local VAD + meter works;
- provider mock adapters pass;
- one OpenAI and one Gemini live session pass;
- secret storage and broker contract are proven.

### R1 — desktop alpha

Exit only when:
- OpenAI, Gemini, Qwen, xAI conversation adapters pass smoke tests;
- card/tray/hotkeys work;
- interruption/AEC works;
- provider/model/voice switching works;
- PTT/toggle dictation and local STT work;
- file transcription works;
- basic FX rack and four factory presets work.

### R2 — Android alpha

Exit only when:
- all four providers can authenticate without embedding master keys;
- foreground hands-free mode works;
- local wake/VAD works;
- FX and transcription modes work;
- battery/resource behavior is measured.

### R3 — beta hardening

Exit only when:
- soak, secret leak, reconnect, device migration, Wayland fallback, Android lifecycle, and update tests pass;
- user-visible diagnostics explain provider/session failure;
- packaging is reproducible.

### R4 — 1.0

Exit only when every Included requirement either passes its EVAL binding or is explicitly reclassified with a recorded rationale.

---

## 22. Source evidence verified 2026-08-29

Primary/current sources:

1. OpenAI GPT-Realtime-2.1 model documentation  
   https://developers.openai.com/api/docs/models/gpt-realtime-2.1

2. OpenAI API key safety guidance  
   https://help.openai.com/en/articles/5112595-best-practices-for-api-key

3. Google Gemini 3.1 Flash Live model documentation  
   https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-live-preview

4. Google Gemini Live API / ephemeral token reference  
   https://ai.google.dev/api/live

5. Google Gemini OAuth quickstart  
   https://ai.google.dev/gemini-api/docs/oauth

6. Alibaba Cloud Qwen-Audio realtime user guide  
   https://www.alibabacloud.com/help/en/model-studio/qwen-audio-realtime-user-guides

7. Alibaba Cloud Realtime token authentication  
   https://www.alibabacloud.com/help/en/model-studio/realtime-token-authentication

8. Alibaba Cloud current model catalog  
   https://www.alibabacloud.com/help/en/model-studio/models

9. xAI ephemeral token documentation  
   https://docs.x.ai/developers/model-capabilities/audio/ephemeral-tokens

10. Tauri 2 platform and mobile documentation  
    https://v2.tauri.app/start/  
    https://v2.tauri.app/develop/  
    https://v2.tauri.app/develop/plugins/

11. Tauri global shortcut and Stronghold documentation  
    https://v2.tauri.app/plugin/global-shortcut/  
    https://v2.tauri.app/plugin/stronghold/

12. RustAudio CPAL  
    https://github.com/RustAudio/cpal

13. sherpa-onnx cross-platform / Android / keyword-spotting documentation  
    https://k2-fsa.github.io/sherpa/onnx/  
    https://k2-fsa.github.io/sherpa/onnx/kws/

14. Signalsmith Stretch  
    https://github.com/Signalsmith-Audio/signalsmith-stretch

Reference applications:

15. RoomKit UI  
    https://github.com/roomkit-live/roomkit-ui

16. RoomKit core  
    https://github.com/roomkit-live/roomkit

17. OpenDex  
    https://github.com/wassgha/opendex

18. OpenWhispr  
    https://github.com/DevomB/OpenWhispr

---

## 23. Requirements completion statement

This requirements baseline deliberately treats provider names, model names, and transports as capabilities that can evolve. The invariant product is the local voice cockpit: one audio/state/UI layer, replaceable provider adapters, safe credentials, deterministic interruption, transparent microphone state, independent transcription modes, and local output transformation.

There are **118 Included contract/evaluation pairs** in this baseline. No requirement depends on an unimplemented “magic OAuth” path, hidden provider login scraping, or WSL2-specific audio behavior.
