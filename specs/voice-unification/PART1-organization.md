# Part 1: organization of existing voice projects

Existing-state disposition plan, outside Strata product requirements. VoiceInk
stays independent; macOS behavior is never judged by Windows/Linux criteria or
used to certify them. This document merge executes no disposition actions.

## 1.1 Inventory: source-reported October 14, 2026

The original inventory's verification has not been reproduced in this review.
Locations, sizes, dates, repository state, and license labels below are historical
reports. No predecessor source was supplied in `archive-inputs/`.

| # | Location | Origin | Size | Platform/role | Reported state |
|---|---|---|---|---|---|
| 1 | `code2/voicechat` | Jun 9 2025; `aaaronmiller/voicechat` | 348K | macOS, AnythingLLM helper | clean, pushed |
| 2 | `code2/Voiceink/VoiceInk-merged-mod-10-3` | upstream Feb 22 2025; rewrite Oct 3 2025 (`b5e48992`); user mods Oct 6 2025 | 22M | macOS Swift/Xcode | 10 modified + 5 untracked; 1 ahead / 1075 behind `Beingpax/VoiceInk` |
| 3 | `code2/Voiceink/VoiceInk-mod-9-23` | same upstream; current to Oct 13 2026 | 31M | macOS Swift/Xcode | clean, current |
| 4 | `code/aaa-voice-assistant`, `-work`, `-recovery` | Feb 7 2026; `aaaronmiller/aaa-voice-assistant` | 3.4M repo / 1.2M work | Windows-first Tauri; cross-platform claim | resolved/pushed Oct 14; history rewritten 4.5G to 1.8M |
| 5 | `code/buttplug/voice-agent` (Echo-Node) | Mar 29 2026; `aaaronmiller/voice-agent` | 493M including environment/dependencies | Linux/macOS/WSL2; Python+Bun+Svelte | substantive work on `crash-backup/2026-08-04`; pushed Oct 2 |
| 6 | `code/stt_project` | Jan 2026 files; no Git | unreported | Windows hotkey dictation | untracked; working per README |
| 7 | `code/realtime-voice-ass` (RVC) | Sep 6 2026 files; referenced spec dated Aug | unreported | Windows native, Linux, Android | spec only, zero code |
| 8 | `code/voice-single-source` | Aug 13 2026 | unreported | harness configs | notes only |
| 9 | `code/voicestudio` | Sep 30 2026 clone; `debpalash/VoiceStudio` | unreported | Electron; reported AGPL-3.0 | detached HEAD + 3 local files |
| 10 | GitHub `voice_assistant`, `voice-agent` | Jun 22 / Oct 2 2026 | unreported | name hygiene | exact duplication unverified |

## 1.2 Implementation quarantine: binding on Part 2

Older projects contribute user goals, pain points, and acceptance ideas. Their
code, assets, hardware/software selections, provider/model choices, version pins,
and architecture do not become current mandates. Age alone does not prove a
technology obsolete; current requirements and evidence must justify selection.

Historical examples, not implementation choices:

- Recognition/synthesis: whisper.cpp-tiny, Kokoro-82M, sherpa, specific ONNX pins.
- Stacks/packaging: Tauri-1 patterns, Electron, Swift/Xcode, Python environments,
  Bun/Svelte, package-lock versus pnpm debates.
- macOS audio: HAL IO Proc, Core Audio Taps, Soundflower, aggregate devices,
  ScreenCaptureKit. Proposed replacements are quarantined alongside older approaches.
- Architecture/defaults: provider ABCs, fixed five-state machines, process splits,
  cockpit shells, named personalities, wake strings, and VRM/avatar libraries.
- Hosting/platform claims: local-everything defaults, old cloud-provider choices,
  WSLg reliability claims, and unsupported portability labels.

A current selection may coincide with prior art after independent justification;
omitting a technology's name does not legitimize inherited architecture. A token
scan needs semantic review. Missing source limits historical coverage, not the
ability to review this document pack.

Retain: hands-free exchange and interruption; no machine-output echo; at most
2 seconds to audible response; configuration-only compatible provider swaps;
native audio ownership, including Windows for WSL invocation; separate lightweight
dictation with insertion and clipboard preservation.

## 1.3 Disposition actions

Before later moves or integration, verify exact source identities and preserve
tracked/untracked work with a recoverable checkpoint. Historical plans do not
authorize destructive or external actions during this review.

1. **VoiceInk, independent:** fork `Beingpax/VoiceInk` to the user account;
   integrate the reported seven-file conversational feature and ten local
   refinements against verified current upstream. Preserve the complete
   merged-mod-10-3 build as an archival example and retain all local work.
   Verify reported counts before integration; build and microphone-test on one
   Mac. This project's gates do not certify the fork.
2. **Single repo:** use the proposed `aaaronmiller/voice-agent` identity for
   non-VoiceInk work. Verify remotes, branches, and contents before migration.
   Compare `voice_assistant` by exact identity/content; retain it until preservation
   is verified. Archival, publication, or deletion needs exact authorization.
3. **Read-only archives:** preserve aaa-voice-assistant and work/recovery copies,
   voicechat, voice-single-source notes, RVC spec/transcript, historical Echo-Node,
   and untracked stt_project. Keep implementations external; mine goals/test ideas
   without rebuilding archived shells or importing source. Record locations and
   revisions or directory fingerprints before moves.
4. **VoiceStudio:** external reference only; import no implementation or assets.
   Preserve and inspect its reported detached local work rather than casually
   reverting it. The license label alone establishes no compatibility finding.
5. **License:** live tree is MIT (`aaaronmiller/voice-agent` ships MIT
LICENSE); KEEP MIT. The GPL-3.0 draft direction is withdrawn — the live
lineage is MIT and actively developed; no relicensing without explicit
approval. VoiceInk port, if ever, stays separate; AGPL material stays out.
