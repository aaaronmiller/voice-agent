"""
Provider Registry for Echo-Node

All providers are registered here by category and name.
The factory function create_provider() instantiates providers by name.
"""

from worker.providers.base import STTProvider, TTSProvider, VADProvider, WakeWordProvider, LLMProvider

# Import provider implementations
from worker.providers.stt.sherpa_stt import SherpaSTT
from worker.providers.stt.faster_whisper_stt import FasterWhisperSTT
from worker.providers.stt.vibevoice_asr import VibeVoiceASR
from worker.providers.tts.kokoro_tts import KokoroTTS
from worker.providers.tts.piper_tts import PiperTTS
from worker.providers.vad.silero_vad import SileroVAD
from worker.providers.wake_word.openwakeword import OpenWakeWordProvider
from worker.providers.llm.ollama_llm import OllamaLLM
from worker.providers.llm.openai_compat_llm import OpenAICompatLLM

# Provider registry - maps category + name to provider class
PROVIDER_REGISTRY: dict[str, dict[str, type]] = {
    "stt": {
        "sherpa-onnx": SherpaSTT,
        "faster-whisper": FasterWhisperSTT,
        "vibevoice-asr": VibeVoiceASR,
    },
    "tts": {
        "kokoro": KokoroTTS,
        "piper": PiperTTS,
        # "chatterbox": ChatterboxTTS,  # Phase 4
        # "orpheus": OrpheusTTS,  # Phase 4
    },
    "vad": {
        "silero": SileroVAD,
    },
    "wake_word": {
        "openwakeword": OpenWakeWordProvider,
    },
    "llm": {
        "ollama": OllamaLLM,
        "openai-compat": OpenAICompatLLM,
    },
}


def create_provider(category: str, name: str) -> STTProvider | TTSProvider | VADProvider | WakeWordProvider | LLMProvider:
    """
    Factory: create a provider by category and name.
    
    Args:
        category: One of 'stt', 'tts', 'vad', 'wake_word', 'llm'
        name: Provider name (e.g., 'sherpa-onnx', 'kokoro')
    
    Returns:
        Provider instance implementing the appropriate ABC
    
    Raises:
        ValueError: If category or provider name is unknown
    """
    if category not in PROVIDER_REGISTRY:
        available = list(PROVIDER_REGISTRY.keys())
        raise ValueError(f"Unknown provider category: {category}. Available: {available}")
    
    if name not in PROVIDER_REGISTRY[category]:
        available = list(PROVIDER_REGISTRY[category].keys())
        raise ValueError(f"Unknown {category} provider: {name}. Available: {available}")
    
    provider_class = PROVIDER_REGISTRY[category][name]
    return provider_class()


def get_available_providers(category: str | None = None) -> dict[str, dict[str, type]]:
    """
    Get available providers, optionally filtered by category.
    
    Args:
        category: Optional category filter ('stt', 'tts', etc.)
    
    Returns:
        Dict of provider categories and their registered providers
    """
    if category:
        return {category: PROVIDER_REGISTRY.get(category, {})}
    return PROVIDER_REGISTRY
