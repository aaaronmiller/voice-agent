---
title: Conversational voice research sources
date: 2026-08-15
scope: 60 primary or project-authoritative pages
---

# Conversational voice research sources

The audit reviewed more than 50 distinct documentation, specification, repository, and model pages before cross-harness changes. Primary vendor documentation and upstream project sources received the most weight.

## Harness voice and configuration

1. https://hermes-agent.nousresearch.com/docs/user-guide/features/voice-mode/
2. https://hermes-agent.nousresearch.com/docs/user-guide/features/wake-word
3. https://hermes-agent.nousresearch.com/docs/guides/use-voice-mode-with-hermes
4. https://hermes-agent.nousresearch.com/docs/user-guide/configuration
5. https://hermes-agent.nousresearch.com/docs/user-guide/cli
6. https://hermes-agent.nousresearch.com/docs/user-guide/features/overview/
7. https://hermes-agent.nousresearch.com/docs/reference/tools-reference/
8. https://hermes-agent.nousresearch.com/docs/getting-started/quickstart/
9. https://code.claude.com/docs/en/voice-dictation
10. https://qwenlm.github.io/qwen-code-docs/en/users/configuration/settings/
11. https://qwenlm.github.io/qwen-code-docs/en/users/features/commands/
12. https://qwenlm.github.io/qwen-code-docs/en/blog/updates/weekly-update-2026-06-25/
13. https://qwenlm.github.io/qwen-code-docs/en/blog/updates/weekly-update-2026-07-16/
14. https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/channels/overview.md
15. https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/settings.md
16. https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/tools.md
17. https://github.com/google-gemini/gemini-cli/blob/main/docs/get-started/index.md
18. https://github.com/google-gemini/gemini-cli/blob/main/docs/resources/troubleshooting.md
19. https://github.com/google-gemini/gemini-cli/discussions/21408
20. https://geminicli.com/extensions/
21. https://kilo.ai/docs/code-with-ai/features/speech-to-text
22. https://kilo.ai/docs/getting-started/settings
23. https://kilo.ai/docs/code-with-ai/platforms/cli-reference
24. https://opencode.ai/docs/commands/
25. https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/voice-input
26. https://docs.github.com/en/copilot/how-tos/github-copilot-app/agent-sessions
27. https://learn.chatgpt.com/docs/features/voice

## OpenAI realtime and agent voice

28. https://platform.openai.com/docs/api-reference/realtime
29. https://openai.github.io/openai-agents-python/voice/pipeline/
30. https://openai.github.io/openai-agents-python/voice/quickstart/
31. https://openai.github.io/openai-agents-python/voice/tracing/
32. https://openai.github.io/openai-agents-python/ref/voice/pipeline/
33. https://openai.github.io/openai-agents-python/ref/voice/pipeline_config/
34. https://openai.github.io/openai-agents-python/ref/voice/input/
35. https://openai.github.io/openai-agents-python/ref/voice/events/
36. https://openai.github.io/openai-agents-python/agents/
37. https://openai.github.io/openai-agents-python/examples/

## Gemini Live audio

38. https://ai.google.dev/gemini-api/docs/live-api
39. https://ai.google.dev/gemini-api/docs/live-api/capabilities
40. https://ai.google.dev/gemini-api/docs/live-api/best-practices
41. https://ai.google.dev/gemini-api/docs/live-api/get-started-websocket
42. https://ai.google.dev/gemini-api/docs/live-api/ephemeral-tokens
43. https://ai.google.dev/api/live
44. https://ai.google.dev/gemini-api/docs/tools
45. https://googleapis.github.io/python-genai/index.html
46. https://googleapis.github.io/python-genai/genai.html
47. https://googleapis.github.io/js-genai/release_docs/classes/live.Live.html

## Wake word, VAD, and speaker analysis

48. https://github.com/dscripka/openWakeWord
49. https://github.com/snakers4/silero-vad
50. https://github.com/snakers4/silero-vad/wiki/Quality-Metrics
51. https://k2-fsa.github.io/sherpa/onnx/kws/index.html
52. https://k2-fsa.github.io/sherpa/onnx/c-api/html/keyword_spotting.html
53. https://k2-fsa.github.io/sherpa/onnx/pretrained_models/index.html
54. https://picovoice.ai/docs/porcupine/
55. https://picovoice.ai/docs/quick-start/porcupine-python/
56. https://picovoice.ai/docs/api/porcupine-python/
57. https://github.com/pyannote/pyannote-audio
58. https://github.com/pyannote/pyannote-audio/discussions/1157
59. https://huggingface.co/superb/wav2vec2-base-superb-er

## Agent routing

60. https://agentclientprotocol.com/get-started/architecture
61. https://agentclientprotocol.com/updates
62. https://agentclientprotocol.com/rfds/streamable-http-websocket-transport
63. https://github.com/agentclientprotocol/agent-client-protocol
64. https://github.com/agentclientprotocol/typescript-sdk/blob/main/src/acp.ts
65. https://github.com/agentclientprotocol/python-sdk
66. https://github.com/agentclientprotocol/registry

## Main findings

- Full-duplex conversation needs a live microphone during model work and playback, VAD that can cancel the active response, and echo or speaker-bleed control.
- Dictation inserts text into a prompt. It is not conversational voice even when it uses a realtime transcription backend.
- A local wake engine can stay separate from the STT, TTS, and agent provider. This reduces cost and avoids sending ambient audio to a wake API.
- ACP is suitable for routing completed text turns and receiving streamed agent updates. It is not an audio transport in the current stable architecture.
- Separate emotion classifiers are not reliable enough to control permissions or task execution. Native affective audio, when available, is better treated as conversational context only.
