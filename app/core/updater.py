"""检查更新：查询 GitHub Releases 的最新版本。

隐私约定：应用自身绝不自动联网；仅当用户在「关于软件」页点击
「检查更新」时发起一次查询，请求只携带固定 User-Agent，不上传
任何本地数据。仓库尚未发布 Release 时给出友好提示而非报错。
"""

from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .. import APP_NAME, APP_VERSION, GITHUB_REPO
from .results import Result

RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO}/releases"
TIMEOUT_S = 6


def fetch_latest_release(timeout: int = TIMEOUT_S) -> Result:
    """请求 releases/latest，返回 Result[dict(tag, url, name)]。"""
    req = Request(
        RELEASES_API_URL,
        headers={
            "User-Agent": f"{APP_NAME}/{APP_VERSION}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return Result.failure("仓库还没有发布任何 Release（发布后即可正常检查）")
        return Result.failure(f"GitHub 返回错误：HTTP {exc.code}", f"HTTPError {exc.code}")
    except (URLError, OSError):
        return Result.failure("网络不可用或查询超时，请稍后再试")
    except ValueError as exc:
        return Result.failure("GitHub 响应不是有效数据", repr(exc))
    tag = str(data.get("tag_name") or "")
    url = str(data.get("html_url") or "")
    if not tag:
        return Result.failure("Release 数据缺少版本号")
    return Result.success({"tag": tag, "url": url, "name": str(data.get("name") or "")})


def _is_github_url(url: str) -> bool:
    try:
        parts = urlparse(url)
    except ValueError:
        return False
    return parts.scheme == "https" and parts.hostname in ("github.com", "www.github.com")


def _version_tuple(version: str):
    """'v1.2.3' / '1.2.3-beta' → (1, 2, 3)；无数字前缀返回 None。"""
    m = re.match(r"^[vV]?(\d+(?:\.\d+)*)", version.strip())
    if not m:
        return None
    return tuple(int(p) for p in m.group(1).split("."))


def check_update(current: str, fetch=None) -> Result:
    """对比当前版本与最新 Release。fetch 可注入用于测试（离线单测）。

    返回 Result[dict(has_update, latest, url, comparable)]。
    版本号无法解析时 comparable=False，仍展示最新版本让用户自行判断。
    """
    fetch = fetch or fetch_latest_release
    r = fetch()
    if not r.ok:
        return r
    info = r.data
    # 安全校验放在唯一对外入口：html_url 来自远端 JSON，只放行 GitHub
    # 域名的 https 链接，其余一律回落仓库 Releases 页（避免打开任意 URL）
    url = info["url"]
    if not _is_github_url(url):
        url = RELEASES_PAGE_URL
    latest_t = _version_tuple(info["tag"])
    cur_t = _version_tuple(current)
    comparable = latest_t is not None and cur_t is not None
    has_update = bool(comparable and latest_t > cur_t)
    return Result.success(
        {
            "has_update": has_update,
            "latest": info["tag"],
            "url": url,
            "comparable": comparable,
            "current": current,
        },
        name=info.get("name", ""),
    )
