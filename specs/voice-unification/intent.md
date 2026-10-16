---
date: 2026-10-15
ver: 1.1.0
author: system adjudication of supplied human intent
tags: [strata, intent, voice-unification, human-authored, constraints]
---

# Voice unification intent

Layer: Intent. Outcomes and constraints govern; implementation selections belong
in the plan. Platform and historical project names identify scope and provenance,
not a prescribed stack. Prior art contributes intent only (§10 and Part 1 §1.2).

## 1. Goal

Give one person reliable hands-free spoken dialogue with AI systems and a
separate instant hotkey-dictation path on the machines they maintain.

## 2. Intent levels

- Consumer intent: arm once, converse and interrupt naturally, and dictate anywhere.
- Engineering intent: one maintainable build with configuration-driven providers.
  Engineering choices serve the consumer outcomes.

## 3. Constraints

- Primary: Windows 11 native, including a WSL2-shell workflow with Windows
  retaining audio ownership. Secondary: Linux desktops. Android remains an
  in-scope later target. The independent VoiceInk fork serves macOS outside this build.
- Dialogue stays hands-free after one arming action, including user interruption
  during machine speech. Constant manual triggering defeats the purpose.
- Machine output must not become user-attributed input or trigger another turn.
  Ordinary assistant transcript entries and deliberate human repetition remain valid.
- Dictation pastes at the intended cursor and restores prior clipboard content,
  including supported formats. A newer concurrent clipboard change takes precedence.
- Stored credentials use a platform-protected local secret store. Configuration
  holds references; ordinary files and diagnostics contain no plaintext credentials.
- Wake detection, speech-activity detection, and input-level indication work
  locally without a network connection, even when dialogue is hosted.
- Listening state is visible. The user can stop or disarm; late responses must
  not restart capture or playback after disarming.

## 4. Scale and quality expectations

- Actual end-of-speech to first audible response content: at most 2 seconds on
  declared reference hardware and network conditions. A chime or filler is not a response.
- Single user, single machine, one dialogue session. Dictation may suspend or
  queue against dialogue, preserving history and never becoming a dialogue turn.
- A failed or stalled provider call gives a reason and returns an already armed,
  usable dialogue to armed idle without re-arming. Disarming, invalid configuration,
  or unavailable microphone permission takes precedence; show the disabled state.
- One person maintains this. Swapping conforming providers or models requires
  configuration alone. A new protocol or capability is a separate design change.

## 5. Success conditions

- One arming action permits a multi-turn exchange with pauses and interruptions;
  only genuine user speech enters the user-input stream.
- One dictation trigger inserts text into the focused editable field and preserves
  the clipboard. Unsupported fields or platform restrictions remain explicit gaps.
- A conforming dialogue provider/model changes through configuration without rebuilding.
- WSL invocation completes the same voice action with Windows owning the audio.
- Windows, Linux, and Android have their own acceptance evidence. Desktop delivery
  is a milestone while Android remains unfinished, not full product completion.

## 6. Failure conditions

- Provider unreachable or stalled: report the reason and recover as defined in §4.
- Microphone denied or lost: give OS-appropriate guidance without prompt/retry loops.
- Sustained music or notifications: create no user turns, while continuing to
  detect genuine speech. A force-listen action remains available while armed;
  it is distinct from dictation and does not bypass permission or echo exclusion.
- User speaks over machine output: interruption wins and retains the beginning
  of the user's utterance. Muting all listening during playback does not satisfy this.
- Invalid configuration or failed insertion: explain the defect, preserve user
  data, and avoid pasting into a different field after focus changes.

## 7. Personas

- Maintainer-user: maintains 50+ machines, including a separately served macOS
  fleet; works primarily in Windows and WSL; dictates and dialogues daily;
  has high technical sophistication and no tolerance for manual retriggering.
- Future contributor: inherits one repo, one spec set, and configuration-driven
  providers; never edits core to swap a conforming provider/model.

## 8. User stories

1. I arm once and converse through pauses without push-to-talk each turn.
2. I interrupt machine speech naturally, retain my utterance, and get no echoed input.
3. I dictate into an editable field with one trigger and retain my clipboard
   and any active dialogue afterward.
4. I change conforming providers/models through configuration and invoke the
   Windows workflow from my WSL shell without rebuilding.

## 9. Scope boundaries

| In scope | Out of scope | Rationale |
|---|---|---|
| hands-free dialogue + hotkey dictation on Windows/Linux/Android | macOS conversational app | independent VoiceInk project |
| hosted dialogue + local listening controls | self-hosted model training/serving | app is a client |
| configurable providers, personalities, memory window | voice cloning/dubbing/audiobooks | different product |
| single repo, predecessors mined for intent | rebuilding archived shells | no implementation inheritance |

## 10. Prior art

These are historical reports from the supplied pack, not newly reproduced results.
No source implementation or runtime evidence was supplied in `archive-inputs/`.

| Source | Intent retained | Evidence limit |
|---|---|---|
| VoiceInk conversational modifications | hands-free exchange, echo exclusion, interruption | reported untested; no portability proof |
| Echo-Node | low latency, replaceable providers | reported incomplete skeleton |
| stt_project | trigger, transcribe, paste, restore | working-loop claim not reproduced |
| RVC specification | platform scope, native audio ownership, traceable acceptance | specification only; referenced research unverified here |
| aaa-voice-assistant | requirement coverage and failure scenarios | reported tests are ideas until validated |
