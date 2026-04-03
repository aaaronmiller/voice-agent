"""
OpenAI-Compatible LLM Provider

Universal LLM client for any OpenAI-compatible API.
Supports: Ollama, OpenRouter, OpenAI, Hermes Agent, etc.
"""

import asyncio
from typing import AsyncIterator
import aiohttp
import json

from worker.providers.base import LLMProvider


class OpenAICompatLLM(LLMProvider):
    """
    OpenAI-compatible LLM provider.
    
    Supports:
    - Ollama (local)
    - OpenRouter (multi-model)
    - OpenAI API
    - Hermes Agent
    - Any OpenAI-compatible endpoint
    """

    def __init__(self):
        self._base_url = "http://localhost:11434/v1"
        self._model = "llama3.2:7b"
        self._api_key = ""
        self._session: aiohttp.ClientSession | None = None
        self._vram_mb = 0  # Cloud API = 0 local VRAM

    @property
    def vram_requirement_mb(self) -> int:
        """
        VRAM requirement for cloud API.
        
        Returns:
            0 (inference happens on server)
        """
        return 0

    async def initialize(self, model: str = "", base_url: str = "", api_key: str = "") -> None:
        """
        Initialize OpenAI-compatible client.
        
        Args:
            model: Model name (e.g., "gpt-4o", "claude-sonnet-4-20250514", "llama3.2:7b")
            base_url: API base URL
            api_key: API key (optional for local, required for cloud)
        """
        self._model = model or self._model
        self._base_url = base_url or self._base_url
        self._api_key = api_key or ""
        
        # Create HTTP session
        self._session = aiohttp.ClientSession(
            headers=self._get_headers()
        )
        
        # Test connection
        try:
            async with self._session.get(f"{self._base_url}/models") as resp:
                if resp.status == 200:
                    print(f"[OpenAICompat] ✅ Connected to {self._base_url}")
                else:
                    print(f"[OpenAICompat] Warning: API returned {resp.status}")
        except Exception as e:
            print(f"[OpenAICompat] Warning: Could not connect: {e}")

    def _get_headers(self) -> dict:
        """Build request headers."""
        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

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
            f"{self._base_url}/chat/completions",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=120)
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise RuntimeError(f"API error: {resp.status} - {error_text}")
            
            # Read streaming response (OpenAI format)
            async for line in resp.content:
                line = line.decode('utf-8').strip()
                
                # Skip empty lines
                if not line:
                    continue
                
                # Parse SSE format: "data: {...}"
                if line.startswith("data: "):
                    data_str = line[6:]  # Remove "data: " prefix
                    
                    # Check for [DONE]
                    if data_str.strip() == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(data_str)
                        
                        # Extract token from delta
                        if 'choices' and len(data['choices']) > 0:
                            delta = data['choices'][0].get('delta', {})
                            content = delta.get('content', '')
                            if content:
                                yield content
                                
                    except json.JSONDecodeError:
                        continue

    async def shutdown(self) -> None:
        """Release resources."""
        if self._session:
            await self._session.close()
            self._session = None
        print("[OpenAICompat] Shutdown complete")
