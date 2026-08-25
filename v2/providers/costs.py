"""
Echo-Node: Cost estimation for voice providers.

Provides per-turn cost estimates and session-level cost tracking
for the standalone CLI providers (Gemini Live, OpenAI Realtime).

Pricing based on published API rates as of mid-2026.

OpenAI Realtime (gpt-4o-realtime-preview):
  Audio input:  ~$0.10/min  ($100/1M tokens, ~1 token/32ms audio)
  Audio output: ~$0.20/min  ($200/1M tokens)
  Text input:   ~$5/1M tokens (~4 chars/token → ~$0.00125/1K chars)
  Text output:  ~$20/1M tokens (~$0.005/1K chars)

Google Gemini Live (gemini-3.1-flash-live-preview):
  Currently FREE during preview period.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class CostEstimate:
    provider: str
    cost_usd: float
    cumulative_usd: float
    audio_input_ms: int = 0
    audio_output_ms: int = 0
    pricing_label: str = ""


# Pricing data: (audio_input_per_ms, audio_output_per_ms, label, is_free)
PROVIDER_PRICING: dict[str, tuple[float, float, str, bool]] = {
    "gemini-live": (0.0, 0.0, "Free (preview)", True),
    "openai-realtime": (
        0.000003125,  # ~$0.10/min
        0.00000625,   # ~$0.20/min
        "$0.30/min",
        False,
    ),
}


class SessionCostTracker:
    """Tracks cumulative costs across a voice session."""

    def __init__(self, provider: str):
        self.provider = provider
        self._cumulative: float = 0.0
        self._turns: int = 0
        pricing = PROVIDER_PRICING.get(provider, (0.0, 0.0, "Unknown", True))
        self._input_rate, self._output_rate, self._label, self._is_free = pricing

    def estimate_turn(self, audio_input_ms: int = 0, audio_output_ms: int = 0) -> CostEstimate:
        """Estimate cost for a turn given audio durations in ms."""
        cost = (audio_input_ms * self._input_rate) + (audio_output_ms * self._output_rate)
        self._cumulative += cost
        self._turns += 1
        return CostEstimate(
            provider=self.provider,
            cost_usd=cost,
            cumulative_usd=self._cumulative,
            audio_input_ms=audio_input_ms,
            audio_output_ms=audio_output_ms,
            pricing_label=self._label if not self._is_free else "Free",
        )

    @property
    def total_cost(self) -> float:
        return self._cumulative

    @property
    def total_turns(self) -> int:
        return self._turns

    @property
    def avg_cost_per_turn(self) -> float:
        return self._cumulative / self._turns if self._turns > 0 else 0.0

    @property
    def label(self) -> str:
        return self._label

    def format_cost(self, cost: float) -> str:
        """Format cost for display."""
        if cost < 0.001:
            return "< $0.001"
        return f"${cost:.4f}"

    def summary(self) -> str:
        """Return a session cost summary string."""
        lines = [
            f"  Cost: {self.format_cost(self._cumulative)} total",
            f"  Avg/turn: {self.format_cost(self.avg_cost_per_turn)}",
            f"  Pricing: {self._label}",
        ]
        return "\n".join(lines)
