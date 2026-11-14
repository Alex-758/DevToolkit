"""检查更新测试：版本对比、Release 解析、错误路径与 URL 安全校验（全部离线 mock）。"""

import io
from unittest.mock import patch

import pytest

from app import APP_VERSION
from app.core import updater
from app.core.results import Result
from urllib.error import HTTPError, URLError


# --- 版本号解析 ---

def test_version_tuple_variants():
    assert updater._version_tuple("v1.2.3") == (1, 2, 3)
    assert updater._version_tuple("1.2.3-beta") == (1, 2, 3)
    assert updater._version_tuple("1.10.0") == (1, 10, 0)
    assert updater._version_tuple("release-2") is None
    assert updater._version_tuple("") is None


def _fake_fetch(tag, url="https://github.com/Alex-758/DevToolkit/releases/latest"):
    return lambda: Result.success({"tag": tag, "url": url, "name": ""})


def test_check_update_newer_version():
    r = updater.check_update("1.0.0", _fake_fetch("v1.0.1"))
    assert r.ok and r.data["has_update"] and r.data["comparable"]
    assert r.data["latest"] == "v1.0.1"
    assert r.data["url"].startswith("https://github.com/")


def test_check_update_same_version():
    r = updater.check_update("1.0.0", _fake_fetch("v1.0.0"))
    assert r.ok and not r.data["has_update"]


def test_check_update_older_remote():
    r = updater.check_update(APP_VERSION, _fake_fetch("0.9.9"))
    assert r.ok and not r.data["has_update"]


def test_check_update_numeric_compare_not_lexicographic():
    """1.10.0 > 1.9.9 必须按数字逐段比较（字符串比较会误判 1.10 < 1.9）。"""
    r = updater.check_update("1.9.9", _fake_fetch("v1.10.0"))
    assert r.ok and r.data["has_update"]


def test_check_update_unparsable_tag_still_shows():
    r = updater.check_update("1.0.0", _fake_fetch("nightly-build"))
    assert r.ok and not r.data["comparable"]
    assert r.data["latest"] == "nightly-build"


def test_check_update_fetch_failure_passthrough():
    r = updater.check_update("1.0.0", lambda: Result.failure("网络不可用或查询超时，请稍后再试"))
    assert not r.ok and "网络不可用" in r.error


def test_check_update_non_github_url_replaced():
    """html_url 来自远端 JSON：非 GitHub 域名必须回落仓库 Releases 页。"""
    r = updater.check_update("1.0.0", _fake_fetch("v2.0.0", url="https://evil.example.com/x"))
    assert r.ok and r.data["has_update"]
    assert r.data["url"] == updater.RELEASES_PAGE_URL


# --- fetch_latest_release（mock urlopen，不发真实请求）---

class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._payload.encode("utf-8")


def test_fetch_latest_release_parses_json():
    payload = (
        '{"tag_name": "v1.1.0", '
        '"html_url": "https://github.com/Alex-758/DevToolkit/releases/tag/v1.1.0", '
        '"name": "v1.1.0"}'
    )
    with patch.object(updater, "urlopen", lambda req, timeout: _FakeResp(payload)):
        r = updater.fetch_latest_release()
    assert r.ok and r.data["tag"] == "v1.1.0"
    assert r.data["url"].startswith("https://github.com/")


def test_fetch_latest_release_404_friendly():
    """仓库尚未发布 Release（404）必须是友好提示，不是报错。"""
    err = HTTPError(updater.RELEASES_API_URL, 404, "Not Found", None, io.BytesIO(b"{}"))

    def _raise(req, timeout):
        raise err

    with patch.object(updater, "urlopen", _raise):
        r = updater.fetch_latest_release()
    assert not r.ok and "Release" in r.error


def test_fetch_latest_release_network_error():
    def _raise(req, timeout):
        raise URLError("connection refused")

    with patch.object(updater, "urlopen", _raise):
        r = updater.fetch_latest_release()
    assert not r.ok and "网络不可用" in r.error


def test_fetch_latest_release_bad_json():
    with patch.object(updater, "urlopen", lambda req, timeout: _FakeResp("not-json{")):
        r = updater.fetch_latest_release()
    assert not r.ok


def test_fetch_latest_release_missing_tag():
    with patch.object(updater, "urlopen", lambda req, timeout: _FakeResp('{"html_url": "x"}')):
        r = updater.fetch_latest_release()
    assert not r.ok and "版本号" in r.error
