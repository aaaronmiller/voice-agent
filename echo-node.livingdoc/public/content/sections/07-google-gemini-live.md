# Google Gemini Multimodal Live API

**Phase:** 5 — Gemini Live | **Status:** Pending | **Owner:** Voice team

## Entry criteria

- [x] Provider system designed (Phase 7 overlaps, can be done in parallel)
- [x] Gateway running (Phase 2) — OR a standalone CLI mode is acceptable first
- [x] Google Cloud API key with Gemini Live API enabled
- [x] Python `google-genai` SDK installed (or TypeScript equivalent)

## Implementation

### Approach

Implement Gemini Multimodal Live API as a first-class provider. Two modes:

1. **Standalone CLI mode** (ship first, fast) — direct Python script that connects to Gemini Live, no gateway needed
2. **Gateway-integrated mode** (ship second) — TypeScript module in the gateway that manages WebRTC connections

### Mode 1: Standalone CLI

```python
# ~/code/voice-agent/v2/providers/gemini_live.py

import asyncio
from google import genai
from google.genai import types

class GeminiLiveClient:
    """Direct Gemini Multimodal Live API client.
    
    Latency target: <800ms end-to-end.
    No local STT, no local TTS, no local LLM.
    Gemini handles: speech-in, understanding, speech-out, VAD, interruption.
    """
    
    def __init__(self, api_key: str, model: str = "gemini-3.1-flash-live-preview"):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.session = None
        
    async def start_session(self) -> AsyncIterator[dict]:
        """Start a live session. Yields events from the model."""
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Puck"
                    )
                )
            ),
        )
        
        async with self.client.aio.live.connect(
            model=self.model,
            config=config,
        ) as session:
            self.session = session
            
            # Send audio from mic and receive responses
            async for response in session.receive():
                if response.data:
                    yield {"type": "audio", "data": response.data}
                if response.text:
                    yield {"type": "text", "text": response.text}
                if response.turn_complete:
                    yield {"type": "turn_complete"}
                    
    async def send_audio(self, audio_data: bytes):
        """Send microphone audio to the live session."""
        if self.session:
            await self.session.send(audio_data)
            
    async def interrupt(self):
        """Interrupt the current model response."""
        if self.session:
            await self.session.send(
                types.LiveClientMessage(
                    interruption=types.LiveClientInterruption()
                )
            )
```

### Mode 2: Gateway integration

```typescript
// ~/code/voice-agent/gateway/src/providers/gemini-live.ts

import { GoogleGenAI } from "@google/genai";

export class GeminiLiveProvider implements VoiceProvider {
  private client: GoogleGenAI;
  private session: any = null;
  
  async init(session: Session): Promise<void> {
    this.client = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
    
    // Create WebRTC-style connection
    // Relay SDP offer/answer between frontend and Gemini
    // Once connected, audio flows directly
  }
  
  async handleAudio(data: ArrayBuffer): Promise<void> {
    if (this.session) {
      await this.session.sendAudio(new Uint8Array(data));
    }
  }
  
  // Latency is measured at the gateway level:
  // audio_in → first response audio = ears-to-mouth
}
```

### Latency optimization

Gemini Live's Multimodal Live API processes audio directly:
- No separate STT step
- Model streams audio tokens as they're generated
- VAD and interruption are built-in
- Target: **200-500ms** for simple queries, **<800ms** for complex ones

### Model options

| Model | Voice options | Notes |
|---|---|---|
| `gemini-2.5-flash-native-audio-preview-12-2025` | Puck, Charon, Kore, Fenrir, Aoede | Earlier preview |
| `gemini-3.1-flash-live-preview` | Same voices | Latest, preferred |

## Exit criteria

- [ ] `python -m echo_node.providers.gemini_live` starts a live voice session
- [ ] User speaks, Gemini responds in <800ms
- [ ] Interruption works (user can barge in)
- [ ] Session ends cleanly on Ctrl+C
- [ ] Gateway provider integration forwards audio bidirectionally
- [ ] Latency metrics are captured and reported
- [ ] Fallback to text mode if audio is unavailable
