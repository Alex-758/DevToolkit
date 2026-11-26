"""哈希计算页：10 种哈希同时展示、文件哈希（后台线程 + 进度）、哈希比较、逐行批量。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ...core import config, hashing
from ..widgets import (
    WorkerRunner,
    CardHeader,
    PageHeader,
    banner,
    btn,
    elapsed_ms,
    io_card,
    make_card,
    set_btn_icon,
    set_chip,
)
from . import PageBase

PAGE_NAME = "哈希计算"


class HashPage(PageBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        header = PageHeader(
            PAGE_NAME,
            "输入即自动计算全部 10 种哈希 · 支持文件哈希 · bcrypt / Argon2 属密码哈希，后续版本单独提供",
        )
        self.file_btn = btn("计算文件哈希", "file")
        set_btn_icon(self.file_btn, "file")
        self.file_btn.clicked.connect(self._pick_file)
        header.add_action(self.file_btn)
        root.addWidget(header)

        # ---- 输入区 ----
        self.in_card, self.in_header, self.in_edit = io_card("输入内容", "0 字符", min_lines=4)
        self.batch_chk = QCheckBox("逐行批量（每行独立哈希）")
        self.upper_chk = QCheckBox("大写输出")
        self.upper_chk.toggled.connect(lambda _: self._recompute_now())
        self.batch_chk.toggled.connect(lambda _: self._recompute_now())
        self.in_clear_btn = btn("清空", "eraser")
        set_btn_icon(self.in_clear_btn, "eraser")
        self.in_clear_btn.clicked.connect(lambda: self.in_edit.setPlainText(""))
        self.in_header.add_button(self.batch_chk)
        self.in_header.add_button(self.upper_chk)
        self.in_header.add_button(self.in_clear_btn)
        root.addWidget(self.in_card)

        # ---- 哈希结果卡 ----
        self.hash_card = make_card()
        hash_v = QVBoxLayout(self.hash_card)
        hash_v.setContentsMargins(1, 1, 1, 1)
        self.hash_header = CardHeader("哈希结果", "输入变化后 300ms 自动重算")
        self.copy_all_btn = btn("复制全部", "copy")
        set_btn_icon(self.copy_all_btn, "copy")
        self.copy_all_btn.clicked.connect(self._copy_all)
        self.hash_header.add_button(self.copy_all_btn)
        hash_v.addWidget(self.hash_header)
        grid_holder = QWidget()
        self.hash_grid = QGridLayout(grid_holder)
        self.hash_grid.setHorizontalSpacing(10)
        self.hash_grid.setVerticalSpacing(6)
        self.hash_grid.setContentsMargins(12, 6, 12, 12)
        self._hash_rows = {}
        for i, (algo, name, note) in enumerate(hashing.HASH_ALGOS):
            # 单列布局：56/64 字符的 SHA-224/256/384/512 摘要约需 470px 宽，
            # 双列布局在默认窗口下值框只有 ~420px，摘要被无声截断（文字不完整）
            row, col = i, 0
            lbl = QLabel(name)
            lbl.setObjectName("dtMeta")
            lbl.setFixedWidth(86)
            val = QLineEdit()
            val.setReadOnly(True)
            val.setProperty("mono", True)
            val.setFont(MONO_FONT_())
            val.setCursorPosition(0)
            copy_b = btn("", "copy")
            set_btn_icon(copy_b, "copy")
            copy_b.setFixedSize(26, 24)
            copy_b.setToolTip(f"复制 {name}")
            copy_b.clicked.connect(lambda _=False, a=algo: self._copy_one(a))
            self.hash_grid.addWidget(lbl, row, col * 3)
            self.hash_grid.addWidget(val, row, col * 3 + 1)
            self.hash_grid.addWidget(copy_b, row, col * 3 + 2)
            self._hash_rows[algo] = (lbl, val)
        self.hash_grid.setColumnStretch(1, 1)
        hash_v.addWidget(grid_holder)
        root.addWidget(self.hash_card)

        # ---- 文件哈希进度 ----
        self.prog_card = make_card()
        prog_h = QHBoxLayout(self.prog_card)
        prog_h.setContentsMargins(14, 11, 14, 11)
        self.prog_lbl = QLabel("文件哈希")
        self.prog_lbl.setObjectName("dtCardTitle")
        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.cancel_btn = btn("取消", "alert")
        set_btn_icon(self.cancel_btn, "alert")
        self.cancel_btn.clicked.connect(self._cancel_file_hash)
        prog_h.addWidget(self.prog_lbl)
        prog_h.addWidget(self.prog_bar, 1)
        prog_h.addWidget(self.cancel_btn)
        self.prog_card.hide()
        root.addWidget(self.prog_card)

        # ---- 比较区 ----
        self.cmp_card = make_card()
        cmp_header = CardHeader("哈希比较", "忽略大小写与空白，适合下载校验")
        self.cmp_card_v = QVBoxLayout()
        self.cmp_card_v.setContentsMargins(1, 1, 1, 1)
        self.cmp_card_v.addWidget(cmp_header)
        cmp_inner = QWidget()
        cmp_grid = QGridLayout(cmp_inner)
        cmp_grid.setContentsMargins(12, 4, 12, 10)
        cmp_grid.setHorizontalSpacing(10)
        cmp_grid.setVerticalSpacing(8)
        a_lbl = QLabel("哈希值 A")
        a_lbl.setObjectName("dtMeta")
        b_lbl = QLabel("哈希值 B")
        b_lbl.setObjectName("dtMeta")
        self.cmp_a = QLineEdit()
        self.cmp_a.setProperty("mono", True)
        self.cmp_a.setFont(MONO_FONT_())
        self.cmp_a.textChanged.connect(self._compare)
        self.cmp_b = QLineEdit()
        self.cmp_b.setProperty("mono", True)
        self.cmp_b.setFont(MONO_FONT_())
        self.cmp_b.textChanged.connect(self._compare)
        self.cmp_chip = QLabel("输入两个哈希值后自动比较")
        self.cmp_chip.setProperty("dtChip", True)
        cmp_grid.addWidget(a_lbl, 0, 0)
        cmp_grid.addWidget(self.cmp_a, 0, 1)
        cmp_grid.addWidget(b_lbl, 1, 0)
        cmp_grid.addWidget(self.cmp_b, 1, 1)
        cmp_grid.addWidget(self.cmp_chip, 2, 1)
        cmp_grid.setColumnStretch(1, 1)
        self.cmp_card_v.addWidget(cmp_inner)
        self.cmp_card.setLayout(self.cmp_card_v)
        root.addWidget(self.cmp_card)

        self.banner_lbl = banner("info", "出于安全考虑，哈希结果可写入历史，但文件路径中的敏感信息会保留在本地，不会上传。")
        root.addWidget(self.banner_lbl)
        root.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._recompute_now)
        self.in_edit.textChanged.connect(self._on_input_changed)

        self.file_runner = WorkerRunner(self._on_file_hash_done, self._on_file_hash_progress, self)
        self._current_file = ""
        self._file_results = {}

        QShortcut(QKeySequence("Ctrl+Return"), self, self._recompute_now)
        self._recompute_now()

    # ------------------------------------------------------------------
    def _on_input_changed(self):
        self._timer.start()

    def _recompute_now(self):
        import time as _time
        t0 = _time.perf_counter()
        text = self.in_edit.toPlainText()
        if self.batch_chk.isChecked():
            from ...core import batch as batch_mod
            r = batch_mod.process_lines(
                text, lambda ln: hashing.text_hash(ln, "sha256"),
                skip_empty=bool(config.get_setting("batch_skip_empty")),
            )
            if r.ok:
                from ...core.batch import format_rows
                for algo, (lbl, val) in self._hash_rows.items():
                    if algo == "sha256":
                        shown = format_rows(r.data, with_index=True, with_errors=False) or ""
                        val.setText(shown)
                        val.setToolTip(shown)
                    else:
                        val.setText("（逐行模式下仅计算 SHA-256，其他算法见批量结果）")
                        val.setToolTip("")
                self.hash_header.set_meta(f"{r.meta['total']} 行 · SHA-256")
                return
        r = hashing.text_hash_all(text)
        if not r.ok:
            for algo, (lbl, val) in self._hash_rows.items():
                val.setText("")
                val.setToolTip("")
            set_chip(self.hash_header.chip_lbl, f"✕ {r.error}", "err")
            return
        for algo, (lbl, val) in self._hash_rows.items():
            v = r.data[algo]
            shown = v.upper() if self.upper_chk.isChecked() else v
            val.setText(shown)
            # 值框较窄时悬停可看完整摘要（R5 UI 审计：长摘要曾无声截断）
            val.setToolTip(shown)
            val.setCursorPosition(0)
        ms = elapsed_ms(t0)
        n = len(text)
        set_chip(self.hash_header.chip_lbl, f"✓ 已计算 {len(r.data)} 种 · {n:,} 字符 · {ms} 毫秒", "ok")

    def _copy_one(self, algo: str):
        from PySide6.QtWidgets import QApplication
        val = self._hash_rows[algo][1].text()
        if not val:
            self.statusMsg.emit("没有可复制的哈希值")
            return
        QApplication.clipboard().setText(val)
        self.statusMsg.emit(f"已复制 {hashing.algo_display(algo)} 哈希值")

    def _copy_all(self):
        from PySide6.QtWidgets import QApplication
        lines = []
        for algo, (lbl, val) in self._hash_rows.items():
            if val.text():
                lines.append(f"{hashing.algo_display(algo)}\t{val.text()}")
        if not lines:
            self.statusMsg.emit("没有可复制的哈希值")
            return
        QApplication.clipboard().setText("\n".join(lines))
        self.statusMsg.emit(f"已复制全部 {len(lines)} 种哈希值")

    def _compare(self):
        r = hashing.compare(self.cmp_a.text(), self.cmp_b.text())
        if not r.ok:
            set_chip(self.cmp_chip, "输入两个哈希值后自动比较", "")
        elif r.data:
            set_chip(self.cmp_chip, "✓ 完全一致（忽略大小写与空白）", "ok")
        else:
            set_chip(self.cmp_chip, "✕ 不一致 —— 两个哈希值不同", "err")

    # ---- 文件哈希 ----
    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择要计算哈希的文件", "", "所有文件 (*.*)")
        if not path:
            return
        self._start_file_hash(path)

    def _start_file_hash(self, path: str):
        algos = hashing.ALGO_IDS
        self._current_file = path
        self.prog_card.show()
        self.prog_bar.setValue(0)
        self.prog_lbl.setText(f"正在计算：{Path(path).name}")
        self.file_runner.start(lambda worker: hashing.file_hash(
            path, algos, progress=lambda d, t: worker.report(d, t),
            cancel_check=worker.is_cancelled,
        ))

    def _on_file_hash_progress(self, done: int, total: int):
        pct = int(done * 100 / total) if total else 0
        self.prog_bar.setValue(pct)

    def _on_file_hash_done(self, result):
        self.prog_card.hide()
        if not result.ok:
            if "已取消" in result.error:
                self.statusMsg.emit("文件哈希已取消")
                return
            QMessageBox.warning(self, "文件哈希失败", result.error)
            return
        self._file_results = result.data
        for algo, (lbl, val) in self._hash_rows.items():
            v = result.data.get(algo, "")
            val.setText(v.upper() if self.upper_chk.isChecked() else v)
            val.setCursorPosition(0)
        name = Path(self._current_file).name
        set_chip(self.hash_header.chip_lbl,
                 f"✓ 文件 {name} · {result.meta['in_bytes']:,} 字节", "ok")
        self.in_edit.setPlainText("")
        # 清空输入会同步触发 textChanged 并重启 300ms 自动重算定时器，
        # 若不停止，定时器到点会用「空文本哈希」覆盖刚显示的文件哈希结果
        self._timer.stop()
        self.historyAdd.emit(PAGE_NAME, "文件哈希", f"{name} · {result.meta['in_bytes']:,} 字节")
        self.statusMsg.emit(f"文件哈希完成：{name}")

    def _cancel_file_hash(self):
        self.file_runner.stop()
        self.statusMsg.emit("正在取消文件哈希…")

    def on_theme_changed(self, theme: str):
        from ..widgets import recolor_icons
        recolor_icons(self)


def MONO_FONT_():
    from ..widgets import MONO_FONT
    return MONO_FONT
