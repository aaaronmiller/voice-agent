# Proposal: Enhanced `repo` Command with `--fix` Flag

## Overview

Enhance the `repo` command (from `git-audit-sync` skill) to:
1. **Smart discovery**: Auto-detect single repo vs monorepo structure
2. **Auto-fix mode**: Automatically resolve safe git issues with `--fix` flag
3. **Safety-first**: Never perform irreversible operations, always refer conflicts to user

---

## Proposed Command Behavior

### `repo [dir]` (Audit Mode - Default)

**Behavior**:
- If `.git/` found in `dir`: Audit only that repo
- If no `.git/` found: Recursively scan `dir/**` for `.git/` folders
- Output: Audit report (current behavior)

**Examples**:
```bash
repo .                          # Audit current folder (if .git exists) or find sub-repos
repo ~/code                    # Scan ~/code for all git repos
repo ~/code --subfolders       # Force recursive scan even if .git exists in ~/code
```

**Output**: Current audit report format (markdown + JSON)

---

### `repo [dir] --fix` (Auto-Fix Mode)

**Behavior**: Launch an agent to automatically resolve **safe** git issues

**Agent Authority** (What it CAN do):
- ✅ `git add -A` (staged all) **BUT** must review diff first for secrets/junk
- ✅ `git commit -m "..."` (commit reviewed changes)
- ✅ `git push origin <branch>` (push to owned repos)
- ✅ `git pull --ff-only` (fast-forward pulls only)
- ✅ Create `.gitignore` entries for common build artifacts
- ✅ Run `git gc`, `git clean -fd` (with confirmation)

**Agent MUST NOT do** (Will refer to user):
- ❌ `git merge` (non-ff)
- ❌ `git rebase` (unless explicitly safe)
- ❌ `git reset --hard`
- ❌ `git force push`
- ❌ Delete branches
- ❌ Push to foreign repos (not owned by user)
- ❌ Resolve merge conflicts (must refer to user)

**Conflict Referral**:
- If merge conflict detected → STOP, output conflict details, ask user
- If divergence >10 commits → STOP, ask user which strategy to use
- If uncommitted work has secrets → STOP, alert user

---

## Detailed Workflow

### Phase 1: Discovery & Audit

```bash
repo ~/code --fix
```

**Steps**:
1. Scan for `.git/` folders (recursive if no `.git/` in `~/code`)
2. Run audit on each repo (current behavior)
3. Generate action plan:
   - Green: Safe to auto-fix (uncommitted source files, ff-able pulls)
   - Yellow: Needs review (large uncommitted sets, minor divergence)
   - Red: Must refer to user (merge conflicts, foreign repos, secrets)

---

### Phase 2: Auto-Fix (Agent-Driven)

For each **Green** repo:

```python
# Pseudocode for agent logic
for repo in green_repos:
    cd repo
    
    # 1. Handle uncommitted work
    if has_uncommitted(repo):
        diff = run("git diff --stat")
        
        # Check for secrets/junk
        if contains_secrets(diff) or contains_build_artifacts(diff):
            # Move to yellow (needs user review)
            mark_yellow(repo, "Secrets or build artifacts detected")
            continue
        
        # Review and commit
        review_diff(diff)
        if approved:
            run("git add -A")
            run("git commit -m 'Auto-commit: <summary>'")
    
    # 2. Push committed work
    if is_ahead(repo) and is_owned_by_user(repo):
        run("git push origin <branch>")
    
    # 3. Pull safe updates
    if is_behind(repo):
        result = run("git pull --ff-only")
        if result.failed:
            # Not a fast-forward → refer to user
            mark_yellow(repo, "Divergence detected, not a fast-forward")
```

For each **Yellow** repo:
- Output detailed status
- Ask user: "Review manually? (y/n)"
- If yes, open diff for user to review

For each **Red** repo:
- Output issue description
- Ask user for decision:
  - `fork`: Fork foreign repo to user's account
  - `add-remote`: Add a new remote
  - `skip`: Leave as-is
  - `delete`: Remove local repo (with confirmation)

---

### Phase 3: Conflict Resolution (User-Driven)

If agent encounters **unsafe** situations:

```bash
⚠️ CONFLICT DETECTED in `/home/cheta/code/last30days-skill`

Issue: Repository is 70 commits behind remote, 2 commits ahead
Risk: Automatic merge may cause conflicts

Options:
  1. [r] View diff and resolve manually
  2. [f] Fork repo and push to your fork
  3. [s] Skip this repo (leave as-is)
  4. [b] Backup branch and reset to remote

Enter choice [1-4]:
```

---

## Safety Mechanisms

### 1. **Dry-Run by Default** (First Run)
```bash
repo ~/code --fix --dry-run
```
- Show what would be done
- No actual changes made
- User must confirm to proceed

### 2. **Backup Branches**
Before any operation:
```bash
git branch backup-<timestamp>-<branch>
```
- Stored in `refs/backup/` (not pushed)
- Can restore with:
  ```bash
  git reset --hard backup-<timestamp>-<branch>
  ```

### 3. **Secrets Detection**
Before committing, scan for:
- API keys (`sk-`, `ghp_`, etc.)
- Private keys (`.pem`, `.key`)
- `.env` files
- Cloud credentials

If detected → STOP, alert user

### 4. **Build Artifact Detection**
Auto-detect and suggest `.gitignore` entries for:
- `node_modules/`
- `__pycache__/`
- `.next/`
- `dist/`
- `build/`

### 5. **Revertibility Check**
Before each operation, ask: "Can this be undone?"
- ✅ Commit: Yes (reset --soft)
- ✅ Push: Yes (force push old ref)
- ✅ FF-pull: Yes (reset --hard to old SHA)
- ❌ Merge: No (without backup)
- ❌ Rebase: No (without backup)

---

## Proposed CLI Interface

### Basic Usage
```bash
# Audit only (current behavior)
repo ~/code
repo .                          # Current folder (smart detection)

# Auto-fix (agent mode)
repo ~/code --fix              # Fix all safe issues
repo ~/code --fix --interactive  # Ask before each action
repo ~/code --fix --dry-run   # Show what would be done

# Granular control
repo ~/code --fix --push-only       # Only push, don't commit
repo ~/code --fix --commit-only    # Only commit, don't push
repo ~/code --fix --pull-only      # Only pull safe updates

# Filtering
repo ~/code --fix --exclude whisper.cpp,agents
repo ~/code --fix --since-days 7   # Only repos modified in last 7 days
```

### Output Modes

**Default** (Verbose):
```
🔍 Scanning /home/cheta/code for git repos...
Found 58 repos.

📊 Audit Results:
  ✅ Clean: 43
  ⚠️  Needs attention: 14
  ❌ Errors: 1

🤖 Auto-fix mode: Resolving 8 safe issues...

[1/8] custom-skills...
  📝 Reviewing 40 uncommitted files...
  ✅ Committed: "Update custom skills (git-audit-sync, etc.)"
  📤 Pushing to origin/main...
  ✅ Pushed successfully

[2/8] claude-code-proxy...
  📝 Reviewing 91 uncommitted files...
  ⚠️  WARNING: Found potential secrets in `.env.local`
  🛑 Stopping: Secrets detected (refer to user)

...

✅ Fixed 7 repos
⚠️  6 repos need manual review
❌ 1 repo has errors
```

**Quiet Mode** (`--quiet`):
```
repo ~/code --fix --quiet
Fixed: 7/14 repos
Manual review needed: 6
Errors: 1
```

**JSON Mode** (`--json`):
```bash
repo ~/code --fix --json > results.json
```
```json
{
  "timestamp": "2026-07-13T18:30:00Z",
  "repos_scanned": 58,
  "repos_fixed": 7,
  "repos_need_input": 6,
  "repos_errors": 1,
  "actions": [
    {
      "repo": "/home/cheta/code/custom-skills",
      "action": "commit+push",
      "status": "success",
      "commit": "abc123",
      "pushed": true
    }
  ],
  "needs_input": [...]
}
```

---

## Implementation Plan

### Phase 1: Enhance Discovery Logic
**File**: `scripts/audit_sync.py`

Add flags:
- `--subfolders`: Force recursive scan even if `.git/` found in root
- Smart detection: If `.git/` in root, only audit that repo (unless `--subfolders`)

### Phase 2: Create Agent Mode
**File**: `scripts/auto_fix.py` (new)

Logic:
1. Parse audit JSON output
2. Classify repos into Green/Yellow/Red
3. For Green: Execute safe operations
4. For Yellow/Red: Output prompts for user

### Phase 3: Safety Wrappers
**File**: `scripts/safety.py` (new)

Functions:
- `check_secrets(repo_path)`: Scan for API keys, private keys
- `check_build_artifacts(repo_path)`: Detect node_modules, etc.
- `create_backup(repo_path)`: Create backup branch
- `is_reversible(operation)`: Check if operation can be undone

### Phase 4: Interactive CLI
**File**: `bin/repo` (update existing)

Add subcommands:
- `repo fix`: Run auto-fix mode
- `repo fix --interactive`: Ask before each action
- `repo fix --dry-run`: Simulate only

---

## Example Interactive Session

```bash
$ repo ~/code --fix --interactive

🔍 Scanning 58 repos...
📊 Found 14 repos needing attention.

🤖 Starting auto-fix (interactive mode)...

[1/14] custom-skills
  Status: 40 uncommitted files
  📝 Reviewing diff...
  ✅ No secrets detected
  📦 Found build artifacts: `node_modules/`, `.bun/`
  
  Proposed actions:
    1. Add `node_modules/`, `.bun/` to `.gitignore`
    2. Commit 12 source files
    3. Push to origin/main
  
  Proceed? [y/n] y
  
  ✅ Updated `.gitignore`
  ✅ Committed: "Update custom skills"
  ✅ Pushed to origin/main

[2/14] last30days-skill
  Status: 70 commits behind, 2 ahead (diverged)
  
  ⚠️  This is not a fast-forward pull. Merge conflict likely.
  
  Options:
    1. [m] Manual review (open diff)
    2. [f] Fork and push to your fork
    3. [s] Skip (leave as-is)
    
  Choice: m
  
  # Opens diff in $EDITOR
  # User resolves conflict manually
  # ...

[3/14] multi-agent-workflow
  Status: Origin is `apolopena/multi-agent-workflow` (not yours)
  
  Options:
    1. [f] Fork to your account (aaaronmiller)
    2. [a] Add your own remote and push there
    3. [s] Skip (keep local only)
  
  Choice: f
  
  🍴 Forking to aaaronmiller/multi-agent-workflow...
  ✅ Forked successfully
  📤 Pushing to your fork...
  ✅ Pushed

...

✅ Summary:
  - Fixed: 9 repos
  - Manual review: 3 repos
  - Skipped: 2 repos
  - Errors: 0

📝 Log saved to: ~/git-audit-logs/repo-fix-2026-07-13.log
```

---

## Edge Cases Handled

### 1. **Monorepo with Sub-Repos**
Example: `/home/cheta/code/.git` (main repo) + `/home/cheta/code/vendor/lib/.git` (submodule or nested repo)

**Behavior**:
- Default: Only audit `/home/cheta/code` (root `.git/`)
- With `--subfolders`: Also audit nested repos

### 2. **Detached HEAD**
**Behavior**:
- Detect `HEAD` detached
- Ask user: "Checkout `main` branch? (y/n)"

### 3. **Active Merge/Rebase**
**Behavior**:
- Detect in-progress merge/rebase/cherry-pick
- Ask user: "Finish or abort? (finish/abort/skip)"

### 4. **Large Uncommitted Sets** (>100 files)
**Behavior**:
- Flag as Yellow (needs user review)
- Suggest: "Review in chunks? (y/n)"

### 5. **Foreign Repo with Local Changes**
**Behavior**:
- Never push to foreign repo
- Offer: Fork, or leave local, or add second remote

---

## Files to Modify/Create

### Existing Files
1. **`bin/repo`** (wrapper script)
   - Add `--fix` flag
   - Add `--subfolders` flag
   - Update help text

2. **`scripts/audit_sync.py`** (core logic)
   - Add smart discovery (single vs recursive)
   - Add `--subfolders` flag
   - Output JSON for agent mode

### New Files
3. **`scripts/auto_fix.py`** (agent mode logic)
   - Parse audit JSON
   - Classify repos (Green/Yellow/Red)
   - Execute safe operations
   - Handle user prompts

4. **`scripts/safety.py`** (safety checks)
   - `check_secrets()`
   - `check_build_artifacts()`
   - `create_backup()`
   - `is_reversible()`

5. **`scripts/interactive.py`** (CLI prompts)
   - `ask_user(prompt, options)`
   - `confirm_action(action)`
   - `display_diff(repo)`

---

## Testing Plan

### Unit Tests
- Test discovery logic (single vs recursive)
- Test safety checks (secrets, build artifacts)
- Test reversibility checks

### Integration Tests
- Run on test repo with:
  - Uncommitted work
  - Divergence
  - Foreign origin
  - Merge conflict

### Dry-Run Tests
- Run `--fix --dry-run` on all 58 repos
- Verify no actual changes made
- Check output accuracy

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|------------|-------------|
| Accidental commit of secrets | Medium | Pre-commit secrets scan |
| Accidental push to foreign repo | Low | Ownership check (gh api user) |
| Data loss from bad merge | Low | Backup branches before any operation |
| Performance (58 repos) | Medium | Parallel workers (current impl) |
| False positives (secrets scan) | Medium | User confirmation before blocking |

---

## Success Criteria

- [ ] `repo .` correctly detects single repo vs monorepo
- [ ] `repo ~/code` recursively finds all sub-repos
- [ ] `repo --fix` resolves 80%+ of "Green" issues automatically
- [ ] All irreversible operations blocked without backup
- [ ] Secrets detection has <5% false positives
- [ ] User referral rate <20% (80% auto-fixed)
- [ ] Dry-run mode accurately simulates all operations
- [ ] JSON output parseable for CI integration

---

## Timeline Estimate

- **Phase 1** (Discovery): 2-3 hours
- **Phase 2** (Agent Mode): 4-6 hours
- **Phase 3** (Safety): 2-3 hours
- **Phase 4** (CLI): 2-3 hours
- **Testing**: 3-4 hours

**Total**: ~15-20 hours

---

## Appendix: Current `repo` Command Help

```bash
repo ~/code                      # audit + safe sync (push owned, ff-pull)
repo ~/code --audit-only         # read-only audit
repo ~/code --dry-run            # show what the safe ops would do
repo ~/code --workers 12 --since-days 30
repo ~/code --exclude whisper.cpp,agents
```

## Appendix: Desired `repo` Command Help (After Enhancement)

```bash
# Audit modes
repo ~/code                      # smart: single repo or recursive scan
repo ~/code --subfolders         # force recursive scan
repo ~/code --audit-only         # read-only audit
repo .                           # audit current folder (if .git exists)

# Auto-fix modes
repo ~/code