from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from scripts.gen_wechat_safe import build_safe_html


def test_skill_source_tree_is_present() -> None:
    """The public skill source tree contains the files later tasks edit."""
    root = Path(__file__).resolve().parents[1]
    expected_paths = [
        "SKILL.md",
        "assets/template_classic.html",
        "assets/template_dark.html",
        "assets/template_magazine.html",
        "scripts/gen_wechat.py",
        "scripts/gen_wechat_safe.py",
        "scripts/gen_wechat_rich.py",
        "scripts/inject_body.js",
        "scripts/find_editor.js",
        "references/technical_reference.md",
        "references/gemini_image_guide.md",
    ]

    missing_paths = [path for path in expected_paths if not (root / path).is_file()]

    assert not missing_paths, f"Missing public skill source files: {missing_paths}"


def test_skill_contract_is_portable_and_honest():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)[1]
    description = re.search(r"description:\s*[|>]?[\r\n ]*([^\r\n]+)", frontmatter)
    assert description is not None
    assert description.group(1) == (
        "Use when 用户希望解构公司新闻稿、内部信、财报、职场复盘或流量科普，"
        "并产出具有讽刺评论风格的微信公众号文章与微信兼容 HTML。"
    )
    for obsolete_name in ("WebFetch", "WebSearch", "DeferExecuteTool", "agent-browser", "present_files"):
        assert obsolete_name not in text
    for required_text in (
        "scripts/gen_wechat_safe.py",
        "手动粘贴",
        "实验功能",
        "无法验证时不得宣称保存成功",
        "再次明确授权发布",
        "未运行脚本时不得将手写 HTML 称为微信安全版 HTML",
        "不能运行脚本时不输出任何自写 HTML",
    ):
        assert required_text in text
    assert "不自动发布" in text


def test_openai_yaml_has_required_interface_fields():
    metadata = yaml.safe_load((ROOT / "agents/openai.yaml").read_text(encoding="utf-8"))
    assert metadata["interface"]["display_name"] == "毒舌职场真相官"
    assert metadata["interface"]["short_description"] == "解构职场话术并生成微信兼容公众号文章"
    assert metadata["interface"]["default_prompt"] == (
        "使用 $toxic-corporate-truth-teller 解构这份职场材料，并生成可供我审阅的公众号文章。"
    )
    assert metadata["policy"]["allow_implicit_invocation"] is True


def test_safe_generator_produces_plain_wechat_compatible_html():
    """Characterize the existing text-only generator contract for manual paste."""
    article = {
        "title": "原创测试标题",
        "date": "2026-09-02",
        "author": "测试作者",
        "lead": "原创导语",
        "verdict": "原创真相翻译",
        "sections": [
            {"heading": "原创拆解", "quote": "原创原文", "comment": "原创点评"},
        ],
        "judge_body": "原创判词",
        "footer": "原创版权说明",
    }

    html = build_safe_html(article, include_images=False)

    for required_text in ("原创测试标题", "原创原文", "原创点评"):
        assert required_text in html
    for forbidden_text in (
        "<style",
        "class=",
        "<div",
        "<section",
        "<h1",
        "<h2",
        "<h3",
        "<hr",
        "max-width",
        "font-family",
    ):
        assert forbidden_text not in html


def test_public_documentation_is_complete():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    required_sections = [
        "## 能做什么",
        "## 两种使用方式",
        "## 快速开始",
        "## 生成微信版 HTML",
        "## 实验自动化：保存公众号草稿",
        "## 安全与内容边界",
        "## 参与贡献",
        "## 许可证",
    ]
    for section in required_sections:
        assert section in readme
    assert "MIT" in readme
    assert "实验功能" in readme
    assert "不自动发布" in readme


def test_license_is_mit():
    license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text
    assert "Copyright (c) 2026 yinnxinn" in license_text


def test_markdown_local_links_resolve():
    markdown_files = [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "CONTRIBUTING.md",
        ROOT / "examples/README.md",
    ]
    pattern = re.compile(r"\[[^]]+\]\((?!https?://|#)([^)]+)\)")
    for markdown_file in markdown_files:
        text = markdown_file.read_text(encoding="utf-8")
        for target in pattern.findall(text):
            resolved = (markdown_file.parent / target.split("#", 1)[0]).resolve()
            assert resolved.exists(), f"broken link: {markdown_file.name} -> {target}"


def test_documentation_uses_real_install_and_validation_commands():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    contributing = (PROJECT_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

    assert "https://github.com/yinnxinn/truth-teller.git" in readme
    assert "<仓库地址>" not in readme
    assert "<仓库地址>" not in contributing
    assert "python tools/sync_skill.py --all" in readme
    assert "python tools/sync_skill.py --check" in readme
    assert ".truth-teller-skill-backups" in readme
    for command_fragment in ("quick_validate.py", "PYTHONUTF8", "python -m pytest", "git diff --check"):
        assert command_fragment in contributing


def test_readme_links_to_ci_and_repository():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "actions/workflows/validate-skill.yml" in readme
    assert "github.com/yinnxinn/truth-teller" in readme


def test_delivery_reference_uses_the_global_sync_contract():
    reference = (ROOT / "references/draft_delivery.md").read_text(encoding="utf-8")
    for required_text in (
        "唯一维护源",
        "python tools/sync_skill.py --all",
        "--target <skills-root>",
        ".truth-teller-skill-backups",
        "凭据、回执、本地配置与缓存不复制",
    ):
        assert required_text in reference


def test_validate_workflow_has_required_github_actions_contract():
    workflow_path = PROJECT_ROOT / ".github/workflows/validate-skill.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    triggers = workflow["on"] if "on" in workflow else workflow[True]
    assert "push" in triggers
    assert "pull_request" in triggers

    test_job = workflow["jobs"]["test"]
    assert test_job["runs-on"] == "ubuntu-latest"

    steps = test_job["steps"]
    uses = {step["uses"] for step in steps if "uses" in step}
    assert {"actions/checkout@v4", "actions/setup-python@v5", "actions/setup-node@v4"} <= uses

    setup_python = next(step for step in steps if step.get("uses") == "actions/setup-python@v5")
    assert setup_python["with"]["python-version"] == "3.12"
    setup_node = next(step for step in steps if step.get("uses") == "actions/setup-node@v4")
    assert setup_node["with"]["node-version"] == "22"

    runs = {step["run"] for step in steps if "run" in step}
    assert "python -m pip install pytest pyyaml" in runs
    assert "python -m pytest skill/tests -v" in runs
    assert "python -m pytest tests -v" in runs
    assert "app/test_dingtalk_one_truth_article.py" not in runs
