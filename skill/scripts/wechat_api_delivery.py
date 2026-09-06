#!/usr/bin/env python3
"""Save one prepared article to the WeChat Official Account draft API.

The command uploads one cover, creates one draft, and reads it back. It never
publishes. A durable pending receipt is written immediately before draft
creation so a lost response is not retried blindly. Python 3.10+, stdlib only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html import unescape
import json
import mimetypes
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import unicodedata
import uuid


API_ROOT = "https://api.weixin.qq.com"


class WechatAPIError(RuntimeError):
    def __init__(self, code, _message=None, *, stage="api"):
        self.code = code if isinstance(code, int) else (
            code if code in {"missing_token", "missing_media_id"}
            else "remote_error"
        )
        self.stage = stage
        super().__init__(f"wechat_api_error stage={stage} code={self.code}")


class WechatTransportError(RuntimeError):
    def __init__(self, *, stage):
        self.stage = stage
        super().__init__(f"wechat_transport_error stage={stage}")


class DeliveryUnknownError(RuntimeError):
    pass


class IndeterminateCreateError(RuntimeError):
    """The create request may have succeeded, but no usable draft ID arrived."""

    def __init__(self):
        super().__init__("wechat_create_response_indeterminate")


def _credential(name):
    value = os.environ.get(name)
    if value or os.name != "nt":
        return value
    try:
        import winreg
        locations = (
            (winreg.HKEY_CURRENT_USER, "Environment"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        )
        for root, key_name in locations:
            try:
                with winreg.OpenKey(root, key_name) as key:
                    candidate, _ = winreg.QueryValueEx(key, name)
                    if candidate:
                        return str(candidate)
            except OSError:
                continue
    except ImportError:
        pass
    return None


def extract_body(document):
    match = re.search(r"<body\b[^>]*>(.*?)</body\s*>", document,
                      flags=re.IGNORECASE | re.DOTALL)
    return (match.group(1) if match else document).strip()


def _visible_text(fragment):
    without_tags = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", "", unescape(without_tags))


def strip_redundant_header(fragment, article):
    paragraphs = list(re.finditer(r"\s*<p\b[^>]*>.*?</p\s*>", fragment,
                                  flags=re.IGNORECASE | re.DOTALL))
    if len(paragraphs) < 2:
        return fragment.strip()
    first, second = paragraphs[0], paragraphs[1]
    title = re.sub(r"\s+", "", str(article.get("title", "")))
    author = re.sub(r"\s+", "", str(article.get("author", "")))
    if (_visible_text(first.group(0)) == title
            and author and author in _visible_text(second.group(0))
            and not fragment[:first.start()].strip()):
        return fragment[second.end():].strip()
    return fragment.strip()


def build_draft_payload(article, body_html, thumb_media_id):
    digest = str(article.get("digest") or article.get("lead") or "")
    item = {
        "title": str(article.get("title", "")),
        "author": str(article.get("author", "")),
        "digest": digest[:120],
        "content": body_html,
        "thumb_media_id": thumb_media_id,
        "show_cover_pic": 1,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }
    source_url = article.get("source_url")
    if source_url:
        item["content_source_url"] = str(source_url)
    if not item["title"].strip() or not body_html.strip():
        raise ValueError("article title and body are required")
    if re.search(r"<img\b", body_html, flags=re.IGNORECASE):
        raise ValueError("body images must be uploaded and rewritten before delivery")
    return {"articles": [item]}


def _normalize_text(value):
    return unicodedata.normalize(
        "NFC", str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    )


def content_identity(account_ref, article, body_html, cover_bytes):
    """Return the protocol's normalized, account-bound content identity."""
    manifest = {
        "account_id": _normalize_text(account_ref),
        "author": _normalize_text(article.get("author")),
        "body_html": _normalize_text(body_html),
        "cover_sha256": hashlib.sha256(cover_bytes).hexdigest(),
        "digest": _normalize_text(article.get("digest") or article.get("lead")),
        "image_sha256": [],
        "title": _normalize_text(article.get("title")),
    }
    serialized = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _write_json(path, value):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


class WechatClient:
    def __init__(self, app_id, app_secret, *, timeout=30):
        if not app_id or not app_secret:
            raise ValueError("WeChat API credentials are missing")
        self.app_id = app_id
        self._app_secret = app_secret
        self.timeout = timeout
        self.account_ref = "appid-sha256:" + hashlib.sha256(
            app_id.encode("utf-8")).hexdigest()[:16]

    def _open_json(self, request, *, stage):
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                data = json.loads(error.read().decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise WechatTransportError(stage=stage) from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError,
                UnicodeDecodeError):
            raise WechatTransportError(stage=stage) from None
        if data.get("errcode") not in (None, 0):
            raise WechatAPIError(data.get("errcode"), stage=stage)
        return data

    def get_token(self):
        query = urllib.parse.urlencode({
            "grant_type": "client_credential",
            "appid": self.app_id,
            "secret": self._app_secret,
        })
        request = urllib.request.Request(f"{API_ROOT}/cgi-bin/token?{query}",
                                         method="GET")
        data = self._open_json(request, stage="token")
        token = data.get("access_token")
        if not token:
            raise WechatAPIError("missing_token", stage="token")
        return token

    def upload_thumb(self, token, cover_path):
        cover_path = Path(cover_path).resolve()
        content = cover_path.read_bytes()
        mime = mimetypes.guess_type(cover_path.name)[0] or "application/octet-stream"
        if mime not in ("image/jpeg", "image/png"):
            raise ValueError("cover must be JPEG or PNG")
        boundary = "----truth-teller-" + uuid.uuid4().hex
        prefix = (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"media\"; filename=\"{cover_path.name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
        body = prefix + content + f"\r\n--{boundary}--\r\n".encode("ascii")
        query = urllib.parse.urlencode({"access_token": token, "type": "thumb"})
        request = urllib.request.Request(
            f"{API_ROOT}/cgi-bin/material/add_material?{query}", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        data = self._open_json(request, stage="upload_thumb")
        media_id = data.get("media_id")
        if not media_id:
            raise WechatAPIError("missing_media_id", stage="upload_thumb")
        return media_id

    def _post_json(self, path, token, payload, *, stage):
        query = urllib.parse.urlencode({"access_token": token})
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{API_ROOT}{path}?{query}", data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        return self._open_json(request, stage=stage)

    def add_draft(self, token, payload):
        data = self._post_json("/cgi-bin/draft/add", token, payload,
                               stage="add_draft")
        media_id = data.get("media_id")
        if not media_id:
            raise IndeterminateCreateError()
        return media_id

    def get_draft(self, token, draft_id):
        return self._post_json("/cgi-bin/draft/get", token,
                               {"media_id": draft_id}, stage="get_draft")


def _base_result(client, article, content_hash):
    return {
        "schema_version": 1,
        "identity_version": 1,
        "target": {"platform": "wechat_mp", "account_ref": client.account_ref},
        "content_sha256": content_hash,
        "action": "deliver",
        "route": "official_api",
        "persistence": "not_saved",
        "saved": False,
        "draft_ids": [],
        "title": str(article.get("title", "")),
        "attempts": [],
        "published": False,
    }


def _existing_result(result_path, client, identity):
    if not result_path.exists():
        return None
    try:
        existing = json.loads(result_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("existing delivery receipt is unreadable") from error
    target = existing.get("target") if isinstance(existing, dict) else None
    if (not isinstance(target, dict)
            or target.get("account_ref") != client.account_ref
            or existing.get("content_sha256") != identity):
        raise ValueError("existing delivery receipt belongs to different content or account")
    if existing.get("persistence") == "verified" and existing.get("saved") is True:
        return existing
    attempts = existing.get("attempts")
    outcomes = {
        item.get("outcome") for item in attempts or [] if isinstance(item, dict)
    }
    if (existing.get("persistence") == "unknown"
            or existing.get("draft_ids")
            or outcomes.intersection({"pending", "unknown", "saved", "readback_mismatch"})):
        raise DeliveryUnknownError("existing draft delivery must be reconciled")
    if attempts and outcomes != {"rejected_no_write"}:
        raise ValueError("existing delivery receipt cannot be safely resumed")
    return existing


def deliver(client, article_path, html_path, cover_path, result_path):
    article_path = Path(article_path).resolve()
    html_path = Path(html_path).resolve()
    cover_path = Path(cover_path).resolve()
    result_path = Path(result_path).resolve()
    article = json.loads(article_path.read_text(encoding="utf-8-sig"))
    document = html_path.read_text(encoding="utf-8-sig")
    body_html = strip_redundant_header(extract_body(document), article)
    cover_bytes = cover_path.read_bytes()
    build_draft_payload(article, body_html, "preflight-thumb")
    identity = content_identity(client.account_ref, article, body_html, cover_bytes)
    existing = _existing_result(result_path, client, identity)
    if existing and existing.get("persistence") == "verified":
        return existing
    result = existing or _base_result(client, article, identity)
    result["action"] = "deliver"

    token = client.get_token()
    thumb_id = client.upload_thumb(token, cover_path)
    payload = build_draft_payload(article, body_html, thumb_id)
    receipt = {
        "route": "official_api",
        "outcome": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result["attempts"].append(receipt)
    result["persistence"] = "unknown"
    _write_json(result_path, result)

    try:
        draft_id = client.add_draft(token, payload)
    except IndeterminateCreateError as error:
        receipt["outcome"] = "unknown"
        result["action"] = "reconcile"
        _write_json(result_path, result)
        raise DeliveryUnknownError("draft create result is unknown") from error
    except WechatAPIError:
        receipt["outcome"] = "rejected_no_write"
        result["persistence"] = "not_saved"
        result["action"] = "manual_handoff"
        _write_json(result_path, result)
        raise
    except Exception as error:
        receipt["outcome"] = "unknown"
        result["action"] = "reconcile"
        _write_json(result_path, result)
        raise DeliveryUnknownError("draft create result is unknown") from error

    receipt["outcome"] = "saved"
    receipt["draft_id"] = draft_id
    result["draft_ids"] = [draft_id]
    _write_json(result_path, result)

    try:
        remote = client.get_draft(token, draft_id)
    except Exception as error:
        result["action"] = "reconcile"
        _write_json(result_path, result)
        raise DeliveryUnknownError("draft exists but readback failed") from error

    items = remote.get("news_item") if isinstance(remote, dict) else None
    remote_item = items[0] if isinstance(items, list) and items else {}
    checks = {
        "account": result["target"]["account_ref"] == client.account_ref,
        "title": remote_item.get("title") == payload["articles"][0]["title"],
        "body": _visible_text(str(remote_item.get("content", "")))
                == _visible_text(body_html),
        "images": remote_item.get("thumb_media_id") == thumb_id,
    }
    receipt["checks"] = checks
    receipt["readback_at"] = datetime.now(timezone.utc).isoformat()
    receipt["evidence"] = {
        "body_text_sha256": hashlib.sha256(
            _visible_text(str(remote_item.get("content", ""))).encode("utf-8")
        ).hexdigest(),
        "title_sha256": hashlib.sha256(
            str(remote_item.get("title", "")).encode("utf-8")
        ).hexdigest(),
    }
    receipt["evidence_ref"] = str(result_path)
    if all(checks.values()):
        receipt["outcome"] = "verified"
        result["action"] = "complete"
        result["persistence"] = "verified"
        result["saved"] = True
    else:
        receipt["outcome"] = "readback_mismatch"
        result["action"] = "reconcile"
        result["persistence"] = "unknown"
    _write_json(result_path, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, help="prepared article.json")
    parser.add_argument("--html", required=True, help="generated WeChat-safe HTML")
    parser.add_argument("--cover", required=True, help="JPEG or PNG cover")
    parser.add_argument("--result", required=True, help="durable JSON receipt")
    parser.add_argument("--app-id-env", default="WECHAT_APP_ID")
    parser.add_argument("--app-secret-env", default="WECHAT_APP_SECRET")
    args = parser.parse_args(argv)
    try:
        client = WechatClient(_credential(args.app_id_env),
                              _credential(args.app_secret_env))
        result = deliver(client, args.article, args.html, args.cover, args.result)
        print(json.dumps({"saved": result["saved"],
                          "persistence": result["persistence"],
                          "draft_ids": result["draft_ids"]}, ensure_ascii=True))
        return 0 if result["saved"] else 3
    except DeliveryUnknownError:
        print(json.dumps({"error": "draft_delivery_result_unknown"}), file=sys.stderr)
        return 3
    except WechatAPIError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 4
    except WechatTransportError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 3
    except (OSError, ValueError, json.JSONDecodeError):
        print(json.dumps({"error": "invalid_or_unreadable_delivery_input"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
