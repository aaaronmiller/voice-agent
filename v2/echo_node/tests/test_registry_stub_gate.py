"""T002 gate probe: a second conforming stub registers with zero core edits.

Contract under test: specs/voice-unification/contracts/registry.md.

- Defines GateStubSTT (STTProvider subclass) OUTSIDE register_builtin.
- Registers it on a FRESH ProviderRegistry (not the core singleton path
  for built-ins) via the public register() API — the documented
  no-core-edit path.
- Runs validate_all(): stub reports ok; pre-existing entries unaffected
  (report still keyed per slot/name; no entry removed).
- Asserts Capability fields match the frozen set (name, version,
  languages, streaming, vram_gb, gpu_required, license, network, notes).

Run: ``python3 -m echo_node.tests.test_registry_stub_gate`` from ``v2/``.
Kept as the EVAL-012 regression tripwire (T002 gate evidence).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from echo_node.slots import Capability, SlotType, STTProvider
from echo_node.slots.registry import ProviderRegistry, register_builtin
from echo_node.slots.validation import ValidationResult


class GateStubSTT(STTProvider):
    """Second conforming stub — lives in the test, not in core."""

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def transcribe(self, wav_path: Path) -> str:
        return "gate stub transcript"

    @classmethod
    def capabilities(cls) -> Capability:
        return Capability(
            name="gate-stub",
            version="0.0.0-test",
            languages=["en"],
            streaming=False,
            vram_gb=None,
            gpu_required=False,
            license="MIT",
            network=False,
            notes="T002 gate probe stub",
        )

    @classmethod
    def validate(cls, config: dict[str, Any] | None = None) -> ValidationResult:
        return ValidationResult(True, "gate stub present", {})


def main() -> int:
    reg = register_builtin(ProviderRegistry())  # core path untouched
    before = set(reg._providers.keys())
    info = reg.register(SlotType.STT, "gate-stub", GateStubSTT)
    assert (SlotType.STT, "gate-stub") not in before, "stub must be new"
    assert info.validate({}).ok, "stub probe must pass"

    report = reg.validate_all()
    assert report["stt/gate-stub"]["ok"], report["stt/gate-stub"]
    # No pre-existing entry lost by the registration.
    for key in before:
        assert f"{key[0].value}/{key[1]}" in report, f"lost entry {key}"

    # Frozen Capability field set — contract drift fails here.
    fields = set(Capability.__dataclass_fields__)
    assert fields == {
        "name", "version", "languages", "streaming", "vram_gb",
        "gpu_required", "license", "network", "notes",
    }, fields

    # working() surfaces the stub once validated.
    names = [i.name for i in reg.working(SlotType.STT)]
    assert "gate-stub" in names, names
    print(f"T002 gate: stub registered, {len(report)} entries validated, "
          f"Capability fields frozen ({len(fields)}). PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
