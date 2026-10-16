# Voice Assistant Requirements

## Executive Summary

Build a cross-platform voice assistant daemon that provides hands-free interaction with autonomous agents and LLMs via wake word detection, STT, and TTS. The system should be model-agnostic, allowing users to switch between different AI backends (Hermes, OpenClaw, Claude Code, etc.) via configuration.

## Core Features

### 1. Wake Word Detection
- **Trigger**: Detect "Hey Jarvis" or custom wake word
- **Accuracy**: <5% false rejection, <0.5 false accepts/hour
- **Performance**: Real-time detection on consumer hardware
- **Customization**: User can train custom wake words

### 2. Speech-to-Text (STT)
- **Providers**: Whisper.cpp (local), AssemblyAI (cloud), OpenAI Whisper API
- **Quality**: High accuracy for conversational speech
- **Latency**: <2s end-to-end response time
- **Languages**: English primary, expandable to others

### 3. Text-to-Speech (TTS)
- **Providers**: Piper TTS (local), Inworld AI (cloud), OpenAI TTS
- **Quality**: Natural-sounding voices
- **Speed**: <1s response for short responses
- **Customization**: Voice selection and speed control

### 4. Model-Agnostic LLM Integration
- **Providers**: Hermes Agent, OpenClaw, Claude Code, OpenAI API, Anthropic API
- **Switching**: Configuration-based backend selection
- **API Keys**: Support for multiple API keys per provider
- **State**: Maintain conversation context across turns

### 5. System Integration
- **OS Support**: Windows, macOS, Linux (WSL2)
- **Audio**: Cross-platform audio capture/playback
- **Hotkeys**: Push-to-talk and manual toggle
- **System Tray**: Background service management

## Non-Functional Requirements

### Performance
- **Latency**: <3s total response time (wake + STT + LLM + TTS)
- **Memory**: <500MB baseline, <1GB under load
- **CPU**: <20% average usage, <50% peak
- **Network**: Minimal bandwidth for local processing

### Usability
- **Reliability**: 99% uptime, graceful degradation
- **Privacy**: All processing local by default, optional cloud fallback
- **Accessibility**: Visual feedback for audio states
- **Customization**: Configurable wake word, voices, providers

### Development
- **Language**: Rust for performance and cross-platform support
- **Architecture**: Provider-based plugin system
- **Configuration**: JSON/YAML config files
- **Testing**: Comprehensive unit and integration tests

## Success Metrics

- **Accuracy**: <5% wake word false rejections
- **Speed**: <3s average response time
- **Uptime**: >99% availability
- **User Satisfaction**: Ability to switch between 3+ LLM providers seamlessly
- **Resource Usage**: <500MB memory baseline

## Out of Scope

- Complex multi-turn conversations (keep simple)
- Voice biometrics/identification
- Advanced noise cancellation (basic noise suppression only)
- Multi-language support beyond English
- Mobile app development

## Dependencies

- **Core**: Rust 2021, Cargo
- **Audio**: cpal, rodio
- **Wake Word**: openWakeWord
- **STT**: whisper-rs or whisper.cpp bindings
- **TTS**: piper-tts or similar
- **LLM**: reqwest for API calls
- **UI**: Tauri (optional, for system tray + settings)

## Configuration Schema

```json
{
  "wake_word": "hey jarvis",
  "wake_word_enabled": true,
  "stt": {
    "provider": "whisper.cpp",
    "language": "en",
    "api_key": "optional"
  },
  "tts": {
    "provider": "piper",
    "voice": "en_US-lessac-medium",
    "volume": 1.0,
    "speed": 1.0
  },
  "llm": {
    "provider": "hermes",
    "model": "default",
    "api_key": "optional",
    "base_url": "http://localhost:18789/v1/chat/completions"
  }
}
```

## Deployment

- **Package**: Single executable with bundled assets
- **Installation**: System tray auto-start on supported OS
- **Updates**: Self-updating via GitHub releases
- **Logs**: Structured logging with log levels

---

*Document version: 1.0*
*Last updated: 2026-03-16*