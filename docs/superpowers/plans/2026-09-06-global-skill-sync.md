# Global Skill Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run one safe synchronizer that deploys the repository `skill/` tree identically to every installed compatible AI host and documents the workflow in the project README.

**Architecture:** `tools/sync_skill.py` treats `skill/` as the source of truth, computes a filtered SHA256 manifest, and installs verified copies under host-specific Skill roots. Existing installations are backed up outside discovery directories before an atomic directory swap; check and dry-run modes never mutate files.

**Tech Stack:** Python 3.10+ standard library, pytest, Markdown.

## Global Constraints

- The only maintained source is the repository `skill/` directory.
- Credentials, delivery receipts, caches, `.git`, and compiled files are never copied.
- Auto-discovery writes only to existing known Skill roots; custom roots require explicit `--target`.
- Every existing target is backed up under `~/.truth-teller-skill-backups/` before replacement.
- The synchronizer never calls WeChat APIs and never publishes content.

---

### Task 1: Synchronizer contract and safety

**Files:**
- Create: `tools/sync_skill.py`
- Create: `tests/test_sync_skill.py`

**Interfaces:**
- Produces: `build_manifest(source: Path) -> dict[str, str]`, `sync_target(source: Path, root: Path, backup_root: Path, label: str, dry_run: bool = False) -> dict`, and `main(argv: list[str] | None = None) -> int`.
- Excludes: `.git`, `.pytest_cache`, `__pycache__`, `*.pyc`, local delivery configuration and receipt names.

- [x] **Step 1: Write failing tests**

Cover identical first install, no-op repeat, changed-target backup and replacement, dry-run, check-mode drift, multiple explicit targets, excluded files, and rejection of a home or drive-root target.

- [x] **Step 2: Verify RED**

Run: `python -m pytest tests/test_sync_skill.py -q`

Expected: failure because `tools/sync_skill.py` does not exist.

- [x] **Step 3: Implement the synchronizer**

Use `pathlib`, `hashlib`, `shutil`, `tempfile`, `uuid`, and `argparse`. Build the destination as `<root>/toxic-corporate-truth-teller`, verify the temporary copy manifest before swapping it into place, preserve a full backup before replacing a differing target, and emit JSON summaries without environment values.

- [x] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_sync_skill.py -q`

Expected: all synchronizer tests pass.

### Task 2: Public installation contract

**Files:**
- Modify: `README.md`
- Modify: `docs/skill-maintenance.md`
- Modify: `skill/references/draft_delivery.md`
- Modify: `tests/test_open_source_layout.py`

**Interfaces:**
- README commands: `python tools/sync_skill.py --all`, `python tools/sync_skill.py --check`, and repeatable `--target <skills-root>`.
- Known roots: `.codex/skills`, `.cursor/skills`, `.gemini/skills`, `.workbuddy/skills`, `.workbuddy-ai/skills`.

- [x] **Step 1: Add failing documentation assertions**

Require README to name `skill/` as the single source of truth, list all five known roots, show sync/check/custom-target commands, explain backups and state that credentials are not copied.

- [x] **Step 2: Verify RED**

Run: `python -m pytest tests/test_open_source_layout.py -q`

Expected: documentation contract test fails on missing global-sync text.

- [x] **Step 3: Update documentation**

Replace hand-copy installation as the recommended path, retain a short manual fallback, document update/check/rollback behavior, and state that identical files do not imply identical host permissions.

- [x] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_open_source_layout.py -q`

Expected: all open-source layout tests pass.

### Task 3: Real local deployment and release

**Files:**
- Deploy from: `skill/`
- Deploy to existing local roots under `.codex`, `.cursor`, `.workbuddy`, and `.workbuddy-ai`.

**Interfaces:**
- Consumes: the verified CLI from Task 1.
- Produces: identical installed manifests and a Git commit pushed to `origin/codex/portable-draft-delivery`.

- [x] **Step 1: Run full offline verification**

Run `python -m pytest skill/tests tests -q`, compile the synchronizer and WeChat executor, run Skill validation, and run `git diff --check`.

- [x] **Step 2: Preview and install**

Run `python tools/sync_skill.py --all --dry-run`, inspect its target list, then run `python tools/sync_skill.py --all`.

- [x] **Step 3: Verify installed manifests**

Run `python tools/sync_skill.py --check`; require every discovered installation to report `identical` and exit 0.

- [ ] **Step 4: Commit and push**

Commit only repository source, tests, and documentation. Push the current feature branch, then compare local `HEAD` with `git ls-remote` for the same branch.
