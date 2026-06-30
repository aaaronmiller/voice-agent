"""Conversation audit logger for Echo-Node v2.

Records every turn with per-stage timestamps so we can measure:

  wake → stt_start → stt_done → llm_start → llm_first_token
  → llm_done → tts_start → tts_done → playback_start → playback_done

Each session is saved as a JSON file in the configured log directory.
A live summary is printed to stderr after every turn.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ── Latency probe ───────────────────────────────────────────────────

class Timer:
    """Lightweight wall-clock probe that can be started & stopped.

    Usage
    -----
    t = Timer().start("stt")
    ...
    t.stop("stt")
    t.pp()  # print all measured intervals
    """

    def __init__(self) -> None:
        self._marks: dict[str, float] = {}

    def start(self, name: str) -> "Timer":
        self._marks[name] = time.perf_counter()
        return self

    def stop(self, name: str) -> float:
        t = time.perf_counter()
        start = self._marks.pop(name, None)
        if start is None:
            return 0.0
        return t - start

    def elapsed(self, name: str) -> float:
        """Return elapsed since *name* was started (without stopping it)."""
        start = self._marks.get(name)
        if start is None:
            return 0.0
        return time.perf_counter() - start

    def pp(self) -> str:
        if not self._marks:
            return ""
        now = time.perf_counter()
        parts = [f"{k}={now - v:.2f}s" for k, v in sorted(self._marks.items())]
        return " ".join(parts)


# ── Per-turn record ─────────────────────────────────────────────────

@dataclass
class TurnRecord:
    turn_id: int = 0

    # Raw texts
    user_text: str = ""
    assistant_text: str = ""
    route: str = ""

    # Absolute wall timestamps (monotonic)
    t_wake: float = 0.0
    t_listen_start: float = 0.0
    t_listen_done: float = 0.0
    t_stt_start: float = 0.0
    t_stt_done: float = 0.0
    t_llm_start: float = 0.0
    t_llm_first_token: float = 0.0
    t_llm_done: float = 0.0
    t_tts_start: float = 0.0
    t_tts_first_chunk: float = 0.0
    t_tts_done: float = 0.0
    t_playback_start: float = 0.0
    t_playback_done: float = 0.0
    t_turn_done: float = 0.0

    # Derived latencies (seconds)
    latency_wake_to_listen: float = 0.0
    latency_vad: float = 0.0          # listen_start → listen_done (how long user spoke)
    latency_stt: float = 0.0          # stt_start → stt_done
    latency_llm: float = 0.0          # llm_start → llm_done
    latency_llm_first_token: float = 0.0  # llm_start → llm_first_token
    latency_tts: float = 0.0          # tts_start → tts_done
    latency_playback: float = 0.0     # playback_start → playback_done
    latency_turn_total: float = 0.0   # wake → turn_done
    latency_ears_to_mouth: float = 0.0  # listen_done → playback_start

    # Extra diagnostics
    stt_model: str = ""
    tts_provider: str = ""
    llm_model: str = ""
    interrupted: bool = False
    error: str = ""
    audio_duration: float = 0.0       # duration of recorded WAV (s)

    def __str__(self) -> str:
        """Compact one-line summary for the terminal."""
        parts = [
            f"turn={self.turn_id}",
            f"route={self.route}",
        ]
        if self.latency_turn_total:
            parts.append(f"total={self.latency_turn_total:.1f}s")
        if self.latency_ears_to_mouth:
            parts.append(f"ears→mouth={self.latency_ears_to_mouth:.1f}s")
        if self.latency_stt:
            parts.append(f"stt={self.latency_stt:.2f}s")
        if self.latency_llm:
            parts.append(f"llm={self.latency_llm:.1f}s")
        if self.latency_llm_first_token:
            parts.append(f"first_token={self.latency_llm_first_token:.1f}s")
        if self.latency_tts:
            parts.append(f"tts={self.latency_tts:.2f}s")
        if self.latency_playback:
            parts.append(f"play={self.latency_playback:.1f}s")
        if self.interrupted:
            parts.append("INTERRUPTED")
        if self.error:
            parts.append(f"ERR={self.error}")
        return " | ".join(parts)

    def derive_latencies(self) -> None:
        """Compute derived latencies from raw timestamps."""
        t = self  # alias

        if t.t_listen_start and t.t_wake:
            t.latency_wake_to_listen = t.t_listen_start - t.t_wake
        if t.t_listen_done and t.t_listen_start:
            t.latency_vad = t.t_listen_done - t.t_listen_start
        if t.t_stt_done and t.t_stt_start:
            t.latency_stt = t.t_stt_done - t.t_stt_start
        if t.t_llm_done and t.t_llm_start:
            t.latency_llm = t.t_llm_done - t.t_llm_start
        if t.t_llm_first_token and t.t_llm_start:
            t.latency_llm_first_token = t.t_llm_first_token - t.t_llm_start
        if t.t_tts_done and t.t_tts_start:
            t.latency_tts = t.t_tts_done - t.t_tts_start
        if t.t_playback_done and t.t_playback_start:
            t.latency_playback = t.t_playback_done - t.t_playback_start
        if t.t_turn_done and t.t_wake:
            t.latency_turn_total = t.t_turn_done - t.t_wake
        if t.t_playback_start and t.t_listen_done:
            t.latency_ears_to_mouth = t.t_playback_start - t.t_listen_done


# ── Session logger ──────────────────────────────────────────────────

class ConversationLogger:
    """Collects per-turn records and writes them to a JSON log file.

    Caller is responsible for creating a TurnRecord and calling
    ``log.end_turn(record)`` after each assistant response.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        log_dir = str(self.config.get("log_dir", "logs") or "logs")
        self.log_dir = Path(log_dir).resolve()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = time.strftime("session_%Y%m%d_%H%M%S")
        self.path = self.log_dir / f"{self.session_id}.jsonl"
        self._turn_count = 0
        self._records: list[TurnRecord] = []
        self._handle = open(self.path, "w", encoding="utf-8")
        print(f"[logger] auditing to {self.path}", flush=True)

    def new_turn(self, route: str = "") -> TurnRecord:
        self._turn_count += 1
        return TurnRecord(turn_id=self._turn_count, route=route)

    def end_turn(self, rec: TurnRecord) -> None:
        rec.t_turn_done = time.perf_counter()
        rec.derive_latencies()
        self._records.append(rec)
        self._write(rec)
        # Print latency summary to terminal
        print(f"[perf] {rec}", flush=True)

    def _write(self, rec: TurnRecord) -> None:
        d = asdict(rec)
        # Convert float timestamps to relative offsets for readability
        first = d.pop("t_wake", 0.0) or rec.t_wake
        d["timestamps_ms"] = {
            k: round((v - first) * 1000, 1)
            for k, v in sorted(d.items())
            if k.startswith("t_") and isinstance(v, (int, float)) and v
        }
        d.pop("t_turn_done", None)
        d["latencies_s"] = {
            k.replace("latency_", ""): round(v, 3)
            for k, v in sorted(d.items())
            if k.startswith("latency_") and isinstance(v, (int, float)) and v
        }
        # Strip raw timestamps from the JSONL version (keep latencies)
        for k in list(d.keys()):
            if k.startswith("t_"):
                del d[k]
        d["session_id"] = self.session_id
        d["timestamp_iso"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._handle.write(json.dumps(d, default=str) + "\n")
        self._handle.flush()

    def summary(self) -> str:
        """Return a human-readable latency summary across all turns."""
        if not self._records:
            return "No turns recorded."
        lines = ["", "── Latency Summary ──"]
        for key, label, fmt in [
            ("latency_wake_to_listen", "Wake→Listen", ".2f"),
            ("latency_vad", "User spoke for", ".1f"),
            ("latency_stt", "STT", ".2f"),
            ("latency_llm", "LLM total", ".1f"),
            ("latency_llm_first_token", "LLM→first token", ".1f"),
            ("latency_tts", "TTS synth", ".2f"),
            ("latency_playback", "Playback", ".1f"),
            ("latency_ears_to_mouth", "Ears→Mouth (listening done → playback)", ".1f"),
            ("latency_turn_total", "Total turn", ".1f"),
        ]:
            vals = [getattr(r, key) for r in self._records if getattr(r, key, 0) > 0]
            if not vals:
                continue
            avg = sum(vals) / len(vals)
            mx = max(vals)
            lines.append(f"  {label:30s}  avg={avg:{fmt}}s  max={mx:{fmt}}s")
        lines.append(f"  {'Turns':30s}  n={len(self._records)}")
        lines.append(f"  {'Log':30s}  {self.path}")
        lines.append("")
        return "\n".join(lines)

    def close(self) -> None:
        print(self.summary(), flush=True)
        self._handle.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


# ── Latency budget breakdown ────────────────────────────────────────

def latency_budget(rec: TurnRecord) -> str:
    """Return a visual bar chart of where time went in a single turn."""
    total = rec.latency_turn_total or 1.0
    segments = [
        ("VAD", rec.latency_vad),
        ("STT", rec.latency_stt),
        ("LLM", rec.latency_llm),
        ("TTS", rec.latency_tts),
        ("Play", rec.latency_playback),
    ]
    scale = 40.0 / total
    bars = []
    for label, val in segments:
        if val <= 0:
            continue
        bar_len = max(1, int(val * scale))
        pct = val / total * 100
        bars.append(f"  {label:6s} {'█' * bar_len}  {val:.1f}s ({pct:.0f}%)")
    remaining = total - sum(v for _, v in segments if v > 0)
    if remaining > 0.1:
        bars.append(f"  {'Other':6s} {'░' * max(1, int(remaining * scale))}  {remaining:.1f}s")
    bars.append(f"  {'TOTAL':6s} {'=' * max(1, int(total * scale))}  {total:.1f}s")
    return "\n".join(bars)
