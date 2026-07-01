"""Session analysis tool — reads session logs and runtime logs, correlates
timestamps with VAD/RMS estimates, and generates tuning recommendations.

Usage:
    source .venv/bin/activate
    python -m avatar.analyze_session [--log v2/logs/session_*.jsonl]

Outputs a markdown report with turn-by-turn breakdown, threshold
analysis, and suggested settings adjustments.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any


def _find_logs(log_dir: str | Path = "logs") -> list[Path]:
    """Find session JSONL logs sorted newest first."""
    p = Path(log_dir)
    return sorted(p.glob("session_*.jsonl"), reverse=True)


def load_turns(log_path: Path) -> list[dict[str, Any]]:
    """Load turns from a JSONL session log."""
    turns: list[dict[str, Any]] = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                turns.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return turns


def _s(val: float | None, digits: int = 2) -> str:
    """Format seconds nicely."""
    if val is None:
        return "N/A"
    return f"{val:.{digits}f}s"


def analyze_turn(t: dict[str, Any]) -> dict[str, Any]:
    """Compute derived metrics for one turn."""
    stages = {}
    for stage in ("wake", "listen_start", "listen_done", "stt_start", "stt_done",
                  "llm_start", "llm_first_token", "llm_done",
                  "tts_start", "tts_first_chunk", "tts_done",
                  "playback_start", "playback_done"):
        stages[stage] = t.get(f"t_{stage}")

    derived = {}
    if stages["listen_start"] and stages["listen_done"]:
        derived["listen_dur"] = stages["listen_done"] - stages["listen_start"]
    if stages["stt_start"] and stages["stt_done"]:
        derived["stt_dur"] = stages["stt_done"] - stages["stt_start"]
    if stages["llm_start"] and stages["llm_done"]:
        derived["llm_dur"] = stages["llm_done"] - stages["llm_start"]
    if stages["tts_start"] and stages["tts_first_chunk"]:
        derived["tts_first"] = stages["tts_first_chunk"] - stages["tts_start"]
    if stages["tts_start"] and stages["tts_done"]:
        derived["tts_dur"] = stages["tts_done"] - stages["tts_start"]
    if stages["playback_start"] and stages["playback_done"]:
        derived["play_dur"] = stages["playback_done"] - stages["playback_start"]
    if stages["wake"] and stages["playback_done"]:
        derived["total"] = stages["playback_done"] - stages["wake"]
    elif stages["wake"] and stages["tts_done"]:
        derived["total"] = stages["tts_done"] - stages["wake"]

    return {**t, "stages": stages, "derived": derived}


BAR_WIDTH = 30


def _bar(pct: float, max_pct: float = 100.0, char: str = "█") -> str:
    """Render a horizontal bar."""
    filled = max(0, min(BAR_WIDTH, int(pct / max_pct * BAR_WIDTH)))
    return char * filled + "░" * (BAR_WIDTH - filled)


def print_turn_report(t: dict[str, Any], idx: int) -> None:
    """Print a human-readable report for one turn."""
    d = t.get("derived", {})
    stages = t.get("stages", {})
    error = t.get("error", "")
    interrupted = t.get("interrupted", False)
    route = t.get("route", "?")
    text = t.get("user_text", "")

    status = "✓"
    if error:
        status = f"✗ {error}"
    elif interrupted:
        status = "⏹ interrupted"

    print(f"\n## Turn {idx}: {status}")
    print(f"- **Route**: {route}")
    if text:
        print(f"- **You**: _{text}_")
    if t.get("assistant_text"):
        print(f"- **Assistant**: {t['assistant_text'][:120]}{'...' if len(t['assistant_text']) > 120 else ''}")

    print("\n### Timings")
    if d.get("total"):
        print(f"- **Total**: {_s(d['total'])}")
    if stages.get("wake"):
        print(f"- Wake→Listen: {_s(stages.get('listen_start', 0) - stages['wake']) if stages.get('listen_start') else 'N/A'}")
    if d.get("listen_dur"):
        print(f"- **Listen (VAD)**: {_s(d['listen_dur'])}")
    if d.get("stt_dur"):
        print(f"- **STT**: {_s(d['stt_dur'])}")
    if d.get("llm_dur"):
        print(f"- **LLM**: {_s(d['llm_dur'])}  "
              f"(first token: {_s(d.get('tts_first', stages.get('llm_first_token')))})")
    if d.get("tts_first"):
        print(f"- **TTS first chunk**: {_s(d['tts_first'])}")
    if d.get("tts_dur"):
        print(f"- **TTS total**: {_s(d['tts_dur'])}")
    if d.get("play_dur"):
        print(f"- **Playback**: {_s(d['play_dur'])}")

    # Threshold analysis
    print("\n### Threshold Analysis")
    tsp = t.get("threshold_snapshot", {})
    if tsp:
        print(f"- Normal VAD threshold: `{tsp.get('threshold', '?')}`")
        print(f"- Boosted (playback):  `{tsp.get('boosted_threshold', '?')}`")
        print(f"- Normal RMS floor:    `{tsp.get('rms_floor', '?')}`")
        print(f"- Boosted RMS:         `{tsp.get('boosted_rms', '?')}`")
        print(f"- Barge-in enabled:    `{tsp.get('barge_in_enabled', '?')}`")
        if interrupted:
            print("\n  ⚠ This turn was **interrupted** — "
                  "likely the assistant's own TTS bleed triggered barge-in.")
            rec = tsp.get("recommendation", "")
            if rec:
                print(f"  → {rec}")

    # Estimate if TTS bleed could cause false trigger
    print("\n### Self-Trigger Risk Assessment")
    threshold = tsp.get("threshold", 0.40) if tsp else 0.40
    boosted = tsp.get("boosted_threshold", threshold * 1.35) if tsp else threshold * 1.35
    rms_floor = tsp.get("rms_floor", 500) if tsp else 500
    boosted_rms = tsp.get("boosted_rms", int(rms_floor * 1.6)) if tsp else int(rms_floor * 1.6)
    
    print(f"- Estimated TTS bleed VAD: **0.30–0.55** (crosses normal {threshold:.2f}? {'⚠ yes' if threshold < 0.55 else '✓ no'})")
    print(f"- TTS bleed at boosted {boosted:.2f}? {'⚠ could still cross' if threshold * 1.35 < 0.55 else '✓ blocked by AND gate'}")
    print(f"- Estimated human speech VAD: **0.50–0.85** (crosses boosted? {'✓ yes' if boosted < 0.85 else '✗ deaf'})")
    print(f"- AND gate (both VAD + RMS needed): {'active' if t.get('and_gate', True) else 'inactive'}")


def generate_recommendations(turns: list[dict[str, Any]]) -> list[str]:
    """Analyze all turns and suggest settings changes."""
    recs: list[str] = []
    interrupted_count = sum(1 for t in turns if t.get("interrupted"))
    total = len(turns)
    empty_count = sum(1 for t in turns if t.get("error") == "empty_transcription")
    no_speech_count = sum(1 for t in turns if t.get("error") == "no_speech")

    if total == 0:
        return ["No turns recorded — nothing to analyze."]

    # Latency
    totals = []
    for t in turns:
        d = t.get("derived", {})
        if d.get("total"):
            totals.append(d["total"])
    if totals:
        avg_total = sum(totals) / len(totals)
        recs.append(f"- Average turn time: **{avg_total:.1f}s** "
                    f"(target: <15s). {'Consider faster LLM or TTS model.' if avg_total > 20 else 'Good.'}")

    # Interruption rate
    if total > 0:
        pct = interrupted_count / total * 100
        recs.append(f"- **{interrupted_count}/{total}** turns interrupted ({pct:.0f}%)")
        if pct > 30:
            recs.append("  ⚠ High interruption rate. Options:")
            recs.append("    a) **Increase playback_threshold_boost** (1.35 → 1.5)")
            recs.append("    b) **Increase playback_rms_boost** (1.6 → 2.0)")
            recs.append("    c) **Enable AND gate** (already on in latest code — ensure running new version)")
        elif pct > 10:
            recs.append("  ⚡ Moderate interruptions — boost may need slight tuning.")
        else:
            recs.append("  ✓ Interruption rate is acceptable.")

    # Empty transcriptions
    if empty_count > 0:
        pct = empty_count / total * 100
        recs.append(f"- **{empty_count}/{total}** empty transcriptions ({pct:.0f}%)")
        if pct > 20:
            recs.append("  ⚠ Lower **speech_threshold** (0.40 → 0.35) or reduce **silence_seconds**")

    # No speech detected
    if no_speech_count > 0:
        recs.append(f"- **{no_speech_count}/{total}** turns with no speech detected")
        recs.append("  → Lower VAD threshold or check mic levels")

    return recs


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Echo-Node session logs")
    parser.add_argument("--log", "-l", type=str, default=None,
                        help="Path to session JSONL log file")
    parser.add_argument("--dir", "-d", type=str, default=None,
                        help="Log directory (default: v2/logs)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON for programmatic consumption")
    args = parser.parse_args()

    if args.log:
        log_paths = [Path(args.log)]
    else:
        log_dir = args.dir or (Path(__file__).resolve().parent.parent / "logs")
        log_paths = _find_logs(log_dir)
        if not log_paths:
            print(f"No session logs found in {log_dir}")
            return 1

    all_turns: list[dict[str, Any]] = []
    for lp in log_paths:
        turns = load_turns(lp)
        if turns:
            print(f"Loaded {len(turns)} turns from {lp.name}", file=sys.stderr)
            all_turns.extend(turns)

    if not all_turns:
        print("No turns found in logs.")
        return 0

    analyzed = [analyze_turn(t) for t in all_turns]

    if args.json:
        print(json.dumps({"turns": analyzed, "count": len(analyzed)}, indent=2))
        return 0

    # ── Print report ──
    print("# Echo-Node Session Analysis")
    print(f"\n**{len(analyzed)} turns** across {len(log_paths)} session(s)\n")
    print("---")

    for i, t in enumerate(analyzed):
        print_turn_report(t, i)

    print("\n---")
    print("\n## Recommendations\n")
    for r in generate_recommendations(analyzed):
        print(r)

    # Summary
    print("\n## Quick Reference: Tuning Knobs")
    print("""
| Setting | Current | Effect |
|---|---|---|
| `speech_threshold` | 0.40 | Lower = more sensitive, higher = less false wake |
| `silence_seconds` | 0.4 | Lower = faster end-of-speech, may clip words |
| `playback_threshold_boost` | 1.35 | Higher = less self-trigger, deafer to real interruption |
| `playback_rms_boost` | 1.6 | Higher = less self-trigger |
| `playback_start_grace_s` | 0.15 | Longer = deaf at start of playback |
| `min_speech_seconds` | 0.45 | Higher = need longer speech to interrupt |
| `min_playback_age_seconds` | 0.4 | Higher = playback must play longer before interrupt allowed |
| `post_turn_cooldown_seconds` | 3 | Higher = longer wait between turns (prevents loop) |
""")

    return 0


if __name__ == "__main__":
    sys.exit(main())
