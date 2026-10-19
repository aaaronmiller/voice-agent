"""T004 gate probe: the three live profiles round-trip byte-identical.

Contract: specs/voice-unification/contracts/profiles.md.
Loader: echo_node.profiles.

For each profile in specs/voice-unification/profiles/*.yaml:
load (validates) -> dump (canonical) -> write temp -> load again ->
dump again. Both dumps must equal the on-disk bytes exactly; the two
loads must produce equal mappings.

Also asserts negative cases: inline secret values and unknown stack
gaps fail validation with the field named.

Run: ``python3 -m echo_node.tests.test_profile_roundtrip`` from ``v2/``.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from echo_node.profiles import ProfileError, dump_profile, load_profile

PROFILE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "specs" / "voice-unification" / "profiles"

EXPECTED = ["offline-daily-driver", "hosted-latency-king", "budget-cascade"]


def main() -> int:
    names = [p.stem for p in sorted(PROFILE_DIR.glob("*.yaml"))]

    for name in EXPECTED:
        path = PROFILE_DIR / f"{name}.yaml"
        original = path.read_bytes()
        doc = load_profile(path)
        dumped = dump_profile(doc).encode("utf-8")
        assert dumped == original, (
            f"{name}: canonical dump differs from on-disk bytes "
            f"({len(dumped)} vs {len(original)})")
        with tempfile.TemporaryDirectory() as tmp:
            rt = Path(tmp) / f"{name}.yaml"
            rt.write_bytes(dumped)
            doc2 = load_profile(rt)
            assert doc2 == doc, f"{name}: reloaded mapping differs"
            assert dump_profile(doc2).encode("utf-8") == original, (
                f"{name}: second dump differs")
        print(f"{name}: round-trip byte-identical ({len(original)} bytes). OK")

    # Negative: inline secret must fail, field named, value not echoed.
    bad_secret: dict = {
        "format": "voice-profile/v1", "name": "bad", "version": 1,
        "description": "x",
        "stack": {"wake_word": "a", "vad": "a", "stt": "a", "tts": "a",
                  "agent_backend": "a", "avatar": "a", "audio_io": "a",
                  "barge_in": "a"},
        "dialogue": {"provider": "a", "transport": "websocket"},
        "params": {}, "secrets": {"x.api_key": "SECRET-VALUE-123"},
        "hardware_floor": {}, "covers": [], "evidence": [],
    }
    from echo_node.profiles import validate_profile
    try:
        validate_profile(bad_secret, source="<probe>")
        raise AssertionError("inline secret accepted")
    except ProfileError as exc:
        assert "x.api_key" in str(exc), str(exc)
        assert "SECRET-VALUE-123" not in str(exc), "secret leaked in error"
        print("inline-secret refusal: OK (field named, value not echoed)")

    # Negative: missing stack slot must fail.
    bad_stack = dict(bad_secret)
    bad_stack["secrets"] = {}
    bad_stack["stack"] = dict(bad_secret["stack"])
    del bad_stack["stack"]["tts"]
    try:
        validate_profile(bad_stack, source="<probe>")
        raise AssertionError("missing slot accepted")
    except ProfileError as exc:
        assert "tts" in str(exc), str(exc)
        print("missing-slot refusal: OK")

    print("T004 gate: 3 profiles round-trip byte-identical, refusals green. PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
