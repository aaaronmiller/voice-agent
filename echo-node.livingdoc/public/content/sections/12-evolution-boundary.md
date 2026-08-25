# Evolution boundary: stretch goals and future work

**Phase:** 9 — Stretch | **Status:** Pending | **Owner:** Cheta

## Entry criteria

- [x] All phases 1-8 complete (or at least stable)
- [x] Core system is working end-to-end

## Stretch goals

These are aspirational — they should not block the core reconstruction. They are listed in rough priority order.

### S-1: Multi-agent orchestration

Route queries between multiple AI agents based on intent:

```
User: "what's the weather?"
  → routes to weather specialist agent

User: "deploy the api server"
  → routes to Hermes/Codex for tool execution

User: "tell me a joke"
  → routes to creative agent
```

**Implementation:** Extend the SmartRouter in `agent_profiles.py` with:
- Intent classification via lightweight classifier (or LLM call)
- Parallel agent execution where applicable
- Agent registry with capability announcements

### S-2: Phone call integration

Connect the voice agent to phone networks:
- **Twilio** integration for inbound/outbound calls
- **SIP** trunk support for enterprise
- **VoIP** adapter via WebRTC

**Implementation:** A new provider type that bridges SIP/telephony audio to the gateway. The gateway treats the phone call as another frontend.

### S-3: Persistent conversation memory

- Long-term user memory stored in a vector database
- Recall past conversations: "What did I ask you yesterday?"
- User preferences remembered across sessions

**Implementation:** 
- ChromaDB or SQLite for embedding storage
- Automatic summarization of each session
- Memory retrieval injected into system prompt

### S-4: Custom wake word training

- Train your own wake word from samples
- No dependency on pretrained OpenWakeWord models

**Implementation:** 
- Audio sample collection UI (web frontend)
- Wake word training pipeline (TensorFlow/PyTorch)
- Model export to ONNX for inference

### S-5: End-to-end encryption

- All audio encrypted between frontend and provider
- No plaintext audio on the gateway

**Implementation:** WebRTC with DTLS-SRTP for audio streams. Gateway only sees encrypted packets.

### S-6: Platform app store packages

- Flatpak for Linux
- macOS .app bundle
- Windows MSI installer
- Mobile apps (iOS/Android via WebView)

### S-7: Voice cloning

- Clone your own voice for TTS
- One-shot or few-shot cloning

**Implementation:** 
- Coqui-AI XTTS for local cloning
- ElevenLabs API for cloud cloning
- Voice profile management in settings

### S-8: Emotion and tone detection

- Detect user emotion from voice tone
- Adjust assistant response accordingly
- Visual emotion indicator in frontend

**Implementation:** Speech emotion recognition model (SER) running alongside VAD.

### S-9: Multi-language support

- Full internationalization of the UI
- Per-user language selection
- Real-time translation mode

### S-10: Accessibility features

- Screen reader support in web frontend
- High-contrast themes (beyond what's already in the living document shell)
- Switch control support for motor-impaired users
- Captioning for all audio responses

## Decision log for stretch goals

| # | Goal | Decision | Rationale |
|---|---|---|---|
| S-1 | Multi-agent | *pending* | Requires stable provider system first |
| S-2 | Phone calls | *pending* | Requires Twilio account |
| S-3 | Memory | *pending* | Needs vector DB infra |
| S-4 | Custom wake word | *pending* | Nice-to-have, not blocking |
| S-5 | E2E encryption | *defer* | Overkill for local-first system |
| S-6 | App store packages | *defer* | Only after core is shipped |
| S-7 | Voice cloning | *defer* | Deep technical rabbit hole |
| S-8 | Emotion detection | *defer* | Novelty feature |
| S-9 | i18n | *defer* | Not needed for English-first |
| S-10 | Accessibility | *defer* | Add when web frontend is stable |

## Resources needed

| Goal | What you need |
|---|---|
| Phone calls | Twilio account, phone number, SIP provider |
| Memory | ChromaDB or Pinecone account |
| Custom wake word | 50+ sample recordings per phrase |
| Voice cloning | 30s+ clean voice sample |
| App store | Flatpak, macOS dev account, Windows signing cert |

## Measuring stretch goal readiness

A stretch goal is **ready** when:
1. Core system has been stable for 2+ weeks
2. No critical bugs open
3. User has time and motivation to work on it
4. Required resources are available

## Exit criteria

- [ ] Stretch goals prioritized (this document)
- [ ] At least one stretch goal partially implemented (multi-agent or memory preferred)
- [ ] Decision log populated with actual decisions
- [ ] Readiness checklist reviewed with Cheta
