#!/usr/bin/env python3
"""Install the repository Skill consistently across compatible AI hosts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid


SKILL_NAME = "toxic-corporate-truth-teller"
EXCLUDED_DIRS = {".git", ".pytest_cache", "__pycache__"}
EXCLUDED_FILES = {
    ".env",
    "api-delivery-result.json",
    "capability-snapshot.json",
    "delivery-result.json",
    "delivery.local.json",
}


def known_skill_roots(home: Path | None = None) -> dict[str, Path]:
    home = Path.home() if home is None else Path(home)
    return {
        "codex": home / ".codex" / "skills",
        "cursor": home / ".cursor" / "skills",
        "gemini": home / ".gemini" / "skills",
        "workbuddy": home / ".workbuddy" / "skills",
        "workbuddy-ai": home / ".workbuddy-ai" / "skills",
    }


def _included(relative: Path) -> bool:
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return False
    name = relative.name
    if name in EXCLUDED_FILES or name.endswith(".pyc"):
        return False
    if name == ".env" or name.startswith(".env.") or name.endswith(".env"):
        return False
    return True


def build_manifest(source: Path) -> dict[str, str]:
    source = Path(source).expanduser().resolve()
    if not source.is_dir() or not (source / "SKILL.md").is_file():
        raise ValueError("source must be a Skill directory containing SKILL.md")
    manifest = {}
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if _included(relative):
            manifest[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return manifest


def _has_excluded_files(source: Path) -> bool:
    source = Path(source)
    return any(
        path.is_file() and not _included(path.relative_to(source))
        for path in source.rglob("*")
    )


def _all_files_manifest(source: Path) -> dict[str, str]:
    source = Path(source)
    return {
        path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(source.rglob("*")) if path.is_file()
    }


def _manifest_sha256(manifest: dict[str, str]) -> str:
    encoded = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_target_root(root: Path, *, home: Path | None = None) -> Path:
    resolved = Path(root).expanduser().resolve()
    user_home = (Path.home() if home is None else Path(home)).expanduser().resolve()
    drive_root = Path(resolved.anchor).resolve()
    if resolved in {user_home, drive_root}:
        raise ValueError("target root cannot be a home or drive root")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("target root must be a directory")
    destination = (resolved / SKILL_NAME).resolve()
    if not destination.is_relative_to(resolved):
        raise ValueError("target destination escapes the Skill root")
    return resolved


def _is_link(path: Path) -> bool:
    return path.is_symlink() or bool(
        getattr(path, "is_junction", lambda: False)()
    )


def target_status(source: Path, root: Path, label: str) -> dict:
    source = Path(source).expanduser().resolve()
    source_manifest = build_manifest(source)
    root = validate_target_root(root)
    target = root / SKILL_NAME
    result = {
        "host": label,
        "target": str(target),
        "source_manifest_sha256": _manifest_sha256(source_manifest),
    }
    if not target.exists():
        result["status"] = "missing"
        return result
    if _is_link(target) or not target.is_dir():
        result["status"] = "unsupported_target"
        return result
    target_manifest = build_manifest(target)
    result["status"] = (
        "identical"
        if target_manifest == source_manifest and not _has_excluded_files(target)
        else "drift"
    )
    result["target_manifest_sha256"] = _manifest_sha256(target_manifest)
    return result


def _copy_manifest(source: Path, destination: Path,
                   manifest: dict[str, str]) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for relative in manifest:
        source_file = source / relative
        target_file = destination / relative
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)


def _backup_path(backup_root: Path, label: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return backup_root / label / timestamp / SKILL_NAME


def sync_target(source: Path, root: Path, backup_root: Path, label: str,
                dry_run: bool = False) -> dict:
    source = Path(source).expanduser().resolve()
    source_manifest = build_manifest(source)
    root = validate_target_root(root)
    if root == source or root.is_relative_to(source):
        raise ValueError("target root cannot be inside the source Skill")
    target = root / SKILL_NAME
    result = {
        "host": label,
        "target": str(target),
        "source_manifest_sha256": _manifest_sha256(source_manifest),
    }
    exists = target.exists()
    if exists:
        if _is_link(target) or not target.is_dir():
            raise ValueError("existing target must be a regular directory")
        if (build_manifest(target) == source_manifest
                and not _has_excluded_files(target)):
            result["status"] = "identical"
            return result
    if dry_run:
        result["status"] = "would_update" if exists else "would_install"
        return result

    root.mkdir(parents=True, exist_ok=True)
    stage = root / f".{SKILL_NAME}-stage-{uuid.uuid4().hex}"
    old = root / f".{SKILL_NAME}-old-{uuid.uuid4().hex}"
    backup = None
    try:
        _copy_manifest(source, stage, source_manifest)
        if build_manifest(stage) != source_manifest:
            raise RuntimeError("staged Skill verification failed")
        if exists:
            backup_root = Path(backup_root).expanduser().resolve()
            backup = _backup_path(backup_root, label).resolve()
            if not backup.is_relative_to(backup_root):
                raise ValueError("backup path escapes backup root")
            backup.parent.mkdir(parents=True, exist_ok=False)
            shutil.copytree(target, backup)
            if _all_files_manifest(backup) != _all_files_manifest(target):
                raise RuntimeError("Skill backup verification failed")
            target.rename(old)
        try:
            stage.rename(target)
        except Exception:
            if old.exists() and not target.exists():
                old.rename(target)
            raise
        if build_manifest(target) != source_manifest:
            raise RuntimeError("installed Skill verification failed")
        if old.exists():
            shutil.rmtree(old)
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    result["status"] = "updated" if exists else "installed"
    if backup is not None:
        result["backup"] = str(backup)
    return result


def _selected_targets(args, home: Path) -> list[tuple[str, Path]]:
    selected = []
    if args.all or (args.check and not args.target):
        selected.extend(
            (label, root) for label, root in known_skill_roots(home).items()
            if root.is_dir()
        )
    selected.extend(
        (f"custom-{index}", Path(root))
        for index, root in enumerate(args.target or [], start=1)
    )
    unique = []
    seen = set()
    for label, root in selected:
        resolved = validate_target_root(root)
        key = str(resolved).casefold()
        if key not in seen:
            seen.add(key)
            unique.append((label, resolved))
    return unique


def main(argv=None) -> int:
    repository_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=repository_root / "skill")
    parser.add_argument("--all", action="store_true",
                        help="use every existing known host Skill root")
    parser.add_argument("--target", action="append", type=Path,
                        help="additional compatible Skill root; repeatable")
    parser.add_argument("--check", action="store_true",
                        help="compare only; defaults to existing known roots")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup-root", type=Path,
                        default=Path.home() / ".truth-teller-skill-backups")
    args = parser.parse_args(argv)
    if not args.check and not args.all and not args.target:
        parser.error("choose --all, --target, or --check")
    try:
        targets = _selected_targets(args, Path.home())
        if args.check:
            results = [target_status(args.source, root, label)
                       for label, root in targets]
            code = 0 if all(item["status"] == "identical"
                            for item in results) else 1
        else:
            results = [sync_target(args.source, root, args.backup_root, label,
                                   dry_run=args.dry_run)
                       for label, root in targets]
            code = 0
        print(json.dumps({"skill": SKILL_NAME, "targets": results},
                         ensure_ascii=False, indent=2))
        return code
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
