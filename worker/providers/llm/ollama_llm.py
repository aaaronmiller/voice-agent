"""
Ollama LLM Provider

Local LLM inference via Ollama API.
Supports streaming, function calling, multiple models.
"""

import asyncio
import json
from typing import AsyncIterator
import aiohttp

from worker.providers.base import LLMProvider


class OllamaLLM(LLMProvider):
    """
    Ollama LLM provider.
    
    Features:
    - Local inference (no API key needed)
    - Streaming responses
    - Function calling support
    - Multiple model variants
    """

    def __init__(self):
        self._base_url = "http://localhost:11434"
        self._model = "llama3.2:7b-q4_K_M"
        self._session: aiohttp.ClientSession | None = None
        self._vram_mb = 0

    @property
    def vram_requirement_mb(self) -> int:
        """
        Estimated VRAM requirement.
        
        Returns:
            VRAM in MB (varies by model: ~4GB for 7B q4, ~8GB for 13B q4)
        """
        return self._vram_mb if self._vram_mb > 0 else 4096  # Default 4GB for 7B

    async def initialize(self, model: str = "", base_url: str = "", api_key: str = "") -> None:
        """
        Initialize Ollama connection.
        
        Args:
            model: Model name (e.g., "llama3.2:7b-q4_K_M")
            base_url: Ollama API base URL
            api_key: Not needed for Ollama (ignored)
        """
        self._model = model or self._model
        self._base_url = base_url or self._base_url
        
        # Create HTTP session
        self._session = aiohttp.ClientSession()
        
        # Verify Ollama is running
        try:
            async with self._session.get(f"{self._base_url}/api/tags") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m['name'] for m in data.get('models', [])]
                    print(f"[OllamaLLM] Connected, available models: {models}")
                    
                    if self._model not in models:
                        print(f"[OllamaLLM] Warning: Model '{self._model}' not found. Pull with: ollama pull {self._model}")
                else:
                    print(f"[OllamaLLM] Warning: Ollama returned {resp.status}")
        except Exception as e:
            print(f"[OllamaLLM] Warning: Could not connect to Ollama: {e}")
        
        # Estimate VRAM based on model
        if "7b" in self._model.lower():
            self._vram_mb = 4096  # ~4GB for 7B quantized
        elif "13b" in self._model.lower():
            self._vram_mb = 8192  # ~8GB for 13B quantized
        elif "70b" in self._model.lower():
            self._vram_mb = 40960  # ~40GB for 70B quantized
        else:
            self._vram_mb = 4096  # Default

    async def chat_stream(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[str]:
        """
        Stream response tokens from LLM.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool/function definitions
        
        Yields:
            Response tokens (strings)
        """
        if not self._session:
            raise RuntimeError("LLM not initialized. Call initialize() first.")
        
        # Build request
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
        }
        
        if tools:
            payload["tools"] = tools
        
        # Stream request
        async with self._session.post(
            f"{self._base_url}/api/chat",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=120)
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise RuntimeError(f"Ollama error: {resp.status} - {error_text}")
            
            # Read streaming response
            async for line in resp.content:
                line = line.decode('utf-8').strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    
                    # Extract token from response
                    if 'message' in data and 'content' in data['message']:
                        content = data['message']['content']
                        if content:
                            yield content
                    
                    # Check for done
                    if data.get('done', False):
                        break
                        
                except json.JSONDecodeError:
                    continue

    async def shutdown(self) -> None:
        """Release resources."""
        if self._session:
            await self._session.close()
            self._session = None
        print("[OllamaLLM] Shutdown complete")
