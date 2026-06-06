# Feature Specification: Echo-Node Voice AI Interface

**Feature Branch**: `001-echo-node-core`
**Created**: 2026-03-29
**Status**: Draft
**Input**: voice-agent-requirements.md + addendum.md

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Wake Word Voice Conversation (Priority: P1)

As a user, I want to say a wake word (default: "Yo Gimp") or press
a hotkey, speak naturally, and hear a spoken response from an AI
assistant — all from my terminal with no graphical interface
required. The full cycle from the end of my speech to hearing the
first word of the response MUST complete in under 2 seconds.

**Why this priority**: This is the core value proposition. Without a
working voice-in/voice-out loop, nothing else matters. Headless
terminal mode proves the pipeline works before adding visual layers.

**Independent Test**: Launch the system in terminal mode, say the
wake word, ask a question, and verify a spoken response plays back
through the speakers within 2 seconds.

**Acceptance Scenarios**:

1. **Given** the system is running in terminal mode, **When** I say
   "Yo Gimp" followed by "What's the weather like?", **Then** I
   hear a spoken response and see a text transcript in the terminal.
2. **Given** the system is running, **When** I press the configured
   hotkey, **Then** the system begins listening without requiring a
   wake word.
3. **Given** the system is actively speaking a response, **When** I
   say the wake word again (barge-in), **Then** the system stops
   speaking and begins listening to my new input.
4. **Given** I ask a follow-up question referencing my previous
   question, **Then** the assistant responds with awareness of the
   prior context (up to 15 turns).

---

### User Story 2 - Config-Only Provider Switching (Priority: P2)

As a user, I want to change any component of the voice pipeline
(speech recognition, text-to-speech, voice detection, wake word
engine, AI backend) by editing a single configuration file and
restarting — with zero code changes required.

**Why this priority**: Modularity is the key differentiator from
monolithic voice assistants. Users with different hardware, models,
or preferences MUST be able to customize without programming.

**Independent Test**: Edit the configuration file to switch the
speech recognition engine, restart, and verify the new engine is
active.

**Acceptance Scenarios**:

1. **Given** the system uses the default speech recognition engine,
   **When** I change `stt.provider` in the config file to an
   alternative engine and restart, **Then** the system uses the new
   engine with no errors.
2. **Given** I change `llm.base_url` to point to a cloud AI service,
   **Then** the system sends requests to that service without code
   changes.
3. **Given** I specify an invalid provider name in config, **When**
   the system starts, **Then** it displays a clear error message
   naming the invalid value and listing valid options.

---

### User Story 3 - Personality Presets & Conversation Memory (Priority: P3)

As a user, I want to select a personality preset (hacker, seductive,
butler, drill-sergeant, stoner-philosopher, or custom) that changes
the assistant's tone and speaking style, and I want the assistant to
remember our conversation within a session (up to 15 exchanges).

**Why this priority**: Personality differentiation and contextual
memory transform a voice tool into a companion. These features make
the product sticky and fun.

**Independent Test**: Select the "hacker" personality, ask a
question, verify the tone matches, then ask a follow-up referencing
the previous answer.

**Acceptance Scenarios**:

1. **Given** the personality is set to "hacker", **When** I ask
   "How do I fix a slow computer?", **Then** the response uses
   hacker-style vocabulary and tone.
2. **Given** I have asked 10 questions in this session, **When** I
   reference something from my 3rd question, **Then** the assistant
   recalls it correctly.
3. **Given** I restart the system, **Then** previous conversation
   history is discarded (no cross-session memory).
4. **Given** I create a custom personality file with a name,
   description, and behavioral rules, **When** I select it in
   config, **Then** the assistant adopts that personality.

---

### User Story 4 - 3D Avatar & Web Interface (Priority: P4)

As a user, I want to open a browser and see an animated 3D avatar
that lip-syncs to the assistant's speech, blinks, performs idle
gestures, and is framed by a selectable visual theme. I want to
browse a library of 10-15 bundled avatars and add my own.

**Why this priority**: The visual experience is a major engagement
driver but depends on the voice pipeline (P1) working first. The
avatar layer is purely additive.

**Independent Test**: Open the web interface, trigger a
conversation, and verify the avatar's mouth movements match the
spoken response.

**Acceptance Scenarios**:

1. **Given** the web interface is open, **When** the assistant
   speaks, **Then** the avatar's lips move in sync with the audio.
2. **Given** no conversation is active, **Then** the avatar
   performs idle animations (blinking, looking around, subtle
   gestures).
3. **Given** I select the "cyberpunk" theme, **Then** the visual
   frame around the avatar changes to the cyberpunk style.
4. **Given** I place a custom avatar model file in the models
   directory, **Then** it appears in the avatar selection list.
5. **Given** I am on the web interface, **Then** I can see a
   scrollable transcript of the conversation and a waveform
   indicator when the system is listening.

---

### User Story 5 - Cloud API Voice Mode (Priority: P5)

As a user, I want an alternative voice mode that uses a cloud AI
service's real-time audio API (e.g., Gemini Flash Live) for
bidirectional voice conversation — where the cloud handles both
speech recognition and text-to-speech — as an option alongside the
local modular pipeline. I also want the option to use cloud-based
speech recognition or text-to-speech providers individually within
the modular pipeline.

**Why this priority**: Provides a simpler, lower-resource alternative
for users who prefer cloud processing. Also opens up cloud STT/TTS
as individual provider options within the existing modular system.

**Independent Test**: Configure cloud API mode, speak to the
assistant, and verify a spoken response arrives via the cloud
service. Separately, configure a cloud STT provider within the
modular pipeline and verify it works.

**Acceptance Scenarios**:

1. **Given** I configure the system to use a cloud real-time audio
   API, **When** I speak, **Then** the cloud service handles speech
   recognition and response generation, and I hear audio responses.
2. **Given** the cloud API mode is active, **When** I speak while
   the assistant is responding, **Then** the assistant stops
   speaking (barge-in, handled by the cloud service).
3. **Given** I configure a cloud-based speech recognition provider
   in the modular pipeline, **Then** it works alongside local
   text-to-speech and other local components.
4. **Given** the cloud API key is missing or invalid, **Then** the
   system displays a clear error and does not silently fail.

---

### User Story 6 - Agent Integration (Priority: P6)

As a Hermes Agent or OpenClaw user, I want Echo-Node to act as a
voice input/output channel so that I can talk to my agent instead
of typing. I also want the assistant to invoke connected tools
when I ask it to (e.g., "search the web for X").

**Why this priority**: Agent integration extends Echo-Node from a
standalone tool into a component of larger AI workflows, but
requires the core pipeline and provider system to be stable first.

**Independent Test**: Connect Echo-Node to a running Hermes Agent
instance, speak a command, and verify the agent receives and
processes the voice input.

**Acceptance Scenarios**:

1. **Given** the Hermes Agent integration is enabled in config,
   **When** I speak a command, **Then** the Hermes Agent receives
   the transcribed text and can respond via Echo-Node's audio
   output.
2. **Given** the OpenClaw integration is enabled, **Then** Echo-Node
   appears as an available skill that OpenClaw can invoke.
3. **Given** the AI backend supports function calling and I say
   "Search the web for Dublin weather", **Then** the assistant
   invokes the appropriate connected tool and speaks the result.
4. **Given** integrations are disabled in config, **Then** the
   system runs standalone with no integration overhead.

---

### Edge Cases

- What happens when the microphone is unavailable or access is
  denied? The system MUST display a clear error and exit gracefully.
- What happens when VRAM is insufficient for the selected model
  combination? The system MUST warn the user before loading and
  suggest smaller models or CPU fallback.
- What happens when the AI backend is unreachable (network failure,
  local service not running)? The system MUST announce the error
  audibly or in the transcript and return to the dormant state.
- What happens when two providers claim the same role (e.g., two
  STT engines configured)? The system MUST use the one specified in
  config and ignore others.
- What happens when the wake word is detected during system startup
  before all models are loaded? The system MUST queue or ignore the
  trigger until ready.
- What happens when the user speaks for longer than the maximum
  supported utterance length? The system MUST process what it has
  and notify the user of the truncation.
- What happens when audio routing changes mid-session (e.g.,
  headphones plugged in)? The system SHOULD handle the change
  gracefully or notify the user to restart.
- What happens when the gateway is bound to 0.0.0.0 and an
  unauthorized LAN device connects? The system SHOULD log the
  connection. Authentication is deferred to post-v1.
- What happens when multiple remote clients trigger simultaneously?
  MVP: First client wins, others wait. Multi-session queuing is
  deferred to post-v1.

## Requirements *(mandatory)*

### Functional Requirements

**Audio Pipeline**

- **FR-001**: System MUST capture microphone audio and detect voice
  activity with configurable sensitivity thresholds.
- **FR-002**: System MUST detect a configurable wake word with a
  false positive rate of 5% or less.
- **FR-003**: System MUST transcribe speech with streaming partial
  results (latency under 500ms from speech to first partial text).
- **FR-004**: System MUST synthesize speech with streaming output,
  beginning playback at sentence boundaries rather than waiting for
  the complete response.
- **FR-005**: System MUST suppress audio feedback during playback
  (mic mute for MVP, acoustic echo cancellation for production).
- **FR-006**: System MUST support multiple speech recognition
  providers including: sherpa-onnx (default), faster-whisper, and
  VibeVoice-ASR (Microsoft 7B model, 51 languages).
- **FR-006a**: System MUST support multiple text-to-speech
  providers including: Kokoro-82M (default), Chatterbox, Orpheus,
  and Piper. VibeVoice-Realtime-TTS (0.5B, 9 languages) MAY be
  added as an optional provider if licensing permits.

**State Management**

- **FR-007**: System MUST maintain a 5-state lifecycle: dormant,
  triggered, listening, processing, speaking.
- **FR-008**: System MUST emit state change events to all connected
  clients in real time.
- **FR-009**: System MUST support both wake word and keyboard/hotkey
  activation.
- **FR-010**: System MUST return to dormant state after response
  playback completes or after a 30-second inactivity timeout.
- **FR-011**: System MUST support interruption (barge-in) during
  the speaking state via wake word or keyboard.

**Configuration**

- **FR-012**: All pipeline component selections, thresholds, model
  paths, and behavioral parameters MUST be configurable via a
  single YAML configuration file.
- **FR-013**: System MUST validate configuration at startup and
  report clear, actionable error messages for invalid values.
- **FR-013a**: System MUST clearly signal when startup is complete
  and it is ready to accept voice input (audible chime, visual
  indicator, or terminal message depending on mode).
- **FR-014**: System MUST calculate total memory requirements for
  the selected model combination and warn if it exceeds available
  resources before attempting to load.

**AI Backend**

- **FR-015**: System MUST send transcribed text to a user-configured
  AI endpoint and stream the response token by token.
- **FR-016**: System MUST support multiple AI backend targets
  (local inference, cloud services, agent systems) by changing
  configuration values only.
- **FR-017**: The AI backend API key MUST be optional (local
  services do not require one).

**Personality & Memory**

- **FR-018**: System MUST support personality presets that modify
  the AI's tone, vocabulary, and behavioral rules.
- **FR-019**: System MUST ship with at least 5 default personality
  presets.
- **FR-020**: Users MUST be able to create custom personality
  definitions.
- **FR-021**: System MUST maintain a sliding-window conversation
  history of up to 15 exchanges per session with no cross-session
  persistence.
- **FR-022**: The activation sound on wake word detection MUST be
  configurable (built-in options plus custom audio files).

**Visual Interface**

- **FR-023**: System MUST display an animated 3D avatar that
  lip-syncs to the spoken response audio.
- **FR-024**: Avatar MUST perform idle animations when not speaking.
- **FR-025**: System MUST support at least 5 visual themes for
  framing the avatar display.
- **FR-026**: System MUST ship with 10-15 bundled avatar models
  with rotation and manual selection.
- **FR-027**: Users MUST be able to add custom avatar models.
- **FR-028**: System MUST display a conversation transcript and a
  visual listening indicator.

**Cloud API Mode**

- **FR-029**: System MUST support an optional cloud real-time audio
  API mode as an alternative to the local modular pipeline.
- **FR-030**: Cloud API mode MUST integrate with the existing
  configuration system, wake word detection, and visual interface.
- **FR-031**: System MUST support cloud-based speech recognition
  and text-to-speech as individual provider options within the
  modular pipeline.
- **FR-032**: Cloud pipeline mode MUST be configured via a top-level
  `pipeline_mode: cloud` option that bypasses the modular
  STT/TTS/LLM chain and uses Gemini Flash Live's bidirectional
  audio WebSocket directly.

**Agent Integration**

- **FR-033**: System MUST register as a voice channel for the
  Hermes Agent system.
- **FR-034**: System MUST expose itself as an OpenClaw skill.
- **FR-035**: System MUST support AI function calling for invoking
  connected tools via voice commands.
- **FR-036**: All integration adapters MUST be independently
  togglable via configuration.

**Platform & Setup**

- **FR-037**: System MUST auto-detect available compute resources
  and use GPU acceleration when available. Supported accelerators:
  NVIDIA (CUDA), Intel Arc (OpenVINO), AMD (ROCm). CPU-only MUST
  be supported as a fallback.
- **FR-038**: System MUST auto-detect and configure audio routing
  on WSL2.
- **FR-039**: System MUST support Linux (Fedora, Ubuntu), macOS,
  and Windows via WSL2.
- **FR-040**: System MUST provide an automated setup process that
  installs dependencies and downloads required models.
- **FR-041**: System MUST operate in headless (terminal-only) mode
  with no graphical dependencies.

**Network & Remote Access**

- **FR-042**: The gateway MUST default to binding on localhost
  (127.0.0.1) for security.
- **FR-043**: The gateway MUST support a configuration option to
  bind to all network interfaces (0.0.0.0), enabling access from
  LAN devices.
- **FR-044**: The gateway protocol MUST be lightweight enough for
  resource-constrained embedded clients (e.g., ESP32) to connect,
  stream audio, and receive audio responses.
- **FR-045**: Remote access beyond the local network is explicitly
  deferred and out of scope for v1.
- **FR-046**: The system MUST support a dedicated ESP32 client
  module that runs local wake word detection on the device, streams
  captured audio to the central gateway upon activation, and plays
  back audio responses from the gateway.
- **FR-047**: The system MUST support a thin-client terminal mode
  where other computers on the local network connect to a central
  machine running the audio worker and models. The remote machine
  captures and plays audio locally but uses the central machine
  for all inference (STT, LLM, TTS).
- **FR-048**: Both ESP32 and remote terminal clients MUST trigger
  via their own local wake word detection or hotkey, independent
  of the central worker's wake word listener.
- **FR-049**: Remote clients (browser, terminal, ESP32) MUST use a
  single WebSocket protocol with raw 16kHz PCM audio. ESP32 MAY
  use a simplified binary protocol handler if raw PCM is
  functionally infeasible on the device.

### Key Entities

- **Session**: A single continuous interaction from system start to
  shutdown. Owns conversation history (max 15 turns), active
  personality preset, and current pipeline state. No persistence
  across restarts.
- **Provider**: An interchangeable implementation of a pipeline
  component (speech recognition, text-to-speech, voice detection,
  wake word, AI backend). Each provider has a name, resource
  requirements, and configuration parameters. Supported providers
  include: sherpa-onnx, faster-whisper, VibeVoice-ASR (STT);
  Kokoro-82M, Chatterbox, Orpheus, Piper (TTS); Silero-VAD (VAD);
  OpenWakeWord (wake word); Ollama, OpenAI-compat, Gemini Live
  (LLM/cloud). VibeVoice-Realtime-TTS MAY be added post-v1.
- **Personality**: A named preset defining the AI's tone and
  behavioral rules. Has a name, description, and behavioral
  definition. Can be built-in or user-created.
- **Avatar**: A 3D character model used for visual display. Has a
  file reference, display name, and lip-sync capability. Can be
  bundled or user-provided.
- **Pipeline State**: One of 5 lifecycle states (dormant, triggered,
  listening, processing, speaking) with defined transitions. Owned
  by the audio processing layer, broadcast to all connected
  clients.
- **Configuration**: A single YAML file defining all component
  selections, thresholds, endpoints, personality, and integration
  toggles. Validated at startup.
- **Remote Client**: A device on the local network that connects to
  the central gateway to use its hosted models. Three client types:
  (1) ESP32 embedded device with custom firmware, local wake word,
  mic capture, and speaker playback; (2) Remote terminal — another
  computer running the thin-client in headless mode, capturing and
  playing audio locally while offloading inference to the central
  machine; (3) Browser client — standard web interface accessing
  the gateway over LAN.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can speak a question and hear the first word of
  the response within 2 seconds of finishing their sentence.
  Latency budget: STT ≤500ms, LLM first token ≤800ms, TTS first
  audio ≤700ms.
- **SC-002**: All default models fit within 6GB of GPU memory
  simultaneously.
- **SC-003**: Users can swap any pipeline component by editing the
  configuration file and restarting — no code changes required.
- **SC-004**: Users can hold a 15-turn conversation where the
  assistant correctly references earlier context.
- **SC-005**: The system runs on CPU-only hardware (fully
  functional, no hard latency target — actual performance MUST be
  documented per hardware class).
- **SC-006**: Headless terminal mode produces a complete voice
  conversation with no graphical dependencies installed.
- **SC-007**: The 3D avatar's lip movements are perceptibly
  synchronized with the spoken audio (no visible lag).
- **SC-008**: The false positive rate for wake word detection is
  5% or lower during normal ambient conditions.
- **SC-009**: Switching between personality presets produces a
  noticeably different conversational tone.
- **SC-010**: The system provides clear, actionable error messages
  for all configuration mistakes, missing models, and resource
  shortfalls — no silent failures.

## Assumptions

- Users have a working microphone and speakers/headphones. The
  system does not support text-only input as a primary mode.
- The primary deployment target is a single desktop/laptop machine
  acting as the central inference server. Multiple client devices
  (ESP32, remote terminals, browsers) on the LAN can connect to
  this central machine. Distributed inference across multiple
  servers is out of scope.
- English is the only supported language for v1. Multilingual
  support is deferred.
- Users are comfortable editing YAML configuration files. A
  graphical configuration UI is a Phase 3 enhancement, not a
  requirement for core functionality.
- Cross-session conversation memory is handled by the connected
  agent system (e.g., Hermes Agent), not by Echo-Node itself.
- Mobile and embedded device access is handled via the web
  interface and gateway protocol over the local network, not a
  native mobile application. Remote access beyond LAN is deferred.
- Voice cloning and custom voice training are out of scope due to
  ethical and legal complexity.
- The Gemini Flash Live API requires a user-provided API key and
  an active internet connection. The system does not provide or
  manage API keys.
- Cloud-based providers (STT, TTS, LLM) require internet access.
  The core local pipeline operates fully offline.
- VibeVoice-ASR (7B-9B params) requires ~18GB VRAM at FP16 or ~6GB
  with 4-bit quantization. Users selecting this provider must have
  adequate GPU memory or accept CPU fallback with higher latency.

## Clarifications

### Session 2026-03-29

- Q: Should the gateway bind to localhost only, or be LAN-accessible
  for remote devices? → A: Localhost by default, with a config
  toggle for LAN access (0.0.0.0). ESP32 devices are a target use
  case as remote voice terminals. Beyond-LAN access deferred.
- Q: In cloud API mode, where does wake word detection run? → A:
  Wake word always runs locally — the worker gates when the cloud
  stream opens. ESP32 devices run their own local wake word
  detection. Remote terminal clients also run local wake word.
  A dedicated ESP32 client module is required. Other LAN computers
  can connect as thin-client terminals using the central machine's
  models for inference while handling audio capture/playback locally.
- Q: What is the acceptable latency target on CPU-only hardware?
  → A: No hard limit. CPU mode MUST be fully functional; actual
  latency MUST be documented per hardware class. GPU acceleration
  MUST be used when available — NVIDIA (CUDA), Intel Arc (OpenVINO),
  and AMD (ROCm) all supported.
- Q: What feedback does the user get during model loading at
  startup? → A: No elaborate progress reporting needed — just load
  fast. System MUST signal clearly when ready (chime, indicator,
  or terminal message). Wake word triggers before ready MUST be
  ignored.
- Q: What protocol do remote clients (ESP32, remote terminals) use
  to communicate with the gateway? → A: Single WebSocket protocol
  with raw 16kHz PCM for all clients. ESP32 gets an exception: if
  functionally unable to send raw PCM, use a simplified binary
  protocol handler (edge case in gateway).
- Q: How does Gemini Flash Live API integrate with the provider
  architecture? → A: Separate "cloud pipeline mode" via top-level
  config option. Bypasses modular STT/TTS/LLM chain entirely, uses
  Gemini's bidirectional audio WebSocket directly.
- Q: What is VibeVoice and how should it be integrated? → A:
  VibeVoice is BOTH STT and TTS, but TTS code was removed from
  GitHub (Sept 2025). Integrate VibeVoice-ASR (7B, 51 langs) as
  STT provider. VibeVoice-Realtime-TTS (0.5B, 9 langs) can be added
  as optional TTS provider.
- Q: How should the 2-second end-to-end latency budget be allocated
  across STT, LLM, and TTS stages? → A: STT ≤500ms, LLM first
  token ≤800ms, TTS first audio ≤700ms. Balanced allocation
  matching existing FR-003 STT target.
- Q: How should multi-client concurrency be handled when multiple
  remote clients trigger simultaneously? → A: Single active
  conversation at a time (MVP). First-come-first-served; others
  wait. Multi-session queuing deferred to post-v1.
