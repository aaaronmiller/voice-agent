# Tasks: Echo-Node Voice AI Interface

**Input**: Design documents from `/specs/001-echo-node-core/`
**Prerequisites**: plan.md, spec.md, data-model.md, contracts/, research.md, quickstart.md

**Tests**: Tests are OPTIONAL - included here for critical path validation only.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Worker**: `worker/` (Python 3.11+)
- **Gateway**: `gateway/src/` (Bun + TypeScript)
- **Frontend**: `frontend/src/` (Svelte 5)
- **Shared**: `config.yaml`, `models/`, `docs/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create project structure per implementation plan (echo-node/ with worker/, gateway/, frontend/, models/, docs/)
- [x] T002 [P] Initialize Python worker with requirements.txt (PyAudio, sounddevice, ONNX Runtime, PyTorch, sherpa-onnx, Kokoro-TTS, OpenWakeWord, Silero-VAD)
- [x] T003 [P] Initialize Bun gateway with package.json (Hono, ws, yaml parser)
- [x] T004 [P] Initialize Svelte 5 frontend with package.json (SvelteKit, TalkingHead, Three.js)
- [x] T005 [P] Create config.example.yaml with documented defaults
- [x] T006 [P] Create .gitignore (exclude models/, .venv/, node_modules/, *.pyc)
- [x] T007 Create setup.sh script (install Python deps, Bun deps, download default models)
- [x] T008 [P] Configure ESLint/Prettier for gateway TypeScript
- [x] T009 [P] Configure ruff/black for Python worker

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T010 [P] Create worker/providers/base.py with ABCs (STTProvider, TTSProvider, VADProvider, WakeWordProvider, LLMProvider)
- [x] T011 [P] Create worker/providers/__init__.py with PROVIDER_REGISTRY
- [x] T012 [P] Create worker/state_machine.py (5-state machine: DORMANT, TRIGGERED, LISTENING, PROCESSING, SPEAKING)
- [x] T013 [P] Create worker/config.py (load + validate config.yaml)
- [x] T014 [P] Create gateway/src/utils/config-loader.ts (parse + validate config.yaml)
- [x] T015 [P] Create gateway/src/utils/types.ts (TypeScript types for WebSocket events)
- [x] T016 [P] Create worker/audio/capture.py (mic capture via PyAudio/sounddevice)
- [x] T017 [P] Create worker/audio/playback.py (speaker playback)
- [x] T018 [P] Create gateway/src/websocket.ts (WebSocket hub: frontend ↔ worker relay)
- [x] T019 [P] Create worker/vram_calculator.py (check available VRAM before model load)
- [x] T020 Create worker/main.py (entry point, WebSocket server on port 9001)
- [x] T021 Create gateway/src/index.ts (Hono server on port 3000)
- [x] T022 [P] Create gateway/src/routes/health.ts (GET /api/health)
- [x] T023 [P] Create gateway/src/routes/config.ts (GET/PUT /api/config)
- [x] T024 [P] Create gateway/src/routes/status.ts (GET /api/status)
- [x] T025 Create gateway/src/utils/logger.ts (pino structured logging)
- [x] T026 Create worker streaming module: worker/streaming/sentence_chunker.py
- [x] T027 Create worker streaming module: worker/streaming/conversation/memory.py (15-turn sliding window)

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Wake Word Voice Conversation (Priority: P1) 🎯 MVP

**Goal**: Working voice conversation in terminal — wake word → STT → LLM → TTS → playback within 2 seconds

**Independent Test**: Launch system in terminal mode, say "Yo Gimp", ask question, verify spoken response within 2 seconds

### Implementation for User Story 1

- [x] T028 [P] [US1] Create worker/providers/stt/__init__.py with sherpa-onnx implementation (worker/providers/stt/sherpa_stt.py)
- [x] T029 [P] [US1] Create worker/providers/tts/__init__.py with Kokoro implementation (worker/providers/tts/kokoro_tts.py)
- [x] T030 [P] [US1] Create worker/providers/vad/silero_vad.py (Silero-VAD wrapper)
- [x] T031 [P] [US1] Create worker/providers/wake_word/openwakeword.py (OpenWakeWord wrapper, default: "Yo Gimp")
- [x] T032 [P] [US1] Create worker/providers/llm/ollama_llm.py (Ollama client with streaming)
- [x] T033 [US1] Create worker/pipeline.py (orchestrate wake → VAD → STT → LLM → TTS → playback)
- [x] T034 [US1] Implement keyboard/hotkey trigger in worker/main.py (bypass wake word)
- [x] T035 [US1] Implement barge-in detection in worker/pipeline.py (wake word during SPEAKING → LISTENING)
- [x] T036 [US1] Implement mic mute during TTS playback (MVP echo cancellation) in worker/audio/playback.py
- [x] T037 [US1] Implement activation sound (beep.wav) in worker/sounds/ + playback on wake word
- [x] T038 [US1] Create worker/personalities/ with 5 default presets (hacker.yaml, seductive.yaml, butler.yaml, drill-sergeant.yaml, stoner-philosopher.yaml)
- [x] T039 [US1] Implement personality injection in worker/pipeline.py (load system prompt from active personality)
- [x] T040 [US1] Implement conversation memory (15-turn sliding window) in worker/streaming/conversation/memory.py
- [x] T041 [US1] Implement state change events emission to gateway in worker/state_machine.py
- [x] T042 [US1] Implement transcript_partial and transcript_final events in worker/pipeline.py
- [x] T043 [US1] Implement llm_token and llm_complete events in worker/pipeline.py
- [x] T044 [US1] Implement tts_audio binary frames in worker/pipeline.py
- [x] T045 [US1] Create gateway/src/sessions/session-manager.ts (single active session MVP)
- [x] T046 [US1] Implement gateway relay: worker events → frontend in gateway/src/websocket.ts
- [x] T047 [US1] Add config validation for provider names in worker/config.py
- [x] T048 [US1] Add VRAM check before model load in worker/main.py (warn if exceeds available)
- [x] T049 [US1] Add startup ready signal (terminal message + optional chime) in worker/main.py
- [x] T050 [US1] Create docs/setup-wsl2.md (PipeWire/PulseAudio configuration)
- [x] T051 [US1] Create docs/setup-fedora.md (native Linux setup)
- [x] T052 [US1] Create docs/setup-macos.md (macOS setup)

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently (MVP complete)

---

## Phase 4: User Story 2 - Config-Only Provider Switching (Priority: P2)

**Goal**: Change any pipeline component by editing config.yaml and restarting — zero code changes

**Independent Test**: Edit stt.provider in config, restart, verify new engine is active

### Implementation for User Story 2

- [x] T053 [P] [US2] Create worker/providers/stt/faster_whisper_stt.py (faster-whisper implementation)
- [x] T054 [P] [US2] Create worker/providers/tts/piper_tts.py (Piper TTS implementation)
- [x] T055 [P] [US2] Create worker/providers/llm/openai_compat_llm.py (OpenAI-compatible API client for OpenRouter/OpenAI)
- [x] T056 [US2] Implement provider factory pattern in worker/providers/__init__.py (create_provider function)
- [x] T057 [US2] Add dynamic provider loading in worker/pipeline.py (instantiate from config)
- [x] T058 [US2] Implement config reload on PUT /api/config in gateway/src/routes/config.ts
- [x] T059 [US2] Add provider validation error messages in gateway/src/index.ts (list available providers on invalid)
- [x] T060 [US2] Implement TTS streaming (sentence-boundary chunking) in worker/providers/tts/kokoro_tts.py
- [x] T061 [US2] Add vram_requirement_mb property to all provider implementations
- [x] T062 [US2] Update config.example.yaml with all provider options documented
- [x] T063 [US2] Create docs/provider-guide.md (how to add new STT/TTS provider)

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Personality Presets & Conversation Memory (Priority: P3)

**Goal**: Select personality preset that changes tone; assistant remembers up to 15 turns within session

**Independent Test**: Select "hacker" personality, ask question, verify tone; ask follow-up referencing prior answer

### Implementation for User Story 3

- [x] T064 [P] [US3] Create worker/personalities/hacker.yaml (system prompt with hacker vocabulary)
- [x] T065 [P] [US3] Create worker/personalities/seductive.yaml (flirtatious, playful tone)
- [x] T066 [P] [US3] Create worker/personalities/butler.yaml (formal, polite, British)
- [x] T067 [P] [US3] Create worker/personalities/drill-sergeant.yaml (aggressive, motivational)
- [x] T068 [P] [US3] Create worker/personalities/stoner-philosopher.yaml (laid-back, deep thoughts)
- [x] T069 [US3] Implement custom personality support in worker/config.py (active: "custom" + custom_prompt)
- [x] T070 [US3] Implement personality switching via PUT /api/config in gateway/src/routes/config.ts
- [x] T071 [US3] Add GET /api/personalities endpoint in gateway/src/routes/personalities.ts (create new file)
- [x] T072 [US3] Implement conversation history persistence in session (15 turns, discard on restart) in worker/streaming/conversation/memory.py
- [x] T073 [US3] Add turn counter and oldest-turn eviction in worker/streaming/conversation/memory.py
- [x] T074 [US3] Implement LLM context building with conversation history in worker/pipeline.py
- [x] T075 [US3] Add personality selector to terminal output (show active personality)

**Checkpoint**: At this point, User Stories 1, 2, AND 3 should all work independently

---

## Phase 6: User Story 4 - 3D Avatar & Web Interface (Priority: P4)

**Goal**: Browser-based 3D avatar with lip-sync, idle animations, selectable themes, avatar library

**Independent Test**: Open browser, trigger conversation, verify avatar lip-sync matches audio

### Implementation for User Story 4

- [x] T076 [P] [US4] Create frontend/src/routes/+page.svelte (main page layout)
- [x] T077 [P] [US4] Create frontend/src/lib/components/avatar-display.svelte (TalkingHead wrapper)
- [x] T078 [P] [US4] Create frontend/src/lib/components/waveform.svelte (audio visualizer during LISTENING)
- [x] T079 [P] [US4] Create frontend/src/lib/components/transcript.svelte (conversation history display)
- [x] T080 [P] [US4] Create frontend/src/lib/components/status-indicator.svelte (state machine indicator)
- [x] T081 [P] [US4] Create frontend/src/lib/components/settings-panel.svelte (config UI)
- [x] T082 [P] [US4] Create frontend/src/lib/components/frame.svelte (theme frame wrapper)
- [x] T083 [P] [US4] Create frontend/src/lib/stores/websocket.svelte.ts (WebSocket connection state)
- [x] T084 [P] [US4] Create frontend/src/lib/stores/pipeline-state.svelte.ts ($state store for pipeline state)
- [x] T085 [P] [US4] Create frontend/src/lib/themes/minimal.css
- [x] T086 [P] [US4] Create frontend/src/lib/themes/cyberpunk.css
- [x] T087 [P] [US4] Create frontend/src/lib/themes/retro-terminal.css
- [x] T088 [P] [US4] Create frontend/src/lib/themes/glassmorphism.css
- [x] T089 [P] [US4] Create frontend/src/lib/utils/talking-head-loader.ts (dynamic TalkingHead import)
- [x] T090 [P] [US4] Bundle 10-15 VRM avatars in frontend/src/static/models/ (avatar-01-casual.vrm through avatar-12-steampunk.vrm)
- [x] T091 [US4] Implement avatar lip-sync from TTS audio amplitude in frontend/src/lib/components/avatar-display.svelte
- [x] T092 [US4] Implement idle animations (blinking, eye tracking) in frontend/src/lib/components/avatar-display.svelte
- [x] T093 [US4] Implement theme switching via config in frontend/src/lib/components/frame.svelte
- [x] T094 [US4] Implement avatar selection (browse library, custom upload) in frontend/src/lib/components/settings-panel.svelte
- [x] T095 [US4] Add GET /api/avatars endpoint in gateway/src/routes/avatars.ts
- [x] T096 [US4] Implement responsive design (mobile-friendly) in frontend/src/routes/+page.svelte
- [x] T097 [US4] Create frontend/src/app.css (global styles + CSS custom properties for themes)
- [x] T098 [US4] Configure Vite static asset serving for VRM models in frontend/vite.config.ts

**Checkpoint**: At this point, User Stories 1-4 should all work independently

---

## Phase 7: User Story 5 - Cloud API Voice Mode (Priority: P5)

**Goal**: Optional cloud mode (Gemini Flash Live) bypassing local STT/TTS/LLM; cloud STT/TTS as individual providers

**Independent Test**: Configure cloud API mode, speak, verify cloud handles STT+response+TTS

### Implementation for User Story 5

- [x] T099 [P] [US5] Add pipeline_mode: local | cloud to config schema in worker/config.py
- [x] T100 [P] [US5] Create gateway/src/integrations/gemini-live-adapter.ts (WebSocket proxy to generativelanguage.googleapis.com)
- [x] T101 [US5] Implement cloud mode gating in worker/main.py (wake word opens cloud stream)
- [x] T102 [US5] Implement Gemini Live WebSocket handshake in gateway/src/integrations/gemini-live-adapter.ts (16kHz PCM, setup payload)
- [x] T103 [US5] Implement barge-in handling for cloud mode in gateway/src/integrations/gemini-live-adapter.ts (interrupted: true)
- [x] T104 [US5] Add cloud API key validation (clear error if missing/invalid) in gateway/src/integrations/gemini-live-adapter.ts
- [x] T105 [US5] Update config.example.yaml with pipeline_mode: cloud example
- [x] T106 [US5] Create docs/gemini-live-setup.md (API key setup, usage guide)

**Checkpoint**: At this point, User Stories 1-5 should all work independently

---

## Phase 8: User Story 6 - Agent Integration (Priority: P6)

**Goal**: Echo-Node as voice channel for Hermes Agent and OpenClaw skill; MCP tool invocation via function calling

**Independent Test**: Connect to Hermes Agent, speak command, verify agent receives transcribed text

### Implementation for User Story 6

- [x] T107 [P] [US6] Create gateway/src/integrations/hermes-adapter.ts (WebSocket channel registration)
- [x] T108 [P] [US6] Create gateway/src/integrations/openclaw-adapter.ts (skill file management)
- [x] T109 [P] [US6] Create gateway/src/integrations/mcp-bridge.ts (MCP tool invocation relay)
- [x] T110 [US6] Implement Hermes channel registration in gateway/src/integrations/hermes-adapter.ts
- [x] T111 [US6] Implement OpenClaw skill directory creation in gateway/src/integrations/openclaw-adapter.ts
- [x] T112 [US6] Implement LLM function calling for MCP tools in worker/providers/llm/ollama_llm.py
- [x] T113 [US6] Add integration toggles to config.yaml (integrations.hermes.enabled, etc.)
- [x] T114 [US6] Implement standalone mode (all integrations disabled) in gateway/src/index.ts
- [x] T115 [US6] Create docs/hermes-integration.md (Hermes Agent setup guide)
- [x] T116 [US6] Create docs/openclaw-skill.md (OpenClaw skill configuration)

**Checkpoint**: At this point, all 6 user stories should work independently

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T117 [P] Create README.md (setup + usage documentation)
- [x] T118 [P] Create CHANGELOG.md with [Unreleased] section
- [x] T119 [P] Add ESP32 binary protocol handler (fallback if raw PCM infeasible) in gateway/src/websocket.ts
- [x] T120 [P] Implement SpeexDSP acoustic echo cancellation (production mode) in worker/audio/echo_cancel.py
- [x] T121 [P] Add VibeVoice-ASR provider (7B model, 51 languages) in worker/providers/stt/vibevoice_asr.py
- [x] T122 [P] Add remote terminal client support (thin-client mode) in gateway/src/sessions/session-manager.ts
- [x] T123 [P] Add LAN access logging (unauthorized connections) in gateway/src/index.ts
- [x] T124 [P] Code cleanup and refactoring across all stories
- [x] T125 [P] Performance optimization (VRAM management, model preloading)
- [x] T126 [P] Run quickstart.md validation (verify all steps work)
- [x] T127 [P] Create docs/troubleshooting.md (common issues + solutions)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - **BLOCKS all user stories**
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Phase 9)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Builds on US1 provider ABCs
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Builds on US1 conversation memory
- **User Story 4 (P4)**: Can start after Foundational (Phase 2) - Depends on US1 WebSocket events
- **User Story 5 (P5)**: Can start after Foundational (Phase 2) - Independent cloud mode
- **User Story 6 (P6)**: Can start after Foundational (Phase 2) - Independent integration adapters

### Within Each User Story

- Models/providers before services
- Services before endpoints/integration
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

**Phase 1 (Setup)**:
- T002, T003, T004, T005, T006, T008, T009 can all run in parallel

**Phase 2 (Foundational)**:
- T010, T011, T012, T013, T014, T015, T016, T017, T018, T019 can all run in parallel

**Phase 3 (US1)**:
- T028, T029, T030, T031, T032 can all run in parallel (provider implementations)
- T033 onwards has dependencies on providers being complete

**Phase 4 (US2)**:
- T053, T054, T055 can run in parallel (additional provider implementations)

**Phase 6 (US4)**:
- T076, T077, T078, T079, T080, T081, T082, T083, T084, T085, T086, T087, T088, T089, T090 can all run in parallel (frontend components)

**Cross-Story Parallel**:
- Once Phase 2 completes, different developers can work on different user stories in parallel

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test US1 independently (wake word → voice conversation in terminal)
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP: terminal voice conversation!)
3. Add User Story 2 → Test independently → Deploy/Demo (config-driven provider swapping)
4. Add User Story 3 → Test independently → Deploy/Demo (personalities + memory)
5. Add User Story 4 → Test independently → Deploy/Demo (3D avatar + web UI)
6. Add User Story 5 → Test independently → Deploy/Demo (Gemini Live cloud mode)
7. Add User Story 6 → Test independently → Deploy/Demo (Hermes/OpenClaw integration)

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (core pipeline)
   - Developer B: User Story 4 (frontend)
   - Developer C: User Story 2 (additional providers)
3. Stories complete and integrate independently

---

## Task Summary

| Phase | User Story | Task Count |
|-------|------------|------------|
| Phase 1 | Setup | 9 tasks |
| Phase 2 | Foundational | 18 tasks |
| Phase 3 | US1 (P1 - MVP) | 23 tasks |
| Phase 4 | US2 (P2) | 11 tasks |
| Phase 5 | US3 (P3) | 12 tasks |
| Phase 6 | US4 (P4) | 23 tasks |
| Phase 7 | US5 (P5) | 8 tasks |
| Phase 8 | US6 (P6) | 10 tasks |
| Phase 9 | Polish | 11 tasks |
| **Total** | | **125 tasks** |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- MVP scope: Phases 1-3 (Setup + Foundational + US1) = 50 tasks