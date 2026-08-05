# Git Audit Report - /home/cheta/code
**Date**: 2026-07-13 18:03:39
**Health**: 74% (43/58 repos clean)

## Executive Summary

- **58 repositories** audited
- **43 clean repos** (74%) - no action needed
- **14 repos need attention** - require manual intervention
- **1 repo has errors** - remote not found
- **2 repos successfully synced** (fast-forward pulls)

---

## 🚨 Repositories Requiring Action

### Critical Issues (Need Immediate Attention)

#### 1. **agents** ❌ ERROR
- **Issue**: Remote repository not found (deleted/renamed)
- **Action Needed**: Update remote URL or remove it
- **Path**: `/home/cheta/code/agents`

#### 2. **aaa-voice-assistant** ⚠️ MASSIVE UNCOMMITTED WORK
- **Branch**: main
- **Uncommitted**: 30,379 files! (likely build artifacts or node_modules)
- **Unpushed**: 4 commits
- **Action Needed**: 
  - Review what's uncommitted (likely needs `.gitignore`)
  - Commit only source files, push commits
- **Risk**: HIGH - 30K files suggests misconfigured git

#### 3. **claude-code-proxy** ⚠️ LARGE UNCOMMITTED WORK
- **Branch**: main
- **Uncommitted**: 91 files
- **Action Needed**: Review and commit source changes, ensure no secrets
- **Path**: `/home/cheta/code/claude-code-proxy`

#### 4. **custom-skills** ⚠️ UNCOMMITTED WORK
- **Branch**: main
- **Uncommitted**: 40 files
- **Action Needed**: Review changes, commit with proper message
- **Path**: `/home/cheta/code/custom-skills`

---

### Uncommitted Work (Review & Commit)

| Repository | Branch | Uncommitted Files | Action |
|------------|--------|-------------------|--------|
| **Tower-Creep-Symbiosis** | 002-game-foundation | 22 | Review game assets, commit |
| **AI_tampermonkey_enhancer** | main | 9 | Review tampermonkey changes |
| **project_dashboard** | 002-compact-table-ui | 14 | Review UI changes |
| **KILLMENOW** | main | 1 | Quick review |
| **model-scan** | main | 1 | Quick review |
| **reggae-wars** | main | 1 | Quick review |
| **terminal_orphan_killer** | main | 1 | Quick review |
| **switchboard-original** | main | 1 + 1 unpushed | Commit & push |

---

### Diverged Repositories (Need Reconciliation)

#### **last30days-skill** ⚠️ DIVERGED SIGNIFICANTLY
- **Branch**: main
- **Ahead**: 2 commits
- **Behind**: 70 commits
- **Uncommitted**: 0
- **Action Needed**: 
  - Pull remote changes (70 commits behind!)
  - Rebase local commits on top
  - **Risk**: HIGH - 70 commits behind suggests long divergence
- **Path**: `/home/cheta/code/last30days-skill`

#### **master-user-skills** ⚠️ DIVERGED
- **Branch**: main
- **Ahead**: 0 commits
- **Behind**: 1 commit
- **Uncommitted**: 2 files
- **Action Needed**: 
  - Commit uncommitted work
  - Pull remote changes (fast-forward likely)
- **Path**: `/home/cheta/code/master-user-skills`

---

### Foreign Origin (Need User Decision)

#### **multi-agent-workflow** ⚠️ NOT YOUR REPO
- **Issue**: Origin is `https://github.com/apolopena/multi-agent-workflow.git`
- **Action Needed**: 
  - Fork to your account, or
  - Leave as local-only, or
  - Add your own remote and push there
- **Path**: `/home/cheta/code/multi-agent-workflow`

---

## ✅ Successfully Synced

| Repository | Action | Details |
|------------|--------|---------|
| **ClawTeam-OpenClaw** | Pulled | 5 commits (fast-forward) |
| **pi-agent-observability** | Pulled | 1 commit (fast-forward) |

---

## 📊 Repositories Needing Push (Have Unpushed Commits)

| Repository | Branch | Unpushed Commits | Status |
|------------|--------|------------------|--------|
| **aaa-voice-assistant** | main | 4 | + 30K uncommitted files |
| **switchboard-original** | main | 1 | + 1 uncommitted file |
| **multi-agent-workflow** | main | 1 | Foreign origin (apolopena) |

---

## 📥 Repositories Needing Pull (Behind Remote)

| Repository | Branch | Behind By | Status |
|------------|--------|-----------|--------|
| **last30days-skill** | main | 70 commits | ⚠️ CRITICAL - Very behind |
| **master-user-skills** | main | 1 commit | Minor |

---

## 🔒 Repositories with No Remote

These repos have no upstream - they're local-only:

- **IDE-auto-complete** (branch: 001-command-sentinel)
- **AIGRAPHICS_DEMO** (branch: main)
- **autodidactic-omni-loop** (branch: 1-multi-agent-interfaces)
- **skills-proj** (branch: 001-agentforge-core)
- **model-scraper** (branch: 001-openrouter-model-scout) - appears twice
- **model-scraper** (branch: 001-openrouter-model-scout) - no upstream

**Action**: Decide if these should be pushed to GitHub or remain local

---

## 🎯 Recommended Action Plan

### Immediate (Do Now)
1. **Fix `agents` repo** - remote not found, decide to repoint or remove
2. **Investigate `aaa-voice-assistant`** - 30K uncommitted files is likely a `.gitignore` issue
3. **Handle `last30days-skill`** - 70 commits behind, needs pull + rebase

### This Week
4. Review and commit uncommitted work in:
   - claude-code-proxy (91 files)
   - custom-skills (40 files)
   - Tower-Creep-Symbiosis (22 files)
   - project_dashboard (14 files)
5. Decide what to do with `multi-agent-workflow` (foreign origin)

### Cleanup
6. Add remotes to local-only repos that should be backed up
7. Ensure all repos have proper `.gitignore` files

---

## Next Steps

Run the audit again after making changes:
```bash
repo /home/cheta/code
```

Or audit a specific repo:
```bash
cd /path/to/repo && repo .
```

---

**Report generated by**: `git-audit-sync` skill
**Full logs**: `/home/cheta/git-audit-logs/git-audit-2026-07-13_180334.md`
