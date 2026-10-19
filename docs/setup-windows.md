# Windows setup + capability findings (T003)

Companion to the per-target guides (`setup-wsl2.md`, `setup-fedora.md`,
`setup-macos.md`). Capability evidence feeds `preparation.json`;
unsupported behavior stays an explicit gap per constitution G2.

## Environment note

Written 2026-10-17 from a Linux (WSL2-kernel) host — no Windows machine
was available in-session, so no Windows probe below was executed here.
Each section names a reproducible check for the declared Windows
hardware. Predecessor evidence is the read-only archive
`archive/stt_project/` (hotkey dictation, README reports 8/8 tests
passing — reported, NOT reproduced here).

## 1. Background listening / wake

- Mechanism: local wake detector (OpenWakeWord per research §3) on the
  mic stream; no OS permission beyond microphone access.
- Check: `python3 -m echo_node.tests.<wake_probe>` with mic present
  reports detection + false-accept on music/noise clips.
- Status for T011/T020: PRESENT-in-principle (archive pattern exists);
  gated on declared-hardware probe before A1 claims pass.

## 2. Global hotkey trigger (dictation, T011)

- Mechanism: `keyboard` package global hook (archive
  `hotkey_listener.py`, default `Ctrl+Shift+A`); no elevated privilege
  for plain key combos on desktop Windows.
- Conflict rule: hotkey registration must fail visibly when the combo
  is taken (feeds SPEC-009 conflicting-triggers refusal).
- Check: register → press in a focused Notepad → callback fires once.
- Status: PRESENT-in-principle.

## 3. Insertion at cursor (T011)

- Mechanism: clipboard swap + `Ctrl+V` synthesis via `pyautogui`
  (archive `paster.py`); fallback `type_text` for fields rejecting
  paste.
- Limits (explicit gaps until proven): elevated/UAC windows ignore
  synthetic input; some secure fields (password boxes, some
  terminals/admin consoles) reject paste. Focus change between trigger
  and insert MUST abort, never paste into the new field (SPEC-006).
- Check: EVAL-006 procedure on declared hardware — insert, restore,
  precedence, focus-change abort.
- Status: PRESENT with documented gaps.

## 4. Clipboard save/restore incl. formats (T011)

- Mechanism: `pyperclip` text backup to temp file + restore after
  paste (archive `clipboard_manager.py`).
- Limits: `pyperclip` handles text; non-text formats
  (images/files/CF_HDROP) need `ctypes` Win32 clipboard handling —
  GAP until implemented. Newer concurrent copy wins: snapshot the
  clipboard serial at insert time; if it changed post-transcription,
  keep the newer content and report (SPEC-006 precedence).
- Check: seed clipboard with text + image → dictate → prior text
  restored; concurrent-copy race test passes.
- Status: TEXT present; RICH-FORMAT gap (named, not silent).

## 5. Microphone permission / device loss (T012, SPEC-011)

- APIs: Win32 `IMMDeviceEnumerator` / WASAPI state + Windows Settings
  `ms-settings:privacy-microphone` guidance link; `WM_DEVICECHANGE`
  for runtime removal.
- Required behavior: denial/revocation/removal disables capture with
  the guidance link, no retry loops; runtime loss stops capture and
  preserves session data; restoring permission never re-arms a
  deliberately disarmed dialogue.
- Check: EVAL-011 procedure (deny → revoke → remove → restore).
- Status: API surface identified; implementation + hardware proof
  deferred to T012.

## 6. Secret storage (T010, SPEC-009)

- Backend: Windows Credential Manager via `keyring` (`pywin32`
  backend); config holds `secret:` references only. No plaintext
  fallback: unavailable store = visible refusal of the affected path
  before capture/provider contact.
- Check: `python3 -c "import keyring; keyring.get_keyring()"` names a
  DPAPI-backed ring; EVAL-009 inline-secret + unavailable-store cases
  refuse.
- Status: DESIGN frozen here; hardware proof deferred to T010.

## A1 task capability map

| A1 task | Required OS capability | Status |
|---|---|---|
| T010 config gate | Credential Manager via keyring | design frozen, proof deferred |
| T011 dictation | hotkey hook, Ctrl+V synthesis, text clipboard | present-in-principle (archive reports, unreproduced) |
| T011 dictation | rich-format clipboard, elevated-window insert | explicit GAP |
| T012 permission | WASAPI state + DEVICECHANGE + guidance | API identified, proof deferred |
