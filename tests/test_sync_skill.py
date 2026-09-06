import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "sync_skill.py"


def sync_module():
    assert SCRIPT.exists(), "global Skill synchronizer is missing"
    spec = importlib.util.spec_from_file_location("sync_skill", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_source(tmp_path):
    source = tmp_path / "source"
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text("---\nname: fixture\n---\n", encoding="utf-8")
    (source / "scripts" / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (source / "delivery.local.json").write_text("secret config", encoding="utf-8")
    (source / "api-delivery-result.json").write_text("receipt", encoding="utf-8")
    (source / ".env").write_text("TOKEN=secret", encoding="utf-8")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "run.pyc").write_bytes(b"compiled")
    (source / "output").mkdir()
    (source / "output" / "article.html").write_text("runtime output", encoding="utf-8")
    (source / "evidence").mkdir()
    (source / "evidence" / "readback.json").write_text("evidence", encoding="utf-8")
    (source / "My-Delivery-Result.JSON").write_text("receipt", encoding="utf-8")
    (source / "credentials.json").write_text("credential", encoding="utf-8")
    (source / "api-result.json").write_text("api receipt", encoding="utf-8")
    (source / "session.log").write_text("runtime log", encoding="utf-8")
    return source


def test_manifest_excludes_runtime_and_secret_files(tmp_path):
    sync = sync_module()
    source = make_source(tmp_path)
    manifest = sync.build_manifest(source)
    assert set(manifest) == {"SKILL.md", "scripts/run.py"}


def test_first_install_and_repeat_are_idempotent(tmp_path):
    sync = sync_module()
    source = make_source(tmp_path)
    root = tmp_path / "host" / "skills"
    backups = tmp_path / "backups"

    first = sync.sync_target(source, root, backups, "fixture")
    second = sync.sync_target(source, root, backups, "fixture")

    target = root / sync.SKILL_NAME
    assert first["status"] == "installed"
    assert second["status"] == "identical"
    assert sync.build_manifest(target) == sync.build_manifest(source)
    assert not backups.exists()


def test_changed_target_is_backed_up_before_replacement(tmp_path):
    sync = sync_module()
    source = make_source(tmp_path)
    root = tmp_path / "host" / "skills"
    target = root / sync.SKILL_NAME
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("old local version", encoding="utf-8")
    backups = tmp_path / "backups"

    result = sync.sync_target(source, root, backups, "workbuddy")

    assert result["status"] == "updated"
    backup_path = Path(result["backup"])
    assert backup_path.is_relative_to(backups.resolve())
    assert (backup_path / "SKILL.md").read_text(encoding="utf-8") == "old local version"
    assert sync.build_manifest(target) == sync.build_manifest(source)


def test_excluded_residue_in_existing_target_forces_clean_replacement(tmp_path):
    sync = sync_module()
    source = make_source(tmp_path)
    root = tmp_path / "host" / "skills"
    target = root / sync.SKILL_NAME
    sync.sync_target(source, root, tmp_path / "initial-backups", "codex")
    (target / ".env").write_text("TOKEN=old-secret", encoding="utf-8")

    result = sync.sync_target(source, root, tmp_path / "backups", "codex")

    assert result["status"] == "updated"
    assert not (target / ".env").exists()
    assert (Path(result["backup"]) / ".env").is_file()


def test_dry_run_reports_change_without_writing(tmp_path):
    sync = sync_module()
    source = make_source(tmp_path)
    root = tmp_path / "host" / "skills"

    result = sync.sync_target(source, root, tmp_path / "backups", "cursor", dry_run=True)

    assert result["status"] == "would_install"
    assert not root.exists()


def test_check_mode_detects_drift_then_accepts_identical_target(tmp_path, capsys):
    sync = sync_module()
    source = make_source(tmp_path)
    root = tmp_path / "host" / "skills"

    assert sync.main(["--source", str(source), "--target", str(root), "--check"]) == 1
    first_output = json.loads(capsys.readouterr().out)
    assert first_output["targets"][0]["status"] == "missing"

    sync.sync_target(source, root, tmp_path / "backups", "fixture")
    assert sync.main(["--source", str(source), "--target", str(root), "--check"]) == 0
    second_output = json.loads(capsys.readouterr().out)
    assert second_output["targets"][0]["status"] == "identical"


def test_cli_syncs_multiple_explicit_targets(tmp_path, capsys):
    sync = sync_module()
    source = make_source(tmp_path)
    first = tmp_path / "one" / "skills"
    second = tmp_path / "two" / "skills"

    code = sync.main([
        "--source", str(source), "--target", str(first), "--target", str(second)
    ])

    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert {item["status"] for item in output["targets"]} == {"installed"}
    assert (first / sync.SKILL_NAME / "SKILL.md").is_file()
    assert (second / sync.SKILL_NAME / "SKILL.md").is_file()


def test_home_and_drive_root_are_rejected_as_target_roots(tmp_path):
    sync = sync_module()
    with pytest.raises(ValueError):
        sync.validate_target_root(tmp_path, home=tmp_path)
    drive_root = Path(tmp_path.anchor)
    with pytest.raises(ValueError):
        sync.validate_target_root(drive_root, home=tmp_path)


def test_backup_root_inside_skill_root_is_rejected_before_mutation(tmp_path):
    sync = sync_module()
    source = make_source(tmp_path)
    root = tmp_path / "host" / "skills"
    target = root / sync.SKILL_NAME
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("old local version", encoding="utf-8")

    with pytest.raises(ValueError):
        sync.sync_target(source, root, root / "backups", "fixture")

    assert (target / "SKILL.md").read_text(encoding="utf-8") == "old local version"
    assert not (root / "backups").exists()


def test_source_inside_destination_is_rejected_before_mutation(tmp_path):
    sync = sync_module()
    root = tmp_path / "host" / "skills"
    target = root / sync.SKILL_NAME
    source = target / "source"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("source version", encoding="utf-8")

    with pytest.raises(ValueError):
        sync.sync_target(source, root, tmp_path / "backups", "fixture")

    assert (source / "SKILL.md").read_text(encoding="utf-8") == "source version"


def test_failed_post_install_verification_restores_old_target(tmp_path, monkeypatch):
    sync = sync_module()
    source = make_source(tmp_path)
    root = tmp_path / "host" / "skills"
    target = root / sync.SKILL_NAME
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("old local version", encoding="utf-8")
    real_build_manifest = sync.build_manifest
    target_checks = 0

    def fail_second_target_check(path):
        nonlocal target_checks
        if Path(path).resolve() == target.resolve():
            target_checks += 1
            if target_checks == 2:
                return {"corrupt": "manifest"}
        return real_build_manifest(path)

    monkeypatch.setattr(sync, "build_manifest", fail_second_target_check)
    with pytest.raises(RuntimeError):
        sync.sync_target(source, root, tmp_path / "backups", "fixture")

    assert (target / "SKILL.md").read_text(encoding="utf-8") == "old local version"
    assert list(root.glob(f".{sync.SKILL_NAME}-old-*")) == []


def test_path_deduplication_respects_host_case_sensitivity():
    sync = sync_module()
    upper = Path("/tmp/Skills")
    lower = Path("/tmp/skills")
    assert sync._path_key(upper, case_insensitive=False) != sync._path_key(
        lower, case_insensitive=False
    )
    assert sync._path_key(upper, case_insensitive=True) == sync._path_key(
        lower, case_insensitive=True
    )


def test_internal_source_links_are_rejected(tmp_path):
    sync = sync_module()
    source = make_source(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside secret", encoding="utf-8")
    link = source / "scripts" / "outside.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are not available in this Windows session")

    with pytest.raises(ValueError):
        sync.build_manifest(source)


def test_link_guard_is_exercised_for_nested_files(tmp_path, monkeypatch):
    sync = sync_module()
    source = make_source(tmp_path)
    real_is_link = sync._is_link
    monkeypatch.setattr(
        sync, "_is_link",
        lambda path: Path(path).name == "run.py" or real_is_link(Path(path)),
    )
    with pytest.raises(ValueError):
        sync.build_manifest(source)


def test_check_reports_malformed_installation_without_aborting(tmp_path):
    sync = sync_module()
    source = make_source(tmp_path)
    root = tmp_path / "host" / "skills"
    target = root / sync.SKILL_NAME
    target.mkdir(parents=True)
    (target / "orphan.txt").write_text("broken install", encoding="utf-8")

    result = sync.target_status(source, root, "fixture")

    assert result["status"] == "invalid_target"


def test_empty_check_does_not_claim_success(tmp_path, monkeypatch, capsys):
    sync = sync_module()
    source = make_source(tmp_path)
    monkeypatch.setattr(sync, "known_skill_roots", lambda home: {})

    assert sync.main(["--source", str(source), "--check"]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "no_targets"


def test_known_hosts_use_standard_user_skill_roots(tmp_path):
    sync = sync_module()
    roots = sync.known_skill_roots(tmp_path)
    assert roots == {
        "codex": tmp_path / ".codex" / "skills",
        "cursor": tmp_path / ".cursor" / "skills",
        "gemini": tmp_path / ".gemini" / "skills",
        "workbuddy": tmp_path / ".workbuddy" / "skills",
        "workbuddy-ai": tmp_path / ".workbuddy-ai" / "skills",
    }
