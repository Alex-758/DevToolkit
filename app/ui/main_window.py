"""主窗口：侧边导航 + 页面栈 + 状态栏 + 主题切换 + 设置 + 全局快捷键。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..core import config, history
from . import icons
from .context import CTX
from .settings_dialog import SettingsDialog
from .theme import build_qss
from .widgets import set_btn_icon
from .pages.about_page import AboutPage
from .pages.compress_page import CompressPage
from .pages.crypto_page import CryptoPage
from .pages.encode_page import EncodePage
from .pages.files_page import FilesPage
from .pages.hash_page import HashPage
from .pages.history_page import HistoryPage
from .pages.smart_page import SmartPage

NAV_ITEMS = [
    ("encode", "编码解码", "encode"),
    ("crypto", "加密解密", "crypto"),
    ("compress", "压缩解压", "compress"),
    ("hash", "哈希计算", "hash"),
    ("smart", "智能解码", "smart"),
    ("files", "文件处理", "files"),
    ("history", "历史记录", "history"),
    ("about", "关于软件", "about"),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1180, 760)
        self.setMinimumSize(960, 620)
        self._set_window_icon()

        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(central)

        # ---- 侧边栏 ----
        self.side = QFrame()
        self.side.setObjectName("dtSide")
        self.side.setFixedWidth(196)
        side_v = QVBoxLayout(self.side)
        side_v.setContentsMargins(10, 12, 10, 10)
        side_v.setSpacing(4)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(9)
        self.logo_lbl = QLabel("DT")
        self.logo_lbl.setFixedSize(28, 28)
        self.logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_lbl.setStyleSheet(
            "border-radius: 8px; background: #10a37f; color: #ffffff; font-weight: 700; font-size: 12px;"
        )
        brand_name = QLabel(APP_NAME)
        brand_name.setStyleSheet("font-weight: 600; font-size: 14px;")
        brand_ver = QLabel(f"v{APP_VERSION}")
        brand_ver.setObjectName("dtMeta")
        brand_row.addWidget(self.logo_lbl)
        brand_row.addWidget(brand_name)
        brand_row.addStretch(1)
        side_v.addLayout(brand_row)

        side_title = QLabel("功能导航")
        side_title.setObjectName("dtSideTitle")
        side_v.addSpacing(10)
        side_v.addWidget(side_title)

        self.nav_buttons = {}
        for idx, (page_id, label, icon_name) in enumerate(NAV_ITEMS):
            b = QPushButton(f" {label}")
            b.setObjectName("dtNav")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setIcon(icons.icon(icon_name, CTX.pal()["fg3"]))
            b.clicked.connect(lambda _=False, i=idx: self.switch_page(i))
            side_v.addWidget(b)
            self.nav_buttons[page_id] = b
            QShortcut(QKeySequence(f"Ctrl+{idx + 1}"), self, lambda i=idx: self.switch_page(i))
        self.nav_buttons["encode"].setChecked(True)
        side_v.addStretch(1)

        # 主题 / 设置按钮
        foot_row = QHBoxLayout()
        foot_row.setSpacing(6)
        self.theme_btn = QPushButton()
        self.theme_btn.setFixedSize(34, 30)
        self.theme_btn.setProperty("variant", "ghost")
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.setToolTip("切换深色 / 浅色主题（Ctrl+T）")
        self.theme_btn.clicked.connect(self.toggle_theme)
        self.settings_btn = QPushButton()
        self.settings_btn.setFixedSize(34, 30)
        self.settings_btn.setProperty("variant", "ghost")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setToolTip("设置（Ctrl+,）")
        self.settings_btn.clicked.connect(self.open_settings)
        foot_row.addWidget(self.theme_btn)
        foot_row.addWidget(self.settings_btn)
        foot_row.addStretch(1)
        side_v.addLayout(foot_row)
        root_layout.addWidget(self.side)

        # ---- 页面栈 ----
        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack, 1)

        self.pages = {}
        page_defs = [
            ("encode", EncodePage), ("crypto", CryptoPage), ("compress", CompressPage),
            ("hash", HashPage), ("smart", SmartPage), ("files", FilesPage),
            ("history", HistoryPage), ("about", AboutPage),
        ]
        for page_id, page_cls in page_defs:
            page = page_cls()
            page.statusMsg.connect(self._set_status)
            page.historyAdd.connect(self._record_history)
            self.stack.addWidget(page)
            self.pages[page_id] = page

        # ---- 状态栏 ----
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.status_label = QLabel("就绪 · 完全离线运行")
        sb.addWidget(self.status_label)
        self.right_status = QLabel(f"UTF-8 · 离线模式 · v{APP_VERSION}")
        sb.addPermanentWidget(self.right_status)

        QShortcut(QKeySequence("Ctrl+T"), self, self.toggle_theme)
        QShortcut(QKeySequence("Ctrl+,"), self, self.open_settings)

        self.switch_page(0)

    # ------------------------------------------------------------------
    def _set_window_icon(self):
        self.setWindowIcon(icons.app_icon(32))

    def apply_theme(self, theme_name: str, save: bool = True):
        CTX.set_theme(theme_name)
        QApplication.instance().setStyleSheet(build_qss(theme_name))
        self._refresh_theme_icons()
        if save:
            config.set_setting("theme", theme_name)
        for page in self.pages.values():
            page.on_theme_changed(theme_name)

    def _refresh_theme_icons(self):
        pal = CTX.pal()
        icons.clear_cache()
        for page_id, (page_key, label, icon_name) in zip(self.nav_buttons.keys(), NAV_ITEMS):
            btn = self.nav_buttons[page_key]
            btn.setIcon(icons.icon(icon_name, pal["accent"] if btn.isChecked() else pal["fg3"]))
        self.theme_btn.setIcon(icons.icon("moon" if CTX.theme == "dark" else "sun", pal["fg2"]))
        self.settings_btn.setIcon(icons.icon("settings", pal["fg2"]))
        self.right_status.setText(f"{CTX.theme.upper()} · UTF-8 · 离线模式 · v{APP_VERSION}")

    def toggle_theme(self):
        new_theme = "light" if CTX.theme == "dark" else "dark"
        self.apply_theme(new_theme)
        self._set_status(f"已切换到{'深色' if new_theme == 'dark' else '浅色'}主题")

    def open_settings(self):
        dlg = SettingsDialog(self, on_theme_change=lambda t: self.apply_theme(t, save=False))
        if dlg.exec():
            self._set_status("设置已保存")
            self.apply_theme(CTX.theme, save=False)
        self._refresh_theme_icons()

    def switch_page(self, index: int):
        page_id = NAV_ITEMS[index][0]
        self.stack.setCurrentIndex(index)
        for pid, btn in self.nav_buttons.items():
            btn.setChecked(pid == page_id)
        self._refresh_theme_icons()
        page = self.pages[page_id]
        page.on_show()

    # ------------------------------------------------------------------
    def _set_status(self, text: str):
        self.status_label.setText(text)

    def _record_history(self, page: str, op: str, detail: str):
        try:
            history.add_entry(page, op, detail, limit=int(config.get_setting("history_limit") or 200))
        except Exception:
            pass  # 历史记录失败不影响主流程

    # ------------------------------------------------------------------
    def closeEvent(self, event):
        for page in self.pages.values():
            try:
                page.shutdown_workers()
            except Exception:
                pass
        super().closeEvent(event)
