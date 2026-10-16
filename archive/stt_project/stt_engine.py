import torch
from transformers import WhisperProcessor, WhisperForConditionalGeneration
import librosa
import requests
from threading import Thread
import time
from logger import setup_logger

logger = setup_logger(__name__)

class STTEngine:
    def __init__(self, model_size="tiny", openrouter_api_key="", openrouter_model="openai/whisper-large-v3"):
        """Initialize STT Engine

        Args:
            model_size: "tiny", "base", "small" (recommended for 4GB)
            openrouter_api_key: API key for OpenRouter fallback
            openrouter_model: Model to use on OpenRouter
        """
        self.model_size = model_size
        self.openrouter_api_key = openrouter_api_key
        self.openrouter_model = openrouter_model
        self.device = torch.device("cpu")

        # Load local model
        try:
            logger.info(f"Loading Whisper {model_size} model...")
            model_name = f"openai/whisper-{model_size}"
            self.processor = WhisperProcessor.from_pretrained(model_name)
            self.model = WhisperForConditionalGeneration.from_pretrained(model_name)
            self.model = self.model.to(self.device)
            self.model.eval()
            logger.info(f"Whisper {model_size} loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load local model: {e}")
            self.model = None

    def transcribe_local(self, audio_path, timeout=5):
        """Transcribe using local Whisper model

        Args:
            audio_path: Path to audio file
            timeout: Maximum time in seconds for transcription

        Returns:
            Transcribed text or None if timeout
        """
        if self.model is None:
            logger.warning("Local model not loaded")
            return None

        result = {"text": None, "error": None}

        def _transcribe():
            try:
                logger.info(f"Transcribing locally: {audio_path}")
                audio_data, sr = librosa.load(audio_path, sr=16000)

                inputs = self.processor(
                    audio_data,
                    sampling_rate=16000,
                    return_tensors="pt",
                    language="en"
                )
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

                with torch.no_grad():
                    predicted_ids = self.model.generate(**inputs)

                transcription = self.processor.batch_decode(
                    predicted_ids,
                    skip_special_tokens=True
                )[0]

                result["text"] = transcription
                logger.info(f"Local transcription: {transcription[:100]}...")
            except Exception as e:
                result["error"] = str(e)
                logger.error(f"Local transcription error: {e}")

        # Run in thread with timeout
        thread = Thread(target=_transcribe, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if result["text"] is None and result["error"] is None:
            logger.warning(f"Local transcription timeout after {timeout}s")
            return None

        return result["text"]

    def transcribe_remote(self, audio_path):
        """Transcribe using OpenRouter API

        Args:
            audio_path: Path to audio file

        Returns:
            Transcribed text or None if error
        """
        if not self.openrouter_api_key:
            logger.warning("OpenRouter API key not configured")
            return None

        try:
            logger.info(f"Transcribing remotely via OpenRouter: {audio_path}")

            with open(audio_path, 'rb') as f:
                files = {'file': f}
                headers = {'Authorization': f'Bearer {self.openrouter_api_key}'}
                data = {'model': self.openrouter_model}

                response = requests.post(
                    'https://openrouter.ai/api/v1/audio/transcriptions',
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=30
                )

            if response.status_code == 200:
                transcription = response.json().get('text', '')
                logger.info(f"Remote transcription: {transcription[:100]}...")
                return transcription
            else:
                logger.error(f"OpenRouter error: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Remote transcription error: {e}")
            return None

    def transcribe(self, audio_path, local_timeout=5, use_local_first=True):
        """Transcribe with fallback strategy

        Args:
            audio_path: Path to audio file
            local_timeout: Timeout for local transcription
            use_local_first: Try local first, fallback to remote

        Returns:
            Transcribed text
        """
        logger.info(f"Starting transcription pipeline for {audio_path}")

        if use_local_first:
            logger.info("Attempting local transcription...")
            text = self.transcribe_local(audio_path, timeout=local_timeout)

            if text:
                logger.info("Local transcription successful")
                return text

            logger.info("Local transcription failed/timeout, trying remote...")
            text = self.transcribe_remote(audio_path)

            if text:
                logger.info("Remote transcription successful")
                return text

            logger.error("All transcription methods failed")
            return None
        else:
            # Use remote only
            return self.transcribe_remote(audio_path)
