"""历史记录页：查看 / 搜索 / 筛选 / 删除 / 清空；附安全说明。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ...core import history
from ..widgets import (
    CardHeader,
    PageHeader,
    banner,
    btn,
    make_card,
    set_btn_icon,
    set_chip,
)
from . import PageBase

PAGE_NAME = "历史记录"

PAGES = ["编码解码", "加密解密", "压缩解压", "哈希计算", "智能解码", "文件处理"]


class HistoryPage(PageBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        header = PageHeader(PAGE_NAME, "最近操作记录 · 支持单条删除与一键清空 · 最多保留 200 条")
        self.clear_btn = btn("清空历史", "trash", variant="danger")
        set_btn_icon(self.clear_btn, "trash", "err")
        self.clear_btn.clicked.connect(self._clear_all)
        header.add_action(self.clear_btn)
        root.addWidget(header)

        # ---- 筛选行 ----
        filter_card = make_card()
        filter_h = QHBoxLayout(filter_card)
        filter_h.setContentsMargins(14, 11, 14, 11)
        filter_h.setSpacing(10)
        search_lbl = QLabel("搜索")
        search_lbl.setObjectName("dtMeta")
        filter_h.addWidget(search_lbl)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("按操作类型或内容搜索历史…")
        self.search_input.textChanged.connect(self._refresh)
        filter_h.addWidget(self.search_input, 1)
        page_lbl = QLabel("页面")
        page_lbl.setObjectName("dtMeta")
        self.page_combo = QComboBox()
        self.page_combo.addItem("全部", "")
        for p in PAGES:
            self.page_combo.addItem(p, p)
        self.page_combo.currentIndexChanged.connect(self._refresh)
        filter_h.addWidget(page_lbl)
        filter_h.addWidget(self.page_combo)
        root.addWidget(filter_card)

        # ---- 列表 ----
        list_card = make_card()
        list_v = QVBoxLayout(list_card)
        list_v.setContentsMargins(1, 1, 1, 1)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["时间", "页面", "操作", "摘要"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(False)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.tree.setColumnWidth(0, 110)
        self.tree.setColumnWidth(1, 90)
        self.tree.setColumnWidth(2, 190)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        list_v.addWidget(self.tree)
        root.addWidget(list_card, 1)

        self.safe_banner = banner(
            "ok",
            "出于安全考虑：密钥、口令、明文与密文内容不会写入历史记录，仅保存操作类型、参数摘要与数据规模。",
        )
        root.addWidget(self.safe_banner)

    # ------------------------------------------------------------------
    def on_show(self):
        self._refresh()

    def _refresh(self):
        self.tree.clear()
        keyword = self.search_input.text().strip().lower()
        page_filter = self.page_combo.currentData()
        entries = history.list_entries()
        shown = 0
        for i, entry in enumerate(entries):
            if page_filter and entry.get("page") != page_filter:
                continue
            text = f"{entry.get('op', '')} {entry.get('detail', '')}".lower()
            if keyword and keyword not in text:
                continue
            item = QTreeWidgetItem([entry.get("ts", ""), entry.get("page", ""), entry.get("op", ""), entry.get("detail", "")])
            item.setData(0, Qt.ItemDataRole.UserRole, i)  # 真实下标（用于删除）
            self.tree.addTopLevelItem(item)
            shown += 1
        self.safe_banner.setText(
            f"共 {len(entries)} 条记录，当前显示 {shown} 条 · 密钥、口令、明文与密文内容不会写入历史记录，仅保存操作类型、参数摘要与数据规模。"
        )

    def _context_menu(self, pos):
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        del_action = menu.addAction("删除选中记录")
        act = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if act == del_action:
            self._delete_selected()

    def _delete_selected(self):
        items = self.tree.selectedItems()
        if not items:
            self.statusMsg.emit("请先选择要删除的记录")
            return
        indexes = sorted((item.data(0, Qt.ItemDataRole.UserRole) for item in items), reverse=True)
        for idx in indexes:
            history.remove_entry(idx)
        self.statusMsg.emit(f"已删除 {len(indexes)} 条记录")
        self._refresh()

    def _clear_all(self):
        count = len(history.list_entries())
        if count == 0:
            self.statusMsg.emit("历史记录已为空")
            return
        confirm = QMessageBox.question(
            self, "清空历史记录",
            f"确定要清空全部 {count} 条历史记录吗？此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            history.clear_entries()
            self.statusMsg.emit("历史记录已清空")
            self._refresh()

    def on_theme_changed(self, theme: str):
        from ..widgets import recolor_icons
        recolor_icons(self)
