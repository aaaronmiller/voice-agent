#!/usr/bin/env python3
"""STT A/B test harness (Phase C, item 5).

Transcribes the same 16 kHz mono PCM16 WAV files with two or three STT
providers from the slot registry and records transcript + wall-clock
latency per (provider, file), with a per-file winner (lowest latency
among successful transcribers).

Usage (run from v2/):
    python3 tools/stt_ab.py --a parakeet --b faster-whisper sample1.wav sample2.wav
    python3 tools/stt_ab.py --a parakeet --b faster-whisper --c onnx-asr \\
        sample1.wav --out report.json --csv report.csv
    python3 tools/stt_ab.py --list

Providers are looked up with ``get_registry().get(SlotType.STT, name)``.
Providers that fail to construct or load are recorded as errors in the
report — the harness never crashes because of a provider.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from echo_node.slots import SlotType
from echo_node.slots.registry import get_registry

# ── Input format the harness accepts ─────────────────────────────────
REQUIRED_RATE = 16000       # 16 kHz
REQUIRED_CHANNELS = 1       # mono
REQUIRED_SAMPWIDTH = 2      # 16-bit PCM


def check_wav(path: Path) -> None:
    """Raise ValueError with a clear message unless *path* is 16 kHz mono PCM16."""
    if not path.exists():
        raise ValueError(f"{path}: file does not exist")
    try:
        with wave.open(str(path), "rb") as w:
            channels = w.getnchannels()
            sampwidth = w.getsampwidth()
            rate = w.getframerate()
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"{path}: not a readable WAV file ({exc})")
    except OSError as exc:
        raise ValueError(f"{path}: cannot read file ({exc})")
    problems = []
    if channels != REQUIRED_CHANNELS:
        problems.append(f"channels={channels}, need {REQUIRED_CHANNELS} (mono)")
    if sampwidth != REQUIRED_SAMPWIDTH:
        problems.append(f"sample width={sampwidth} bytes, need {REQUIRED_SAMPWIDTH} (16-bit PCM)")
    if rate != REQUIRED_RATE:
        problems.append(f"sample rate={rate} Hz, need {REQUIRED_RATE} Hz")
    if problems:
        raise ValueError(f"{path}: unsupported WAV format: " + "; ".join(problems))


def load_stt_config() -> dict[str, Any]:
    """Best-effort read of v2/config.yaml's ``stt:`` section ({} on any failure)."""
    cfg_path = ROOT / "config.yaml"
    if not cfg_path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        stt = cfg.get("stt", {})
        return dict(stt) if isinstance(stt, dict) else {}
    except Exception:
        return {}


def dedupe(names: list[str]) -> list[str]:
    seen: list[str] = []
    for n in names:
        if n not in seen:
            seen.append(n)
    return seen


# ── Provider lifecycle ───────────────────────────────────────────────

def instantiate_providers(
    names: list[str], stt_config: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Look each name up in the registry and construct + load it.

    Returns {name: {"class": str|None, "instance": provider|None, "error": str|None}}.
    A provider that fails lookup/construction/load gets "error" set and
    "instance" None — never an exception.
    """
    registry = get_registry()
    providers: dict[str, dict[str, Any]] = {}
    for name in names:
        try:
            cls = registry.get(SlotType.STT, name)
        except KeyError as exc:
            providers[name] = {
                "class": None, "instance": None, "error": str(exc)}
            continue
        qualname = f"{cls.__module__}.{cls.__name__}"
        try:
            instance = cls(stt_config)
            instance.load()
        except Exception as exc:
            providers[name] = {
                "class": qualname, "instance": None,
                "error": f"construct/load failed: {type(exc).__name__}: {exc}"}
            continue
        providers[name] = {"class": qualname, "instance": instance, "error": None}
    return providers


def unload_providers(providers: dict[str, dict[str, Any]]) -> None:
    for info in providers.values():
        instance = info.get("instance")
        if instance is None:
            continue
        try:
            instance.unload()
        except Exception:
            pass  # unload is best-effort; the report already stands


# ── Transcription ────────────────────────────────────────────────────

def transcribe_file(instance: Any, path: Path) -> dict[str, Any]:
    """Transcribe one file; return {"transcript", "latency_s", "error"}."""
    start = time.perf_counter()
    try:
        transcript = instance.transcribe(path)
    except Exception as exc:
        return {"transcript": None, "latency_s": None,
                "error": f"{type(exc).__name__}: {exc}"}
    latency = time.perf_counter() - start
    return {"transcript": str(transcript), "latency_s": latency, "error": None}


def pick_winner(results: dict[str, dict[str, Any]]) -> str | None:
    """Lowest latency among successful transcribers; None if none succeeded."""
    best: str | None = None
    best_latency: float | None = None
    for name, r in results.items():
        if r.get("error") is not None or r.get("latency_s") is None:
            continue
        latency = float(r["latency_s"])
        if best_latency is None or latency < best_latency:
            best, best_latency = name, latency
    return best


def run_ab(
    provider_names: list[str],
    files: list[Path],
    stt_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full harness run; returns the JSON-able report dict."""
    config = stt_config if stt_config is not None else load_stt_config()
    providers = instantiate_providers(provider_names, config)
    try:
        results: list[dict[str, Any]] = []
        for path in files:
            check_wav(path)  # raises ValueError with a clear message
            transcripts: dict[str, dict[str, Any]] = {}
            for name, info in providers.items():
                instance = info.get("instance")
                if instance is None:
                    transcripts[name] = {
                        "transcript": None, "latency_s": None,
                        "error": info.get("error"),
                    }
                    continue
                transcripts[name] = transcribe_file(instance, path)
            results.append({
                "file": str(path),
                "transcripts": transcripts,
                "winner": pick_winner(transcripts),
            })
    finally:
        unload_providers(providers)

    return {
        "harness": "stt_ab",
        "providers": {
            name: {"class": info["class"], "error": info["error"]}
            for name, info in providers.items()
        },
        "files": [str(p) for p in files],
        "results": results,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def write_csv(report: dict[str, Any], csv_path: Path) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["file", "provider", "latency_s", "transcript", "error"])
        for entry in report["results"]:
            for name, t in entry["transcripts"].items():
                latency = t["latency_s"]
                writer.writerow([
                    entry["file"],
                    name,
                    f"{latency:.3f}" if latency is not None else "",
                    t["transcript"] or "",
                    t["error"] or "",
                ])


# ── CLI ──────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "A/B test STT providers: transcribe the same WAV file(s) with "
            "two or three providers and compare transcripts, per-file "
            "latency, and errors. Each provider runs in-process; a provider "
            "that fails on a file records the error instead of aborting "
            "the run."
        ),
        epilog=(
            "examples:\n"
            "  %(prog)s --list\n"
            "  %(prog)s --a parakeet --b faster-whisper sample1.wav sample2.wav\n"
            "  %(prog)s --a parakeet --b faster-whisper --c onnx-asr \\\n"
            "      --out report.json --csv report.csv *.wav\n"
            "\n"
            "WAV files must be 16 kHz mono PCM16 (anything else is rejected\n"
            "with a clear message); provider names are the registry names\n"
            "shown by --list (experimental providers need\n"
            "ECHO_INCLUDE_EXPERIMENTAL=1)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--a", metavar="PROVIDER",
                        help="First STT provider (registry name, see --list).")
    parser.add_argument("--b", metavar="PROVIDER",
                        help="Second STT provider (registry name, see --list).")
    parser.add_argument("--c", metavar="PROVIDER", default=None,
                        help="Optional third STT provider (registry name).")
    parser.add_argument("--list", action="store_true",
                        help="Print available STT provider names and exit.")
    parser.add_argument("--out", default=None, metavar="PATH",
                        help="Write the JSON report to this path "
                             "(default: stdout). The report holds one entry "
                             "per (file, provider) with transcript, "
                             "latency_s, and error fields.")
    parser.add_argument("--csv", default=None, metavar="PATH",
                        help="Also write a CSV report to this path "
                             "(columns: file, provider, latency_s, "
                             "transcript, error).")
    parser.add_argument("files", nargs="*", metavar="WAV",
                        help="WAV files to transcribe (16 kHz mono PCM16).")
    args = parser.parse_args(argv)
    if not args.list:
        if not args.a or not args.b:
            parser.error("--a and --b are required (unless --list)")
        if not args.files:
            parser.error("at least one WAV file is required (unless --list)")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.list:
        for name in get_registry().all_names(SlotType.STT):
            print(name)
        return 0

    provider_names = dedupe([n for n in (args.a, args.b, args.c) if n])
    files = [Path(f) for f in args.files]
    try:
        report = run_ab(provider_names, files)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.out:
        Path(args.out).write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    if args.csv:
        write_csv(report, Path(args.csv))
        print(f"wrote {args.csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
