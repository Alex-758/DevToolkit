"""应用数据目录与配置：历史记录、收藏、用户设置均保存在本地，不联网。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

DEFAULT_SETTINGS: Dict[str, Any] = {
    "theme": "dark",            # dark / light
    "max_layers": 5,            # 智能解码最大层数（1-10）
    "decompress_cap_mb": 512,   # 解压输出上限（MB），防压缩炸弹
    "history_limit": 200,       # 历史记录条数上限
    "batch_skip_empty": True,   # 批量处理时跳过空行
}


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
    """读取设置；文件损坏时返回默认值（绝不因此崩溃）。"""
    settings = dict(DEFAULT_SETTINGS)
    path = get_settings_path()
    try:
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key, default in DEFAULT_SETTINGS.items():
                    if key in raw:
                        settings[key] = raw[key]
    except (OSError, ValueError):
        pass
    return settings


def save_settings(settings: Dict[str, Any]) -> bool:
    try:
        data = dict(DEFAULT_SETTINGS)
        for key in DEFAULT_SETTINGS:
            if key in settings:
                data[key] = settings[key]
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
    settings = load_settings()
    settings[key] = value
    return save_settings(settings)
