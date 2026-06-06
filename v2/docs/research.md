# v2 Research Notes

## Practical Choice

For this local build, the best fit is a lean Pipecat-like local pipeline without
requiring Pipecat itself as a hard runtime dependency:

- Parakeet v2 is a strong local English ASR model and is available through ONNX.
- Kokoro ONNX is the preferred local TTS because it is small and fast.
- OpenWakeWord provides open local wake-word detection.
- Silero VAD provides speech/silence and barge-in triggering.
- Ollama/OpenAI-compatible routing keeps the conversation model swappable.

## Alternatives

- Pipecat: best Python graph framework when you want to build many processors and
  transports.
- LiveKit Agents: best when WebRTC, rooms, remote clients, adaptive interruption,
  and network media quality matter.
- TEN Framework: broad multimodal graph platform with more operational overhead.
- Open Voice OS: full assistant ecosystem with skills, heavier than this package.

## Benefits and Trade-Offs

| Option | Benefits | Trade-offs |
| --- | --- | --- |
| Echo-Node v2 local pipeline | Lowest overhead, direct `arecord`/`aplay` audio, works without Docker, easy to hack, Parakeet/Kokoro are local | Less polished than Pipecat/LiveKit, barge-in is VAD-based and can false-trigger from speaker echo |
| Pipecat | Mature processor graph, strong turn-management concepts, easy to add custom Python processors | Local audio setup still needs care, additional framework API surface |
| LiveKit Agents | Best remote/WebRTC path, documented interruption modes, room-based clients | More infrastructure, not as lean for a single local terminal assistant |
| TEN Framework | Rich multimodal/conversational agent framework | Highest operational complexity for this immediate local need |
| OVOS | Full assistant ecosystem and skills | Heavier daemon-style assistant, less ideal for a custom coding companion pipeline |

## Future Build Ideas

- Add semantic interruption filtering so coughs and backchannels do not always kill playback.
- Add speaker verification to reject TV/speaker echo during barge-in.
- Add a Pipecat backend profile once local audio and Kokoro wrappers are stable.
- Add a LiveKit profile for browser/phone clients and WebRTC echo cancellation.
- Add screen-context capture for coding help.
- Add a local RAG node for project docs and Obsidian notes.
- Add provider profiles for Ollama, LM Studio, llama.cpp server, OpenRouter, OpenAI,
  Gemini Live, and local Hermes/OpenClaw endpoints.

## Hardware Fit

Surface Laptop Studio 2 with RTX 4050 has 6GB VRAM in the Microsoft specs. Keep
STT and TTS on CPU/ONNX by default, and reserve GPU memory for the conversational
LLM if you use one. A 12B 4-bit model generally needs partial offload rather than
full GPU residency on 6GB VRAM.

The current v2 implementation was validated with:

- `arecord -D default`: 32,000 bytes captured for one second at 16 kHz mono.
- `aplay -D default`: played a real Kokoro-generated WAV.
- Parakeet v2: transcribed a real sample WAV.
- Kokoro ONNX: generated a real WAV from text.
