"""关于软件页：版本信息、技术栈、快捷键、隐私声明。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from ... import APP_NAME, APP_VERSION
from ..widgets import PageHeader, banner, make_card
from . import PageBase

PAGE_NAME = "关于软件"

TECH_STACK = ["Python 3.11+", "PySide6", "PyCryptodome", "brotli", "zstandard", "lz4", "PyInstaller"]

SHORTCUTS = [
    ("Ctrl+Enter", "执行当前页操作"),
    ("Ctrl+1 ~ Ctrl+8", "切换左侧功能页"),
    ("Ctrl+T", "切换深色 / 浅色主题"),
    ("Ctrl+Shift+K", "复制当前页结果"),
    ("Ctrl+R", "编码解码页：交换输入与输出"),
    ("Ctrl+,", "打开设置"),
]


class AboutPage(PageBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        header = PageHeader(PAGE_NAME, "纯离线运行的 Windows 编码解码工具箱")
        root.addWidget(header)

        card = make_card()
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(14)

        head_row = QHBoxLayout()
        head_row.setSpacing(12)
        logo = QLabel("DT")
        logo.setFixedSize(44, 44)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(
            "border-radius: 11px; background: #10a37f; color: #ffffff;"
            "font-weight: 700; font-size: 17px;"
        )
        head_row.addWidget(logo)
        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        name_lbl = QLabel(f"{APP_NAME} v{APP_VERSION}")
        name_lbl.setObjectName("dtTitle")
        sub_lbl = QLabel("面向开发者与日常技术人员的多功能编码解码工具箱 · 编码 / 加密 / 压缩 / 哈希 / 智能解码")
        sub_lbl.setObjectName("dtSub")
        sub_lbl.setWordWrap(True)
        title_col.addWidget(name_lbl)
        title_col.addWidget(sub_lbl)
        head_row.addLayout(title_col)
        head_row.addStretch(1)
        v.addLayout(head_row)

        v.addLayout(self._kv("技术栈", " · ".join(TECH_STACK)))
        v.addLayout(self._kv("数据位置", r"%APPDATA%\DevToolkit\（历史、收藏与设置均为本地 JSON，可随时删除）"))
        v.addLayout(self._kv("开源许可", "MIT License · 图标为内置 SVG 线性图标"))

        shortcuts_card = make_card()
        sc_v = QVBoxLayout(shortcuts_card)
        sc_v.setContentsMargins(1, 1, 1, 1)
        sc_header = QLabel("键盘快捷键")
        sc_header.setProperty("dtCard", False)
        sc_header.setStyleSheet("font-weight:600; padding: 10px 14px 2px 14px;")
        sc_v.addWidget(sc_header)
        for keys, desc in SHORTCUTS:
            row = QHBoxLayout()
            key_lbl = QLabel(keys)
            key_lbl.setStyleSheet(
                "font-family: Consolas, monospace; font-size: 11px; background: rgba(128,128,128,0.14);"
                "border-radius: 4px; padding: 1px 7px; margin-left: 14px;"
            )
            key_lbl.setFixedWidth(130)
            desc_lbl = QLabel(desc)
            desc_lbl.setObjectName("dtMeta")
            row.addWidget(key_lbl)
            row.addWidget(desc_lbl)
            row.addStretch(1)
            sc_v.addLayout(row)
        spacer = QLabel(" ")
        spacer.setFixedHeight(6)
        sc_v.addWidget(spacer)
        root.addWidget(card)
        root.addWidget(shortcuts_card)

        root.addWidget(banner(
            "ok",
            "本软件完全离线运行：不联网、不上传、不收集任何数据，所有计算均在本地完成。"
            "加密功能使用 PBKDF2 派生密钥（默认 210,000 次迭代），AEAD 模式防篡改。",
        ))
        root.addStretch(1)

    def _kv(self, key: str, value: str) -> QHBoxLayout:
        row = QHBoxLayout()
        k = QLabel(key)
        k.setObjectName("dtMeta")
        k.setFixedWidth(72)
        val = QLabel(value)
        val.setObjectName("dtSub")
        val.setWordWrap(True)
        row.addWidget(k)
        row.addWidget(val, 1)
        return row

    def on_theme_changed(self, theme: str):
        pass
