"""关于软件页：版本信息、检查更新、技术栈、快捷键、隐私声明。"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from ... import APP_NAME, APP_VERSION
from ...core import updater
from ..widgets import PageHeader, WorkerRunner, banner, btn, chip, make_card, set_btn_icon, set_chip
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

        # ---- 检查更新：仅用户点击时联网查询一次 GitHub Releases ----
        upd_row = QHBoxLayout()
        upd_row.setSpacing(10)
        self.check_btn = btn("检查更新", "refresh")
        set_btn_icon(self.check_btn, "refresh")
        self.check_btn.clicked.connect(self._check_update)
        self.update_chip = chip()
        self.update_chip.setOpenExternalLinks(True)  # 新版本下载页链接
        upd_row.addWidget(self.check_btn)
        upd_row.addWidget(self.update_chip, 1)
        v.addLayout(upd_row)

        self.update_runner = WorkerRunner(self._on_update_done, None, self)

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
            "加密功能使用 PBKDF2 派生密钥（默认 210,000 次迭代），AEAD 模式防篡改。"
            "唯一例外是「检查更新」——仅在你点击时查询一次 GitHub Releases。",
        ))
        root.addStretch(1)

    # ------------------------------------------------------------------
    def _check_update(self):
        if self.update_runner.busy():
            return
        self.check_btn.setEnabled(False)
        self.check_btn.setText("检查中…")
        set_chip(self.update_chip, "… 正在查询 GitHub Releases", "info")
        self.statusMsg.emit("正在检查更新（联网查询 GitHub Releases）…")
        self.update_runner.start(lambda _w: updater.check_update(APP_VERSION, updater.fetch_latest_release))

    def _on_update_done(self, result):
        self.check_btn.setEnabled(True)
        self.check_btn.setText("检查更新")
        if not result.ok:
            set_chip(self.update_chip, f"✕ {result.error}", "err")
            self.statusMsg.emit(f"检查更新失败：{result.error}")
            return
        info = result.data
        latest = html.escape(info["latest"])
        url = info["url"]
        from ..context import CTX
        accent = CTX.pal()["accent"]
        if info["has_update"]:
            set_chip(self.update_chip,
                     f"✓ 发现新版本 {latest}（当前 v{APP_VERSION}） · "
                     f'<a href="{html.escape(url)}" style="color: {accent};">前往下载页</a>', "accent")
            self.statusMsg.emit(f"发现新版本：{info['latest']}")
        elif info["comparable"]:
            set_chip(self.update_chip, f"✓ 已是最新版本（v{APP_VERSION}）", "ok")
            self.statusMsg.emit("已是最新版本")
        else:
            # 远端 tag 无法解析为版本号：不猜大小关系，给出链接让用户自行判断
            set_chip(self.update_chip,
                     f"最新版本 {latest}（与当前 v{APP_VERSION} 无法自动比较） · "
                     f'<a href="{html.escape(url)}" style="color: {accent};">前往下载页</a>', "info")
            self.statusMsg.emit(f"最新版本：{info['latest']}")

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
