"""Shared helpers for echo_node components and pipeline stages.

Single source of truth for the small utilities the old monolith defined at
module level (rms, text chunking, backend error phrasing).
"""

from __future__ import annotations

import math
import re

import numpy as np
import requests


def rms_int16(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    values = samples.astype(np.float32)
    return float(math.sqrt(float(np.mean(values * values))))


def sentence_chunks(text: str, max_chars: int = 240) -> list[str]:
    pieces = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]
    chunks: list[str] = []
    current = ""
    for piece in pieces or [text.strip()]:
        if len(current) + len(piece) + 1 <= max_chars:
            current = f"{current} {piece}".strip()
        else:
            if current:
                chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks


def pop_speakable_chunk(text: str, max_chars: int = 240) -> tuple[str, str] | None:
    stripped = text.strip()
    if not stripped:
        return None
    match = re.search(r"(?<=[.!?])\s+", text)
    if match:
        return text[: match.end()].strip(), text[match.end() :]
    if len(stripped) >= max_chars:
        split_at = text.rfind(" ", 0, max_chars)
        if split_at <= 0:
            split_at = max_chars
        return text[:split_at].strip(), text[split_at:].lstrip()
    return None


def backend_error_message(exc: Exception) -> str:
    """TTS-safe phrasing for a failed backend call.

    Raw tracebacks and "[X error] ..." strings must never reach the speaker —
    the assistant would read them aloud. Use this on every backend error path.
    """
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        if status == 402:
            return "The configured backend requires credits or payment for that model."
        if status == 429:
            return "The configured backend is rate limiting this model. Try again later or switch models."
        if status == 401:
            return "The configured backend rejected the API key."
        if status == 404:
            return "The configured backend could not find that model."
        return f"The configured backend returned HTTP {status}."
    return f"The configured backend did not answer: {exc}"
