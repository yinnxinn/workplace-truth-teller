"""Offline contract tests for the official WeChat draft executor."""
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "wechat_api_delivery.py"


def executor():
    assert SCRIPT.exists(), "Official API executor is missing"
    spec = importlib.util.spec_from_file_location("wechat_api_delivery", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def article_fixture():
    return {
        "title": "自动化的最后一步",
        "author": "毒舌职场真相官",
        "lead": "演示环境没有历史。",
        "verdict": "按钮很小，责任很大。",
        "sections": [{"heading": "第一节", "comment": "正文内容。"}],
        "judge_body": "保存后必须回读。",
    }


class SuccessfulClient:
    account_ref = "appid-sha256:fixture"

    def __init__(self, result_path):
        self.result_path = result_path
        self.add_calls = 0
        self.payload = None

    def get_token(self):
        return "access-token-placeholder"

    def upload_thumb(self, token, cover_path):
        assert token
        assert cover_path.read_bytes() == b"cover-bytes"
        return "cover-media-id"

    def add_draft(self, token, payload):
        self.add_calls += 1
        pending = json.loads(self.result_path.read_text(encoding="utf-8"))
        assert pending["persistence"] == "unknown"
        assert pending["attempts"][0]["outcome"] == "pending"
        self.payload = payload
        return "draft-media-id"

    def get_draft(self, token, draft_id):
        assert draft_id == "draft-media-id"
        return {"news_item": self.payload["articles"]}


def write_inputs(tmp_path):
    article_path = tmp_path / "article.json"
    article_path.write_text(json.dumps(article_fixture(), ensure_ascii=False), encoding="utf-8")
    html_path = tmp_path / "article.html"
    html_path.write_text(
        "<!doctype html><html><body><p>演示环境没有历史。</p>"
        "<p>按钮很小，责任很大。</p><p>保存后必须回读。</p></body></html>",
        encoding="utf-8",
    )
    cover_path = tmp_path / "cover.jpg"
    cover_path.write_bytes(b"cover-bytes")
    return article_path, html_path, cover_path


def test_build_payload_extracts_body_and_required_draft_fields():
    api = executor()
    article = article_fixture()
    fragment = api.extract_body("<html><body><p>正文</p></body></html>")
    article_html = (
        "<p style='x'>自动化的最后一步</p>"
        "<p>毒舌职场真相官 · 原创评论</p><p>正文</p>"
    )
    stripped = api.strip_redundant_header(article_html, article)
    payload = api.build_draft_payload(article, fragment, "cover-media-id")
    item = payload["articles"][0]
    assert fragment == "<p>正文</p>"
    assert stripped == "<p>正文</p>"
    assert item["title"] == article["title"]
    assert item["author"] == article["author"]
    assert item["thumb_media_id"] == "cover-media-id"
    assert item["content"] == fragment
    assert item["need_open_comment"] == 0


def test_delivery_persists_pending_then_verifies_remote_readback(tmp_path):
    api = executor()
    article_path, html_path, cover_path = write_inputs(tmp_path)
    result_path = tmp_path / "delivery-result.json"
    client = SuccessfulClient(result_path)

    result = api.deliver(client, article_path, html_path, cover_path, result_path)

    assert client.add_calls == 1
    assert result["saved"] is True
    assert result["persistence"] == "verified"
    assert result["draft_ids"] == ["draft-media-id"]
    receipt = result["attempts"][0]
    assert receipt["outcome"] == "verified"
    assert all(receipt["checks"].values())
    assert receipt["readback_at"].endswith("+00:00")
    assert receipt["evidence_ref"] == str(result_path.resolve())


def test_timeout_after_create_is_unknown_and_never_retried(tmp_path):
    api = executor()
    article_path, html_path, cover_path = write_inputs(tmp_path)
    result_path = tmp_path / "delivery-result.json"

    class TimeoutClient(SuccessfulClient):
        def add_draft(self, token, payload):
            self.add_calls += 1
            assert json.loads(self.result_path.read_text(encoding="utf-8"))["attempts"][0]["outcome"] == "pending"
            raise TimeoutError("response was lost")

    client = TimeoutClient(result_path)
    with pytest.raises(api.DeliveryUnknownError):
        api.deliver(client, article_path, html_path, cover_path, result_path)

    persisted = json.loads(result_path.read_text(encoding="utf-8"))
    assert client.add_calls == 1
    assert persisted["saved"] is False
    assert persisted["persistence"] == "unknown"
    assert persisted["attempts"][0]["outcome"] == "unknown"


def test_readback_mismatch_is_not_reported_as_saved(tmp_path):
    api = executor()
    article_path, html_path, cover_path = write_inputs(tmp_path)
    result_path = tmp_path / "delivery-result.json"

    class MismatchClient(SuccessfulClient):
        def get_draft(self, token, draft_id):
            remote = super().get_draft(token, draft_id)
            remote["news_item"][0]["content"] = "<p>内容不完整</p>"
            return remote

    result = api.deliver(MismatchClient(result_path), article_path, html_path, cover_path, result_path)
    assert result["saved"] is False
    assert result["persistence"] == "unknown"
    assert result["attempts"][0]["outcome"] == "readback_mismatch"
    assert result["attempts"][0]["checks"]["body"] is False


def test_api_error_and_cli_message_do_not_expose_tokens():
    api = executor()
    error = api.WechatAPIError(40013, "invalid appid", stage="token")
    rendered = str(error)
    assert "40013" in rendered
    assert "invalid appid" not in rendered
    assert "access-token-placeholder" not in rendered
    assert "leaky-response" not in str(
        api.WechatAPIError("leaky-response", stage="token")
    )
    assert "remote_error" in str(
        api.WechatAPIError("leaky-response", stage="token")
    )


def test_missing_media_id_response_is_indeterminate():
    api = executor()
    client = api.WechatClient("fixture-app", "fixture-secret")
    client._post_json = lambda *args, **kwargs: {}
    with pytest.raises(api.IndeterminateCreateError):
        client.add_draft("placeholder-token", {"articles": []})


def test_content_identity_is_normalized_and_bound_to_account():
    api = executor()
    article = article_fixture()
    first = api.content_identity(
        "appid-sha256:first", article, "<p>one\r\ntwo</p>", b"cover-bytes"
    )
    second = api.content_identity(
        "appid-sha256:first", dict(reversed(list(article.items()))),
        "<p>one\ntwo</p>", b"cover-bytes"
    )
    another_account = api.content_identity(
        "appid-sha256:second", article, "<p>one\ntwo</p>", b"cover-bytes"
    )
    assert first == second
    assert first != another_account


def test_verified_receipt_makes_same_delivery_idempotent(tmp_path):
    api = executor()
    article_path, html_path, cover_path = write_inputs(tmp_path)
    result_path = tmp_path / "delivery-result.json"
    first_client = SuccessfulClient(result_path)
    first = api.deliver(first_client, article_path, html_path, cover_path, result_path)

    class NoCallClient:
        account_ref = first_client.account_ref

        def __getattr__(self, name):
            raise AssertionError(f"remote call attempted during replay: {name}")

    replay = api.deliver(NoCallClient(), article_path, html_path, cover_path, result_path)
    assert replay == first
    assert first_client.add_calls == 1


def test_unknown_receipt_blocks_blind_retry(tmp_path):
    api = executor()
    article_path, html_path, cover_path = write_inputs(tmp_path)
    result_path = tmp_path / "delivery-result.json"

    class TimeoutClient(SuccessfulClient):
        def add_draft(self, token, payload):
            self.add_calls += 1
            raise TimeoutError("response was lost")

    first_client = TimeoutClient(result_path)
    with pytest.raises(api.DeliveryUnknownError):
        api.deliver(first_client, article_path, html_path, cover_path, result_path)

    class NoCallClient:
        account_ref = first_client.account_ref

        def __getattr__(self, name):
            raise AssertionError(f"remote call attempted during retry: {name}")

    with pytest.raises(api.DeliveryUnknownError):
        api.deliver(NoCallClient(), article_path, html_path, cover_path, result_path)
    assert first_client.add_calls == 1


def test_missing_media_id_after_create_stays_unknown(tmp_path):
    api = executor()
    article_path, html_path, cover_path = write_inputs(tmp_path)
    result_path = tmp_path / "delivery-result.json"

    class MissingIdClient(SuccessfulClient):
        def add_draft(self, token, payload):
            self.add_calls += 1
            raise api.IndeterminateCreateError()

    with pytest.raises(api.DeliveryUnknownError):
        api.deliver(MissingIdClient(result_path), article_path, html_path,
                    cover_path, result_path)
    persisted = json.loads(result_path.read_text(encoding="utf-8"))
    assert persisted["persistence"] == "unknown"
    assert persisted["attempts"][0]["outcome"] == "unknown"


def test_invalid_body_is_rejected_before_remote_calls(tmp_path):
    api = executor()
    article_path, html_path, cover_path = write_inputs(tmp_path)
    html_path.write_text("<html><body><img src='https://example.test/x.jpg'></body></html>",
                         encoding="utf-8")

    class NoCallClient:
        account_ref = "appid-sha256:fixture"

        def __getattr__(self, name):
            raise AssertionError(f"remote call attempted before validation: {name}")

    with pytest.raises(ValueError):
        api.deliver(NoCallClient(), article_path, html_path, cover_path,
                    tmp_path / "delivery-result.json")
