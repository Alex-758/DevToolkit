"""应用数据目录与配置：历史记录、收藏、用户设置均保存在本地，不联网。"""

from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterator


@contextlib.contextmanager
def cross_process_lock(target_path, timeout_s: float = 5.0) -> Iterator[None]:
    """跨进程互斥锁（Windows msvcrt 字节锁）：保护「读-改-写」序列。

    R5 修复（B6）：多实例并发时读-改-写会互相覆盖（实测两进程各写 100 条
    历史只剩 17 条）。锁文件为 <target>.lock；超时或锁文件不可用时退化为
    无锁 —— 单次写入仍是原子替换，最坏情况回到旧行为（丢一次更新），
    绝不卡死 UI。线程内并发由 history 层自身的 threading.Lock 保护。
    """
    try:
        import msvcrt
    except ImportError:
        yield  # 非 Windows 平台无字节锁可用（本应用面向 Windows）
        return
    fh = None
    locked = False
    try:
        try:
            fh = open(Path(str(target_path) + ".lock"), "a+b")
        except OSError:
            yield
            return
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                locked = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.02)
        yield
    finally:
        if fh is not None:
            if locked:
                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            try:
                fh.close()
            except OSError:
                pass

DEFAULT_SETTINGS: Dict[str, Any] = {
    "theme": "dark",            # dark / light
    "max_layers": 5,            # 智能解码最大层数（1-10）
    "decompress_cap_mb": 512,   # 解压输出上限（MB），防压缩炸弹
    "history_limit": 200,       # 历史记录条数上限
    "batch_skip_empty": True,   # 批量处理时跳过空行
}

# 数值设置的合法区间：越界 / 非法值一律回落默认，防止下游 int() 崩溃
_NUM_RANGES: Dict[str, tuple] = {
    "max_layers": (1, 10),
    "decompress_cap_mb": (16, 4096),
    "history_limit": (10, 1000),
}


def _sanitize_setting(key: str, value: Any) -> Any:
    """清洗单个设置值：类型 / 取值非法时回落默认值。"""
    if key in _NUM_RANGES:
        try:
            iv = int(value)
        except (TypeError, ValueError):
            return DEFAULT_SETTINGS[key]
        lo, hi = _NUM_RANGES[key]
        return max(lo, min(hi, iv))
    if key == "theme":
        return value if value in ("dark", "light") else DEFAULT_SETTINGS[key]
    if key == "batch_skip_empty":
        return bool(value) if isinstance(value, (bool, int)) else DEFAULT_SETTINGS[key]
    return value


def get_data_dir() -> Path:
    """数据目录：%APPDATA%\\DevToolkit，取不到 APPDATA 时退回用户目录。"""
    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home() / ".devtoolkit-data")
    path = Path(base) / "DevToolkit"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path.home() / ".devtoolkit-data"
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_settings_path() -> Path:
    return get_data_dir() / "settings.json"


def get_history_path() -> Path:
    return get_data_dir() / "history.json"


def get_favorites_path() -> Path:
    return get_data_dir() / "favorites.json"


def load_settings() -> Dict[str, Any]:
    """读取设置；文件损坏或字段非法时回落默认值（绝不因此崩溃）。"""
    settings = dict(DEFAULT_SETTINGS)
    path = get_settings_path()
    try:
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key in DEFAULT_SETTINGS:
                    if key in raw:
                        settings[key] = _sanitize_setting(key, raw[key])
    except (OSError, ValueError):
        pass
    return settings


def save_settings(settings: Dict[str, Any]) -> bool:
    try:
        data = dict(DEFAULT_SETTINGS)
        for key in DEFAULT_SETTINGS:
            if key in settings:
                data[key] = _sanitize_setting(key, settings[key])
        path = get_settings_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return True
    except OSError:
        return False


def get_setting(key: str) -> Any:
    return load_settings().get(key, DEFAULT_SETTINGS.get(key))


def set_setting(key: str, value: Any) -> bool:
    # 读-改-写序列：跨进程加锁防止多实例互相覆盖（R5 B6）
    with cross_process_lock(get_settings_path()):
        settings = load_settings()
        settings[key] = value
        return save_settings(settings)
