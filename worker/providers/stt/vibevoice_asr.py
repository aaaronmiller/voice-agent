"""
VibeVoice ASR Provider

Cloud-based speech recognition using VibeVoice API.
7B model with support for 51 languages.
"""

import json
import base64
from typing import AsyncIterator
import aiohttp

from worker.providers.base import STTProvider


class VibeVoiceASR(STTProvider):
    """
    VibeVoice cloud ASR provider.

    Features:
    - 7B parameter model
    - 51 language support
    - Cloud-based (no local VRAM needed)
    - Streaming transcription
    """

    def __init__(self):
        self._api_key = ""
        self._base_url = "https://api.vibevoice.ai/v1"
        self._language = "en-US"
        self._session: aiohttp.ClientSession | None = None
        self._vram_mb = 0  # Cloud-based, no local VRAM
        self._stream_buffer = b""

    @property
    def vram_requirement_mb(self) -> int:
        """No local VRAM - cloud-based service."""
        return 0

    async def initialize(
        self,
        model_path: str = "",
        device: str = "cloud",
        api_key: str = "",
        language: str = "en-US",
    ) -> None:
        """
        Initialize VibeVoice ASR.

        Args:
            model_path: Not used (cloud model)
            device: Not used
            api_key: VibeVoice API key
            language: Language code (e.g., "en-US", "zh-CN")
        """
        self._api_key = api_key
        self._language = language

        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
        )

        print(f"[VibeVoiceASR] Initialized: {self._language}")

    async def recognize_stream(
        self,
        audio_stream: AsyncIterator[bytes],
    ) -> AsyncIterator[tuple[str, bool]]:
        """
        Stream audio for real-time transcription.

        Args:
            audio_stream: Async iterator of audio chunks

        Yields:
            Tuple of (transcript, is_final)
        """
        if not self._session:
            raise RuntimeError("VibeVoiceASR not initialized")

        async def audio_generator():
            async for chunk in audio_stream:
                yield chunk

        try:
            async with self._session.post(
                f"{self._base_url}/asr/stream",
                json={
                    "language": self._language,
                    "format": "raw",
                    "sample_rate": 16000,
                },
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"VibeVoice API error: {resp.status} - {error}")

                async for line in resp.content:
                    line = line.decode("utf-8").strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        if "text" in data:
                            yield data["text"], data.get("is_final", False)
                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            print(f"[VibeVoiceASR] Stream error: {e}")
            raise

    async def recognize(
        self,
        audio: bytes,
    ) -> str:
        """
        Recognize speech from audio bytes.

        Args:
            audio: Raw PCM audio (16kHz, 16-bit, mono)

        Returns:
            Transcribed text
        """
        if not self._session:
            raise RuntimeError("VibeVoiceASR not initialized")

        audio_b64 = base64.b64encode(audio).decode("utf-8")

        try:
            async with self._session.post(
                f"{self._base_url}/asr/recognize",
                json={
                    "audio": audio_b64,
                    "language": self._language,
                    "format": "raw",
                    "sample_rate": 16000,
                },
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"VibeVoice API error: {resp.status} - {error}")

                data = await resp.json()
                return data.get("text", "")

        except Exception as e:
            print(f"[VibeVoiceASR] Recognition error: {e}")
            return ""

    async def shutdown(self) -> None:
        """Release resources."""
        if self._session:
            await self._session.close()
            self._session = None
        print("[VibeVoiceASR] Shutdown complete")


def create_vibevoice_provider(
    api_key: str,
    language: str = "en-US",
) -> VibeVoiceASR:
    """
    Create VibeVoice ASR provider.

    Args:
        api_key: VibeVoice API key
        language: Language code

    Returns:
        VibeVoiceASR instance
    """
    provider = VibeVoiceASR()
    return provider


# Language codes supported by VibeVoice
SUPPORTED_LANGUAGES = [
    "en-US",
    "en-GB",
    "zh-CN",
    "zh-TW",
    "zh-HK",
    "ja-JP",
    "ko-KR",
    "de-DE",
    "fr-FR",
    "es-ES",
    "it-IT",
    "pt-BR",
    "pt-PT",
    "ru-RU",
    "ar-SA",
    "hi-IN",
    "th-TH",
    "vi-VN",
    "id-ID",
    "ms-MY",
    "fil-PH",
    "nl-NL",
    "pl-PL",
    "tr-TR",
    "sv-SE",
    "da-DK",
    "no-NO",
    "fi-FI",
    "el-GR",
    "he-IL",
    "hu-HU",
    "cs-CZ",
    "ro-RO",
    "uk-UA",
    "bg-BG",
    "hr-HR",
    "sk-SK",
    "sl-SI",
    "lt-LT",
    "lv-LV",
    "et-EE",
    "bn-BD",
    "pa-IN",
    "ta-IN",
    "te-IN",
    "mr-IN",
    "kn-IN",
    "gu-IN",
    "ml-IN",
    "or-IN",
    "as-IN",
    "ne-NP",
    "si-LK",
    "my-MM",
    "km-KH",
]
