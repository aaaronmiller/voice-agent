# OpenAI Realtime API

**Phase:** 5b — OpenAI Realtime | **Status:** Pending | **Owner:** Voice team

## Entry criteria

- [x] Provider system designed (Phase 7)
- [x] Gateway running (Phase 2) — OR standalone CLI acceptable first
- [x] OpenAI API key with Realtime API access
- [x] Python `openai` SDK >= 1.0 (or TypeScript equivalent)

## Implementation

### API overview

OpenAI Realtime API provides:
- WebSocket-based audio-in/audio-out
- Built-in VAD (configurable)
- Turn detection (configurable silence threshold)
- Function calling during audio session
- Voice options (alloy, echo, shimmer, verse, ballad, etc.)
- **Latency: 200-600ms** end-to-end

### Mode 1: Standalone CLI

```python
# ~/code/voice-agent/v2/providers/openai_realtime.py

import asyncio
import base64
import json
import pyaudio
import websockets

class OpenAIRealtimeClient:
    """Direct OpenAI Realtime API client.
    
    Uses WebSockets (wss://api.openai.com/v1/realtime)
    with the standard Realtime API protocol.
    """
    
    def __init__(self, api_key: str, model: str = "gpt-4o-realtime-preview-2024-12-17"):
        self.api_key = api_key
        self.model = model
        self.ws = None
        
    async def connect(self):
        url = "wss://api.openai.com/v1/realtime"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        self.ws = await websockets.connect(url, extra_headers=headers)
        
        # Initialize session
        await self.ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": "You are a helpful voice assistant.",
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "silence_duration_ms": 500,
                },
            }
        }))
        
        # Start conversation
        await self.ws.send(json.dumps({
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
            }
        }))
        
    async def send_audio(self, pcm_data: bytes):
        """Send a chunk of PCM16 audio data."""
        if self.ws:
            await self.ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(pcm_data).decode(),
            }))
            
    async def receive(self) -> AsyncIterator[dict]:
        """Receive events from the Realtime API."""
        async for message in self.ws:
            event = json.loads(message)
            event_type = event.get("type", "")
            
            if event_type == "response.audio.delta":
                audio_bytes = base64.b64decode(event["delta"])
                yield {"type": "audio", "data": audio_bytes}
                
            elif event_type == "response.audio.done":
                yield {"type": "audio_done"}
                
            elif event_type == "response.text.delta":
                yield {"type": "text", "text": event["delta"]}
                
            elif event_type == "response.done":
                yield {"type": "turn_complete"}
                
            elif event_type == "error":
                yield {"type": "error", "message": event["error"]["message"]}
                
    async def interrupt(self):
        """Clear the audio buffer and cancel the current response."""
        if self.ws:
            await self.ws.send(json.dumps({
                "type": "response.cancel"
            }))
            await self.ws.send(json.dumps({
                "type": "input_audio_buffer.clear"
            }))
```

### Mode 2: Gateway integration

```typescript
// ~/code/voice-agent/gateway/src/providers/openai-realtime.ts

import OpenAI from 'openai';

export class OpenAIRealtimeProvider implements VoiceProvider {
  private ws: WebSocket | null = null;
  
  async init(session: Session): Promise<void> {
    // Connect to OpenAI Realtime API via WebSocket
    // Relay bidirectional audio through gateway
    // Capture latency metrics at gateway level
  }
  
  async handleAudio(data: ArrayBuffer): Promise<void> {
    // Forward PCM16 audio to OpenAI
  }
}
```

### Voice options

| Voice | Description |
|---|---|
| `alloy` | Neutral, warm |
| `echo` | Male, resonant |
| `shimmer` | Female, bright |
| `verse` | Male, deep |
| `ballad` | Female, soft |

### Turn detection configuration

```json
{
  "type": "server_vad",
  "threshold": 0.5,
  "silence_duration_ms": 500,
  "prefix_padding_ms": 300,
  "silence_duration_ms": 500,
  "create_response": true
}
```

## Exit criteria

- [ ] `python -m echo_node.providers.openai_realtime` starts a live voice session
- [ ] User speaks, OpenAI responds in <800ms (target 200-600ms)
- [ ] Interruption works
- [ ] Session ends cleanly
- [ ] Gateway integration forwards audio bidirectionally
- [ ] Latency metrics captured and reported
- [ ] Voice can be switched via config
- [ ] Function calling works during audio session
