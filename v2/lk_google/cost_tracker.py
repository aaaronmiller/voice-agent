"""Cost tracker for Gemini Multimodal Live API calls.

Logs every turn with estimated token usage and cost to a JSONL file.
Provides a running session total displayed at the end.

Pricing (Gemini 2.5 Flash — Multimodal Live API, pay-as-you-go):
  Audio input:  $0.70 / 1M tokens  (~$0.002/sec)
  Audio output: $1.40 / 1M tokens  (~$0.004/sec)
  Text input:   $0.10 / 1M tokens
  Text output:  $0.40 / 1M tokens

Estimates are approximate. Actual billing from Google Cloud may differ.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("echo-node-google.cost")

# ── Cost Constants (Gemini 2.5 Flash Live API) ────────────────────

PRICING = {
    "gemini-2.5-flash-native-audio-preview-12-2025": {
        "audio_input_per_sec": 0.0002,     # $0.0002/second of audio input
        "audio_output_per_sec": 0.0004,    # $0.0004/second of audio output
        "text_input_per_1k": 0.0001,       # $0.0001/1K text input chars
        "text_output_per_1k": 0.0004,      # $0.0004/1K text output chars
    },
    "gemini-3.1-flash-live-preview": {
        "audio_input_per_sec": 0.0003,     # slightly more expensive
        "audio_output_per_sec": 0.0005,
        "text_input_per_1k": 0.00015,
        "text_output_per_1k": 0.0005,
    },
}

# ── Default pricing if model not found ────────────────────────────

DEFAULT_RATES = PRICING["gemini-2.5-flash-native-audio-preview-12-2025"]
FREE_TIER_REQUESTS = 60  # requests/minute free tier limit


@dataclass
class TurnCost:
    """Cost record for a single conversation turn."""
    turn_number: int
    timestamp: float
    agent_state: str  # listening, generating, responding
    
    # Duration estimates
    user_speech_seconds: float = 0.0
    response_seconds: float = 0.0
    
    # Text (if available from transcription)
    user_text: str = ""
    response_text: str = ""
    
    # Token estimates
    estimated_input_chars: int = 0
    estimated_output_chars: int = 0
    
    # Calculated costs
    estimated_cost: float = 0.0
    model: str = ""
    
    # Free tier tracking
    request_count: int = 0
    within_free_tier: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def cost_str(self) -> str:
        if self.within_free_tier:
            return "FREE"
        return f"${self.estimated_cost:.6f}"


@dataclass
class SessionCost:
    """Aggregate cost for an entire session."""
    session_id: str
    start_time: float
    model: str
    turns: list[TurnCost] = field(default_factory=list)
    total_estimated_cost: float = 0.0
    free_tier_requests_used: int = 0
    
    @property
    def duration_seconds(self) -> float:
        return time.time() - self.start_time
    
    @property
    def total_turns(self) -> int:
        return len(self.turns)
    
    def add_turn(self, turn: TurnCost) -> None:
        self.turns.append(turn)
        if not turn.within_free_tier:
            self.total_estimated_cost += turn.estimated_cost
        self.free_tier_requests_used += 1
    
    def summary(self) -> str:
        mins = self.duration_seconds / 60
        return (
            f"📊 Cost Summary\n"
            f"  Session: {self.session_id[:8]}...\n"
            f"  Model: {self.model}\n"
            f"  Duration: {mins:.1f} min\n"
            f"  Turns: {self.total_turns}\n"
            f"  Free tier requests used: {self.free_tier_requests_used}/{FREE_TIER_REQUESTS}/min\n"
            f"  Est. cost: ${self.total_estimated_cost:.4f}"
        )
    
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "duration_seconds": self.duration_seconds,
            "model": self.model,
            "total_turns": self.total_turns,
            "total_estimated_cost": self.total_estimated_cost,
            "free_tier_requests_used": self.free_tier_requests_used,
            "turns": [t.to_dict() for t in self.turns],
        }


class CostTracker:
    """Tracks and logs costs for a Gemini voice session."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash-native-audio-preview-12-2025",
        log_dir: str | Path = "logs",
        session_id: str | None = None,
    ):
        self.model = model
        self.rates = PRICING.get(model, DEFAULT_RATES)
        self.session = SessionCost(
            session_id=session_id or f"gemini-{int(time.time())}",
            start_time=time.time(),
            model=model,
        )
        self._turn_counter = 0
        self._last_state: str = "idle"
        self._state_start = time.time()
        self._user_speech_start: float | None = None
        self._response_start: float | None = None
        
        # Setup log file
        log_path = Path(log_dir)
        log_path.mkdir(exist_ok=True)
        self._log_file = log_path / f"cost-{self.session.session_id}.jsonl"
        logger.info(f"Cost tracking to {self._log_file}")
    
    def on_state_change(self, new_state: str) -> None:
        """Call this when agent state changes: idle→listening→transcribing→working→responding→idle"""
        now = time.time()
        elapsed = now - self._state_start
        
        if new_state == "listening" and self._last_state != "listening":
            self._user_speech_start = now
        elif new_state == "working" and self._last_state == "listening" and self._user_speech_start:
            # User finished speaking
            user_secs = now - self._user_speech_start
            self._response_start = now
            # Estimate input duration
            self._current_turn = TurnCost(
                turn_number=self._turn_counter,
                timestamp=now,
                agent_state="listening",
                user_speech_seconds=user_secs,
                model=self.model,
                request_count=self.session.free_tier_requests_used + 1,
                within_free_tier=self.session.free_tier_requests_used < FREE_TIER_REQUESTS,
            )
        elif new_state == "responding" and self._response_start:
            resp_secs = now - self._response_start
            if hasattr(self, '_current_turn'):
                self._current_turn.response_seconds = resp_secs
                self._current_turn.agent_state = "responding"
                # Estimate costs
                cost = self._estimate_turn_cost(self._current_turn)
                self._current_turn.estimated_cost = cost
                self.session.add_turn(self._current_turn)
                self._write_log(self._current_turn)
                self._turn_counter += 1
                logger.info(
                    f"Turn {self._current_turn.turn_number}: "
                    f"in={self._current_turn.user_speech_seconds:.1f}s "
                    f"out={self._current_turn.response_seconds:.1f}s "
                    f"cost={self._current_turn.cost_str}"
                )
            self._user_speech_start = None
            self._response_start = None
        
        self._last_state = new_state
        self._state_start = now
    
    def _estimate_turn_cost(self, turn: TurnCost) -> float:
        """Estimate cost based on audio duration."""
        # Rough estimate: audio at ~16KB/s = ~400 tokens/s
        # But for Live API, pricing is per-second
        input_cost = turn.user_speech_seconds * self.rates["audio_input_per_sec"]
        output_cost = turn.response_seconds * self.rates["audio_output_per_sec"]
        return input_cost + output_cost
    
    def _write_log(self, turn: TurnCost) -> None:
        """Append a JSONL line for this turn."""
        try:
            with open(self._log_file, "a") as f:
                f.write(json.dumps(turn.to_dict()) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write cost log: {e}")
    
    def final_summary(self) -> str:
        """Return the session cost summary."""
        return self.session.summary()
    
    def close(self) -> None:
        """Log the final session summary."""
        logger.info(f"\n{self.session.summary()}")


# ── Testing ────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Quick test
    tracker = CostTracker(session_id="test-123")
    tracker.on_state_change("listening")
    time.sleep(2)
    tracker.on_state_change("working")
    time.sleep(0.01)
    tracker.on_state_change("responding")
    time.sleep(3)
    tracker.on_state_change("idle")
    print(tracker.final_summary())
    tracker.close()
