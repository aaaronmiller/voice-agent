# Voice Assistant Design

## Architecture Overview

A cross-platform voice assistant daemon built in Rust with a provider-based plugin system. The architecture separates concerns into independent modules that communicate via well-defined interfaces, enabling model-agnostic AI backend switching and resilient operation.

## Core Components

### 1. Main Daemon (`voice-assistant`)
- **Entry Point**: `src/main.rs` - initializes system and starts event loop
- **Configuration**: `src/config.rs` - JSON/YAML config management
- **State Management**: `src/state.rs` - thread-safe shared state with Arc<Mutex<>>
- **Audio Pipeline**: `src/audio.rs` - cross-platform audio capture/playback
- **Wake Word**: `src/wake_word.rs` - openWakeWord integration
- **STT Providers**: `src/providers/stt.rs` - trait-based provider system
- **TTS Providers**: `src/providers/tts.rs` - trait-based provider system
- **LLM Providers**: `src/providers/llm.rs` - trait-based provider system
- **HTTP API**: `src/api.rs` - REST endpoints for Hermes integration
- **System Tray**: `src/tray.rs` - background service management

### 2. Provider System
```rust
trait STTProvider {
    fn transcribe(&self, audio: Vec<f32>) -> Result<String, Error>;
    fn is_available(&self) -> bool;
}

trait TTSProvider {
    fn synthesize(&self, text: &str) -> Result<Vec<u8>, Error>;
    fn is_available(&self) -> bool;
}

trait LLMProvider {
    fn chat(&self, messages: Vec<Message>) -> Result<String, Error>;
    fn is_available(&self) -> bool;
}
```

### 3. Audio Pipeline
```
Microphone → Audio Capture → Wake Word Detection → STT → LLM → TTS → Speaker
     ↓
  Audio Levels → Visual Feedback
```

## Module Details

### Configuration Store
- **Format**: JSON/YAML with validation
- **Location**: `~/.config/voice-assistant/config.json`
- **Features**: Default values, hot-reload, validation
- **Providers**: Dynamic loading based on config

### Audio Manager
- **Backend**: cpal for cross-platform audio
- **Features**: Device enumeration, hot-swapping, audio levels
- **Processing**: Noise suppression, AGC, silence detection
- **Buffer**: Ring buffer for wake word detection

### Wake Word Detection
- **Library**: openWakeWord (pure Rust, ONNX/TFLite backends)
- **Models**: Pre-trained models for common wake words
- **Performance**: <50ms detection latency
- **Customization**: User training for custom wake words

### STT Providers
```rust
// Whisper.cpp Provider
pub struct WhisperCppProvider {
    model: WhisperModel,
    device: Device,
}

// AssemblyAI Provider
pub struct AssemblyAIProvider {
    api_key: String,
    client: reqwest::Client,
}

// OpenAI Whisper API Provider
pub struct OpenAITTSProvider {
    api_key: String,
    client: reqwest::Client,
}
```

### TTS Providers
```rust
// Piper TTS Provider
pub struct PiperTTSProvider {
    model: PiperModel,
    voice: String,
}

// Inworld AI Provider
pub struct InworldTTSProvider {
    api_key: String,
    client: reqwest::Client,
}

// OpenAI TTS Provider
pub struct OpenAITTSProvider {
    api_key: String,
    client: reqwest::Client,
}
```

### LLM Providers
```rust
// Hermes Agent Provider
pub struct HermesProvider {
    base_url: String,
    api_key: Option<String>,
    client: reqwest::Client,
}

// OpenClaw Provider
pub struct OpenClawProvider {
    url: String,
    api_key: Option<String>,
    client: reqwest::Client,
}

// Claude Code Provider
pub struct ClaudeCodeProvider {
    cli_command: String,
    client: reqwest::Client,
}
```

## HTTP API Design

### REST Endpoints
```
GET    /status              # System status and configuration
POST   /voice/transcribe   # Transcribe audio data
POST   /voice/chat         # Send text to LLM and get response
POST   /voice/speak        # Synthesize speech from text
GET    /config            # Get current configuration
POST   /config            # Update configuration
GET    /providers         # List available providers
```

### WebSocket Events
```json
// Audio levels for visual feedback
{ "type": "audio_levels", "rms": 0.23, "peak": 0.45 }

// Wake word detection
{ "type": "wake_word", "detected": true, "word": "hey jarvis" }

// Transcription result
{ "type": "transcription", "text": "hello", "confidence": 0.95 }

// TTS synthesis complete
{ "type": "tts_complete", "duration_ms": 1200 }
```

## System Integration

### Cross-Platform Support
- **Windows**: Win32 audio, system tray via tauri-plugin-tray
- **macOS**: CoreAudio, LaunchAgent for autostart
- **Linux**: ALSA/PulseAudio, .desktop autostart
- **WSL2**: Windows audio passthrough, systemd service

### Dependencies Management
```toml
[package]
name = "voice-assistant"
version = "1.0.0"
edition = "2021"

[dependencies]
tauri = { version = "2.5", features = ["tray-icon"] }
cpal = "0.15"
rodio = "0.17"
reqwest = { version = "0.11", features = ["json"] }
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
thiserror = "1.0"
tokio = { version = "1.0", features = ["full"] }
log = "0.4"
env_logger = "0.10"
uuid = { version = "1.0", features = ["v4", "serde"] }

# Provider-specific dependencies
openwakeword = "0.1"
whisper-rs = "0.10"
piper-tts = "0.5"
```

## Configuration Schema

```json
{
  "wake_word": {
    "enabled": true,
    "phrase": "hey jarvis",
    "sensitivity": 0.5,
    "timeout_ms": 3000
  },
  "audio": {
    "input_device": "default",
    "output_device": "default",
    "sample_rate": 16000,
    "channels": 1,
    "noise_suppression": true,
    "auto_gain_control": true
  },
  "stt": {
    "provider": "whisper.cpp",
    "language": "en",
    "streaming": false,
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
    "base_url": "http://localhost:18789/v1/chat/completions",
    "temperature": 0.7,
    "max_tokens": 2048
  },
  "hotkeys": {
    "push_to_talk": "F1",
    "toggle_wake_word": "Ctrl+Shift+W",
    "toggle_assistant": "Ctrl+Shift+A"
  },
  "system": {
    "autostart": true,
    "minify_to_tray": true,
    "log_level": "info"
  }
}
```

## Error Handling & Resilience

### Provider Fallbacks
```rust
// Try providers in order of preference
let stt_result = config.stt.providers.iter().find_map(|provider| {
    match provider.transcribe(audio) {
        Ok(result) => Some(result),
        Err(_) => None, // Try next provider
    }
});
```

### Graceful Degradation
- **Audio Failure**: Retry with different backend, fallback to text input
- **Network Failure**: Switch to local providers, queue requests
- **Model Unavailability**: Fallback to default model, notify user
- **Resource Exhaustion**: Reduce quality, disable non-essential features

## Performance Optimizations

### Audio Processing
- **Threading**: Separate audio capture, processing, and API threads
- **Buffering**: Ring buffer for real-time processing
- **Caching**: Model caching for faster startup
- **Preemption**: Priority audio processing thread

### API Calls
- **Connection Pooling**: Reuse HTTP connections
- **Timeouts**: Configurable per-provider timeouts
- **Retries**: Exponential backoff with jitter
- **Batching**: Where applicable (e.g., TTS synthesis)

## Testing Strategy

### Unit Tests
- Provider trait implementations
- Configuration parsing and validation
- Audio processing algorithms
- Error handling paths

### Integration Tests
- End-to-end voice pipeline
- Provider switching
- Cross-platform audio
- System tray functionality

### Performance Tests
- Audio latency measurements
- API response times
- Memory usage under load
- CPU usage profiling

## Security Considerations

### API Key Management
- **Storage**: Encrypted config files
- **Transmission**: HTTPS for all API calls
- **Validation**: Input sanitization
- **Rotation**: Support for key rotation

### Audio Privacy
- **Local Processing**: Default to local processing
- **Data Retention**: Minimal local storage
- **Permissions**: OS-level audio permissions
- **Transparency**: Clear user controls

## Deployment

### Packaging
- **Executable**: Single binary with embedded assets
- **Installer**: Platform-specific installers
- **Updates**: Self-updating via GitHub releases
- **Dependencies**: Bundled where possible

### System Integration
- **Windows**: System tray, startup registry
- **macOS**: LaunchAgent, system tray
- **Linux**: .desktop file, systemd service
- **WSL2**: Windows integration

## Future Extensions

### Advanced Features
- **Multi-language Support**: Expand beyond English
- **Voice Biometrics**: User identification
- **Noise Cancellation**: Advanced audio processing
- **Multi-turn Conversations**: Context persistence

### Platform Extensions
- **Mobile Apps**: iOS/Android companion apps
- **Smart Home**: IoT device integration
- **Car Integration**: Automotive voice assistant
- **IoT Devices**: Embedded voice control

---

*Document version: 1.0*
*Last updated: 2026-03-16*