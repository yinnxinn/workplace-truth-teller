"""End-to-end invariants for the stable WeChat-safe generator path."""

from __future__ import annotations

import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
FIXTURE = ROOT / "tests" / "fixtures" / "article.json"
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?<![A-Za-z0-9_])[\"']?(?:[A-Za-z][A-Za-z0-9]*_)*(?:api[_-]?key|token|secret|password)\b[\"']?\s*(?:=|:)\s*"
    r"(?:[\"'])?([A-Za-z0-9_+\-/=]{12,})(?:[\"'])?"
)
FORBIDDEN_TRACKED_PARTS = ("__pycache__", ".pyc", ".cookie", ".session")
TEXT_EXTENSIONS = {".cfg", ".html", ".ini", ".js", ".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"}
TEXT_FILENAMES = {".gitignore"}
PLACEHOLDER_TOKENS = {
    "api", "change", "changeme", "dummy", "example", "here", "key", "me",
    "password", "placeholder", "replace", "sample", "secret", "test", "token",
    "value", "your",
}
PLACEHOLDER_MARKERS = {
    "change", "changeme", "dummy", "example", "here", "me", "placeholder",
    "replace", "sample", "test", "value", "your",
}
ALLOWED_TEMPLATE_HTML = {
    "assets/article_template.html",
    "assets/template_classic.html",
    "assets/template_dark.html",
    "assets/template_magazine.html",
}
SENSITIVE_FILENAMES = {
    "account_session.json",
    "auth-state.json",
    "auth_state.json",
    "browser-cookies.txt",
    "cookie.json",
    "cookies.json",
    "session.json",
    "sessions.json",
}
LOGIN_IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".webp"}


def _is_allowed_text_path(path: Path) -> bool:
    return path.name in TEXT_FILENAMES or path.suffix.lower() in TEXT_EXTENSIONS


def _tracked_text_files() -> list[Path]:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return [Path(path) for path in tracked if _is_allowed_text_path(Path(path))]


def _is_hardcoded_secret_assignment(text: str) -> bool:
    for match in SECRET_ASSIGNMENT.finditer(text):
        raw_value = match.group(1)
        if re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", raw_value):
            continue
        value = raw_value.lower()
        if not _is_placeholder_secret_value(value):
            return True
    return False


def _is_placeholder_secret_value(value: str) -> bool:
    tokens = [token for token in re.split(r"[-_.]+", value) if token]
    return bool(tokens) and all(token in PLACEHOLDER_TOKENS for token in tokens) and any(
        token in PLACEHOLDER_MARKERS for token in tokens
    )


def _secret_match_files() -> list[str]:
    """Return file names only: potential secret values must never enter test output."""
    matches: list[str] = []
    for path in _tracked_text_files():
        try:
            text = (ROOT / path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _is_hardcoded_secret_assignment(text):
            matches.append(path.as_posix())
    return matches


def _normalised_artifact_component(component: str) -> str:
    return re.sub(r"[_-]", "", PurePosixPath(component).stem.lower())


def _artifact_violations(paths: list[str]) -> list[str]:
    violations: list[str] = []
    for path in paths:
        posix_path = PurePosixPath(path)
        lower_path = path.lower()
        filename = posix_path.name.lower()
        if any(part in lower_path for part in FORBIDDEN_TRACKED_PARTS):
            violations.append(path)
        elif lower_path.endswith(".html") and path not in ALLOWED_TEMPLATE_HTML:
            violations.append(path)
        elif filename == ".env" or filename.startswith(".env.") or posix_path.suffix.lower() == ".env":
            violations.append(path)
        elif filename in SENSITIVE_FILENAMES:
            violations.append(path)
        elif filename.startswith("login") and posix_path.suffix.lower() in LOGIN_IMAGE_SUFFIXES:
            violations.append(path)
        elif any(
            _normalised_artifact_component(component) in {"wechatlogin", "wechatloggedin"}
            for component in posix_path.parts
        ):
            violations.append(path)
    return violations


def test_secret_classifier_detects_real_assignments_but_ignores_placeholders() -> None:
    name = "api" + "_key"
    secret = "a" * 16

    assert _is_hardcoded_secret_assignment(f"{name} = {secret}")
    for placeholder in ("your-api-key-here", "replace-me-placeholder", "你的密钥"):
        assert not _is_hardcoded_secret_assignment(f"{name} = {placeholder}")


def test_secret_classifier_matches_prefixed_variables_and_keeps_scanning_after_placeholders() -> None:
    secret = "b" * 16
    gemini_name = "GEMINI" + "_API_KEY"
    openai_name = "OPENAI" + "_API_KEY"
    service_name = "SERVICE" + "_TOKEN"

    assert _is_hardcoded_secret_assignment(f"{gemini_name}={secret}")
    assert _is_hardcoded_secret_assignment(
        f"{openai_name}=your-api-key-here\n{service_name}={secret}"
    )
    assert not _is_hardcoded_secret_assignment(f"{openai_name}=your-api-key-here")


def test_secret_classifier_matches_json_keys_and_uses_strict_placeholder_values() -> None:
    secret = "c" * 16
    api_name = "api" + "_key"
    gemini_name = "GEMINI" + "_API_KEY"
    api_json = '{"' + api_name + '": "' + secret + '"}'
    gemini_json = '{"' + gemini_name + '": "' + secret + '"}'

    assert _is_hardcoded_secret_assignment(api_json)
    assert _is_hardcoded_secret_assignment(gemini_json)
    assert not _is_hardcoded_secret_assignment(
        '{"' + api_name + '": "your-api-key-here"}'
    )
    assert not _is_hardcoded_secret_assignment(
        '{"' + api_name + '": "replace-me-placeholder"}'
    )
    assert _is_hardcoded_secret_assignment(
        '{"' + api_name + '": "example-' + secret + '"}'
    )


def test_secret_scan_uses_only_tracked_allowed_text_files() -> None:
    tracked = _tracked_text_files()
    tracked_names = set(
        subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.splitlines()
    )

    assert tracked
    assert all(path.as_posix() in tracked_names for path in tracked)
    assert all(_is_allowed_text_path(path) for path in tracked)


def test_artifact_classifier_rejects_sensitive_and_unapproved_paths() -> None:
    unsafe_paths = [
        "article.html",
        "assets/unapproved.html",
        "cookie.json",
        "cookies.json",
        "session.json",
        "sessions.json",
        "auth-state.json",
        "auth_state.json",
        ".env",
        ".env.local",
        "production.env",
        "secrets.env",
        "account_session.json",
        "browser-cookies.txt",
        "evidence/login-page.png",
        "evidence/login-proof.jpeg",
        "WeChat_logged_in/state.txt",
        "wechat_login/profile.json",
    ]
    allowed_paths = [
        "assets/template_classic.html",
        "assets/template_dark.html",
        "assets/template_magazine.html",
        "assets/article_template.html",
        "README.md",
    ]

    assert _artifact_violations(unsafe_paths) == unsafe_paths
    assert not _artifact_violations(allowed_paths)


def test_readme_lists_node_22_as_a_test_dependency() -> None:
    assert "Node.js 22" in (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")


def test_gitignore_covers_environment_and_common_session_artifacts() -> None:
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    for required_pattern in ("account_session.json", "browser-cookies.txt", "*.env", ".env*"):
        assert required_pattern in gitignore


def test_safe_generator_cli_writes_plain_manual_paste_html(tmp_path: Path) -> None:
    output = tmp_path / "article.html"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "gen_wechat_safe.py"),
            "--config",
            str(FIXTURE),
            "--out",
            str(output),
            "--no-images",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    html = output.read_text(encoding="utf-8")
    lower_html = html.lower()
    for required_text in ("自愿加班，强制背锅", "员工可自愿参加", "礼貌外套"):
        assert required_text in html
    for forbidden_text in (
        "{{",
        "<style",
        "class=",
        "<div",
        "<section",
        "<h1",
        "<h2",
        "<h3",
        "<h4",
        "<h5",
        "<h6",
        "<hr",
        "max-width",
        "font-family",
    ):
        assert forbidden_text not in lower_html


def test_python_scripts_compile() -> None:
    for script in sorted((ROOT / "scripts").glob("*.py")):
        py_compile.compile(str(script), doraise=True)


def test_javascript_scripts_pass_node_syntax_check() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js 22 is required to syntax-check repository JavaScript files."
    for script in sorted((ROOT / "scripts").glob("*.js")):
        result = subprocess.run(
            [node, "--check", str(script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"node --check failed for {script.name}: {result.stderr}"


def test_repository_has_no_hard_coded_secret_assignments() -> None:
    matches = _secret_match_files()
    assert not matches, f"Potential hard-coded secret assignments in: {', '.join(matches)}"


def test_secret_scanner_distinguishes_environment_names_from_literal_values() -> None:
    assert not _is_hardcoded_secret_assignment(
        '"app_secret": "WECHAT_APP_SECRET"'
    )
    assignment_key = '"app_' + 'secret"'
    literal_value = '"thisIsARealLiteralValue123"'
    assert _is_hardcoded_secret_assignment(assignment_key + ': ' + literal_value)


def test_tracked_files_exclude_generated_outputs_and_session_artifacts() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    violations = _artifact_violations(tracked)
    assert not violations, f"Tracked generated or sensitive artifacts: {', '.join(violations)}"


def test_legacy_article_template_is_not_described_as_safe_default() -> None:
    template = (ROOT / "assets" / "article_template.html").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "旧版兼容参考，不用于默认安全输出" in template
    assert "article_template.html` 为旧版兼容参考，不用于默认安全输出" in readme
