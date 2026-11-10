"""历史记录与收藏：本地 JSON 存储。

安全设计：历史只保存操作类型、参数摘要与数据规模，绝不保存密钥、口令、
明文与密文内容。调用方传入的 detail 必须是脱敏后的摘要。
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import List, Optional

from .config import get_favorites_path, get_history_path

_lock = threading.Lock()

MAX_DETAIL_LEN = 120


def _load_list(path) -> list:
    try:
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return raw
    except (OSError, ValueError):
        pass
    return []


def _save_list(path, items: list) -> bool:
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
        return True
    except OSError:
        return False


def add_entry(page: str, op: str, detail: str, limit: int = 200) -> bool:
    """新增一条历史记录。detail 必须是脱敏摘要（不含密钥 / 明文 / 密文）。"""
    if detail and len(detail) > MAX_DETAIL_LEN:
        detail = detail[:MAX_DETAIL_LEN] + "…"
    entry = {
        "ts": time.strftime("%m-%d %H:%M", _now_str_struct()),
        "page": page,
        "op": op,
        "detail": detail,
    }
    with _lock:
        items = _load_list(get_history_path())
        items.insert(0, entry)
        if len(items) > max(10, int(limit)):
            items = items[: max(10, int(limit))]
        return _save_list(get_history_path(), items)


def _now_str_struct():
    return time.localtime()


def list_entries(limit: int = 200) -> List[dict]:
    with _lock:
        items = _load_list(get_history_path())
    return items[: max(1, int(limit))]


def remove_entry(index: int) -> bool:
    """按 list_entries 返回顺序中的下标删除（0 起始）。"""
    with _lock:
        items = _load_list(get_history_path())
        if 0 <= index < len(items):
            items.pop(index)
            return _save_list(get_history_path(), items)
    return False


def clear_entries() -> bool:
    with _lock:
        return _save_list(get_history_path(), [])


# ---------------------------------------------------------------------------
# 收藏（常用算法）
# ---------------------------------------------------------------------------

def list_favorites() -> List[dict]:
    with _lock:
        return _load_list(get_favorites_path())


def add_favorite(kind: str, target: str) -> bool:
    """kind: 'codec'（编码算法）| 'hash'（哈希算法）；target 为算法 id。"""
    favs = list_favorites()
    if any(f.get("kind") == kind and f.get("target") == target for f in favs):
        return True
    favs.append({"kind": kind, "target": target, "ts": time.strftime("%Y-%m-%d %H:%M:%S", _now_str_struct())})
    with _lock:
        return _save_list(get_favorites_path(), favs)


def remove_favorite(kind: str, target: str) -> bool:
    favs = list_favorites()
    favs = [f for f in favs if not (f.get("kind") == kind and f.get("target") == target)]
    with _lock:
        return _save_list(get_favorites_path(), favs)


def toggle_favorite(kind: str, target: str) -> bool:
    """切换收藏状态，返回切换后是否已收藏。"""
    favs = list_favorites()
    exists = any(f.get("kind") == kind and f.get("target") == target for f in favs)
    if exists:
        remove_favorite(kind, target)
        return False
    add_favorite(kind, target)
    return True


def is_favorite(kind: str, target: str) -> bool:
    return any(f.get("kind") == kind and f.get("target") == target for f in list_favorites())
