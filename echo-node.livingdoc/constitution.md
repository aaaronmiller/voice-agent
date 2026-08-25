## ⚠️ Invariant: Living Document Features Are Mandatory

**The living document at `echo-node.livingdoc/` is a coordination protocol with mandatory features.** These features are the reason the document prevents project drift (see RAISON_DETRE.md for the failure-mode justification):

- Annotation system (select text → popup → save → export)
- ModelReplies (question/option cards)
- Proposals (approve/defer/reject)
- Immutable worklogs
- Three export formats (change request JSON, merged JSON, Markdown)
- Dashboard health indicators
- Constitution (constitution.md)

**No agent may remove, disable, strip, or simplify any of these features without explicit human authorization recorded in a modelReply.** Doing so is a violation of Principle IV (Honest Status Reporting) and Principle IX (Open Decision Tracking). This invariant exists because a prior agent stripped the annotation/feedback/export features from this document, destroying its ability to function as a collaboration surface.

## Principles

### Principle I: Gate Integrity
**The gate is external to any single agent.** No agent may define, modify, or waive the criteria by which its own work is judged. All gate checks must be performed by:
- A pre-commit hook installed **before** the agent session began
- A CI/CD pipeline that runs independently of the agent
- A second agent operating in a separate context
- Explicit human sign-off recorded in a modelReply

*Violation:* Changing `gate-check.sh` criteria to pass a failing check. Changing the pre-commit hook during a session. Declaring a gate passed without running the check.

### Principle II: Constitutional Primacy
**The constitution is the highest authority.** Every agent action must be consistent with these principles. When in doubt, the constitution controls. The canonical constitution lives at `echo-node.livingdoc/constitution.md`. The project `AGENTS.md` inlines the principle headings for context survival; the canonical file is the source of truth.

*Violation:* Acting on a perceived "shortcut" that violates a principle. Relying on memory rather than the canonical file.

### Principle III: Build Order Fidelity
**The implementation order CLI → TUI → Web is binding.** Each layer must be verifiably complete before the next begins. "Verifiably complete" means:
1. All exit criteria in the living document section are checked programmatically
2. The gate script reports zero failures
3. A human or second agent has confirmed functionality

*Violation:* Building the web frontend before the CLI mode passes all gates. Adding TUI features to "unblock" web work.

### Principle IV: Honest Status Reporting
**Phase status must reflect reality, not convenience.** A phase is "stable" only when:
1. All source files exist and pass syntax/type validation
2. The gateway process runs and responds to health checks
3. WebSocket handshake succeeds with the gateway
4. All exit criteria in the phase's living document section are checked programmatically
5. The gate script reports zero failures

All other phases are "active" (work in progress) or "pending" (not started). The status field in the manifest may only be changed when the phase passes a gate check.

*Violation:* Setting a phase to "stable" when any exit criterion is unmet. Changing status without a corresponding gate check log entry.

### Principle V: Immutable Worklog
**Every agent revision produces an append-only worklog entry.** Worklogs record what was changed, what was validated, what is suggested, and what warnings exist. Worklogs are never rewritten — corrections are new entries.

*Violation:* Editing a prior worklog to remove a failed validation. Omitting a worklog after significant changes.

### Principle VI: Pre-Commit Verification
**No code change may be committed without passing the gate check.** The pre-commit hook at `.githooks/pre-commit` runs automatically on every `git commit`. Bypassing with `--no-verify` requires:
1. Explicit human authorization ("approved --no-verify")
2. A corresponding worklog entry documenting the bypass
3. A plan to resolve the failing check within 3 commits

*Violation:* Using `--no-verify` without authorization. Making multiple `--no-verify` commits without resolving the underlying gate failure.

### Principle VII: Context Reload for Rule Changes
**Changes to AGENTS.md, constitution.md, or any gating mechanism require a context reload or agent restart before taking effect.** The constitution is loaded into agent context at session start. Until the agent is reloaded or restarted, the original rules remain in effect — even if the files on disk have changed.

**Required procedure for rule changes:**
1. Make the change to `constitution.md` and/or `AGENTS.md`
2. Record the change in a worklog entry
3. Create or update a modelReply for the human to approve the change
4. Wait for human approval
5. **The human or a new agent session must reload/restart the agent** before the new rules apply
6. Verify the new rules are in context before acting on them

*Violation:* Editing AGENTS.md in a session, then immediately acting on the new rule without reloading. The agent is still operating under the old context. Any action taken under the old rules that would violate the new ones is still a violation.

### Principle VIII: Mechanical Principle Extraction
**Principle names in AGENTS.md must be extracted mechanically from the canonical constitution.md.** Never type principle names from memory. Use `grep -nE '^### Principle ' echo-node.livingdoc/constitution.md` to extract the authoritative list. The list in AGENTS.md must have the exact same count and strings as the canonical source.

*Violation:* Adding a principle to AGENTS.md that doesn't exist in constitution.md. Omitting a principle. Paraphrasing a principle name.

### Principle IX: Open Decision Tracking
**All decisions requiring human input are tracked as modelReplies in the living document.** A modelReply is "open" until the human responds. No phase may advance past a blocking modelReply without the human's answer. Non-blocking modelReplies do not block unrelated work.

*Violation:* Proceeding with a phase that depends on an unanswered blocking modelReply. Recording a human decision that was never made.

### Principle X: Cross-Verification
**No phase completion is valid without cross-verification.** The agent that built the phase cannot be the sole verifier. Cross-verification takes one of these forms:
1. Running the gate check script (which the agent did not write)
2. A second agent reviewing the phase against its exit criteria
3. Human confirmation via the living document's annotation/export system

*Violation:* Marking a phase complete based solely on the implementing agent's assertion. Skipping the gate check because "it worked when I tested it."

---

## Governance

### Amendment Process
1. Any agent or human may propose a constitutional amendment
2. The amendment is recorded as a proposal in the living document
3. The human must approve the proposal before it takes effect
4. After approval, the constitution.md is updated, version incremented, and AGENTS.md regenerated
5. A context reload is required before the amendment applies

### Enforcement
- The pre-commit hook enforces Gate Integrity (I), Pre-Commit Verification (VI), and Build Order (III)
- The AGENTS.md file enforces Constitutional Primacy (II), Mechanical Extraction (VIII), and Context Reload (VII)
- The living document manifest enforces Honest Status Reporting (IV) and Open Decision Tracking (IX)
- Worklogs in the living document enforce Immutable Worklog (V)
- ModelReplies enforce Cross-Verification (X)

### Violation Handling
1. First violation: documented warning in worklog
2. Second violation: human notification via modelReply
3. Third violation: requires human review before any further agent action
