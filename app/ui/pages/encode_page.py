"""编码解码页：12 种编解码器 + 批量逐行 + 自动识别 + 一键交换。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core import batch as batch_mod
from ...core import detect, encoders
from .. import icons
from ..context import CTX
from ..widgets import (
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

PAGE_NAME = "编码解码"


class EncodePage(PageBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        header = PageHeader(
            PAGE_NAME,
            "Base64 · Base32 · Base58 · Base62 · Hex · URL · HTML 实体 · Unicode · ASCII · ROT13 · Quoted-Printable，UTF-8 中文安全",
        )
        self.fav_btn = btn("收藏此页", "star")
        self.fav_btn.setProperty("variant", "ghost")
        set_btn_icon(self.fav_btn, "star", "fg2")
        self.fav_btn.clicked.connect(self._toggle_fav)
        header.add_action(self.fav_btn)
        root.addWidget(header)

        # ---- 输入区 ----
        self.in_card, self.in_header, self.in_edit = io_card("输入内容", "0 字符", min_lines=4)
        self.in_edit.textChanged.connect(self._update_in_meta)
        self.paste_btn = btn("粘贴", "paste")
        set_btn_icon(self.paste_btn, "paste")
        self.paste_btn.clicked.connect(self._paste)
        self.import_btn = btn("导入文件", "upload")
        set_btn_icon(self.import_btn, "upload")
        self.import_btn.clicked.connect(self._import_file)
        self.in_clear_btn = btn("清空", "eraser")
        set_btn_icon(self.in_clear_btn, "eraser")
        self.in_clear_btn.clicked.connect(lambda: (self.in_edit.setPlainText(""), self._update_in_meta()))
        self.in_header.add_button(self.paste_btn)
        self.in_header.add_button(self.import_btn)
        self.in_header.add_button(self.in_clear_btn)
        root.addWidget(self.in_card)

        # ---- 操作区 ----
        op_card = make_card()
        op_v = QVBoxLayout(op_card)
        op_v.setContentsMargins(14, 11, 14, 11)
        op_v.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(10)

        self.algo_label = QLabel("算法")
        self.algo_label.setObjectName("dtMeta")
        self.algo_combo = QComboBox()
        for cid in encoders.CODEC_ORDER:
            self.algo_combo.addItem(encoders.get_codec(cid).name, cid)
        self.algo_combo.setMinimumWidth(180)
        self.algo_combo.currentIndexChanged.connect(self._on_algo_change)

        self.dir_label = QLabel("方向")
        self.dir_label.setObjectName("dtMeta")
        self.seg_frame = QFrame()
        self.seg_frame.setObjectName("dtSegFrame")
        seg_h = QHBoxLayout(self.seg_frame)
        seg_h.setContentsMargins(2, 2, 2, 2)
        seg_h.setSpacing(2)
        self.enc_btn = QPushButton("编码")
        self.dec_btn = QPushButton("解码")
        for b in (self.enc_btn, self.dec_btn):
            b.setObjectName("dtSeg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.enc_btn.setChecked(True)
        seg_h.addWidget(self.enc_btn)
        seg_h.addWidget(self.dec_btn)
        # 互斥：同一时间只有一个方向处于选中态
        self._dir_group = QButtonGroup(self)
        self._dir_group.setExclusive(True)
        self._dir_group.addButton(self.enc_btn)
        self._dir_group.addButton(self.dec_btn)

        self.batch_chk = QCheckBox("逐行批量（每行独立处理）")
        self.batch_chk.setToolTip("勾选后对多行文本逐行独立执行，输出带行号，失败的行显示错误原因")

        self.exec_btn = btn("执行", "play", variant="primary")
        set_btn_icon(self.exec_btn, "play", "accent_fg")
        self.exec_btn.clicked.connect(self._execute)

        self.detect_btn = btn("自动识别", "detect")
        set_btn_icon(self.detect_btn, "detect")
        self.detect_btn.clicked.connect(self._detect)

        self.swap_btn = btn("交换", "swap")
        set_btn_icon(self.swap_btn, "swap")
        self.swap_btn.setToolTip("交换输入与输出内容")
        self.swap_btn.clicked.connect(self._swap)

        for w in (self.algo_label, self.algo_combo, self.dir_label, self.seg_frame, self.batch_chk):
            row.addWidget(w)
        row.addStretch(1)
        for w in (self.swap_btn, self.detect_btn, self.exec_btn):
            row.addWidget(w)
        op_v.addLayout(row)

        self.params_row = QHBoxLayout()
        self.params_row.setSpacing(10)
        op_v.addLayout(self.params_row)

        self.hint_lbl = QLabel("")
        self.hint_lbl.setObjectName("dtHint")
        self.hint_lbl.setWordWrap(True)
        op_v.addWidget(self.hint_lbl)
        root.addWidget(op_card)

        # ---- 自动识别结果 ----
        self.detect_lbl = banner("info", "")
        self.detect_lbl.hide()
        root.addWidget(self.detect_lbl)

        # ---- 输出区 ----
        self.out_card, self.out_header, self.out_edit = io_card("输出结果", "", readonly=True, min_lines=4)
        self.copy_btn = btn("复制结果", "copy")
        set_btn_icon(self.copy_btn, "copy")
        self.copy_btn.clicked.connect(self._copy)
        self.save_btn = btn("保存结果", "save")
        set_btn_icon(self.save_btn, "save")
        self.save_btn.clicked.connect(self._save)
        self.out_clear_btn = btn("清空", "eraser")
        set_btn_icon(self.out_clear_btn, "eraser")
        self.out_clear_btn.clicked.connect(lambda: (self.out_edit.set_result_text(""), set_chip(self.out_header.chip_lbl, "", "")))
        self.out_header.add_button(self.copy_btn)
        self.out_header.add_button(self.save_btn)
        self.out_header.add_button(self.out_clear_btn)
        root.addWidget(self.out_card)

        root.addStretch(1)

        self._on_algo_change()
        QShortcut(QKeySequence("Ctrl+Return"), self, self._execute)
        QShortcut(QKeySequence("Ctrl+R"), self, self._swap)
        QShortcut(QKeySequence("Ctrl+Shift+K"), self, self._copy)

    # ------------------------------------------------------------------
    def current_codec(self):
        return encoders.get_codec(self.algo_combo.currentData())

    def _on_algo_change(self):
        while self.params_row.count():
            item = self.params_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        codec = self.current_codec()
        self._param_combos = {}
        for key, label, options in codec.params_schema:
            box = QVBoxLayout()
            box.setSpacing(4)
            lbl = QLabel(label)
            lbl.setObjectName("dtMeta")
            combo = QComboBox()
            for value, text in options:
                combo.addItem(text, value)
            combo.setProperty("dtParamKey", key)
            box.addWidget(lbl)
            box.addWidget(combo)
            holder = QWidget()
            holder.setLayout(box)
            self.params_row.addWidget(holder)
            self._param_combos[key] = combo
        self.params_row.addStretch(1)
        self.hint_lbl.setText(codec.hint)
        self.detect_lbl.hide()

    def collect_params(self) -> dict:
        return {key: combo.currentData() for key, combo in getattr(self, "_param_combos", {}).items()}

    def _direction(self) -> str:
        return "decode" if self.dec_btn.isChecked() else "encode"

    # ------------------------------------------------------------------
    def _update_in_meta(self):
        text = self.in_edit.toPlainText()
        n = len(text)
        self.in_header.set_meta(f"{n:,} 字符 · {len(text.encode('utf-8')):,} 字节" if n else "0 字符")

    def _paste(self):
        from PySide6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        text = cb.text()
        if text:
            self.in_edit.setPlainText(text)
            self.statusMsg.emit(f"已粘贴剪贴板内容（{len(text):,} 字符）")
        else:
            self.statusMsg.emit("剪贴板为空")

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入文件内容", "", "所有文件 (*.*)")
        if path:
            self._load_file(path)

    def _load_file(self, path: str):
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            QMessageBox.warning(self, "导入失败", f"无法读取文件：{exc}")
            return
        text = data.decode("utf-8", errors="replace")
        self.in_edit.setPlainText(text)
        self.statusMsg.emit(f"已导入 {Path(path).name}（{len(data):,} 字节；非 UTF-8 字节已替换显示）")

    def _swap(self):
        out_text = self.out_edit.result_text()
        in_text = self.in_edit.toPlainText()
        self.out_edit.set_result_text(in_text)
        self.in_edit.setPlainText(out_text)
        self.statusMsg.emit("已交换输入与输出内容")

    def _toggle_fav(self):
        from ...core import history
        codec = self.current_codec()
        starred = history.toggle_favorite("codec", codec.id)
        self._refresh_fav()
        self.statusMsg.emit(f"{'已收藏' if starred else '已取消收藏'}「{codec.name}」")

    def _refresh_fav(self):
        from ...core import history
        codec = self.current_codec()
        starred = history.is_favorite("codec", codec.id)
        icons.clear_cache()
        self.fav_btn.setIcon(icons.icon(
            "star",
            CTX.pal()["warn"] if starred else CTX.pal()["fg2"],
            filled=starred,
        ))

    def _detect(self):
        text = self.in_edit.toPlainText()
        result = detect.detect(text)
        if not result.ok:
            set_chip(self.out_header.chip_lbl, "", "")
            self.detect_lbl.setProperty("kind", "err")
            self._repolish(self.detect_lbl)
            self.detect_lbl.setText(f"✕ {result.error}")
            self.detect_lbl.show()
            return
        candidates = result.data
        if not candidates:
            self.detect_lbl.setProperty("kind", "info")
            self._repolish(self.detect_lbl)
            self.detect_lbl.setText(result.meta.get("note", "未检测到常见编码特征"))
            self.detect_lbl.show()
            return
        lines = ["<b>识别候选（按可能性排序，仅供参考，不保证 100% 准确）：</b>"]
        for c in candidates[:6]:
            conf = {"high": "高", "medium": "中", "low": "低"}.get(c.confidence, c.confidence)
            line = f"· <b>{c.name}</b>（置信度：{conf}）—— {c.basis}"
            if c.preview:
                line += f"　→ 预览：<code>{_escape(c.preview)}</code>"
            lines.append(line)
        self.detect_lbl.setProperty("kind", "info")
        self._repolish(self.detect_lbl)
        self.detect_lbl.setText("<br/>".join(lines))
        self.detect_lbl.show()
        self.statusMsg.emit(f"识别完成：{len(candidates)} 个候选")

    @staticmethod
    def _repolish(lbl: QLabel):
        lbl.style().unpolish(lbl)
        lbl.style().polish(lbl)

    # ------------------------------------------------------------------
    def _execute(self):
        import time as _time

        text = self.in_edit.toPlainText()
        if not text.strip():
            set_chip(self.out_header.chip_lbl, "✕ 输入为空：请输入待处理内容", "err")
            self.statusMsg.emit("执行失败：输入为空")
            return
        codec = self.current_codec()
        direction = self._direction()
        params = self.collect_params()
        t0 = _time.perf_counter()
        is_batch = self.batch_chk.isChecked()
        if is_batch:
            result = batch_mod.process_lines(
                text, lambda ln: encoders.run(codec.id, direction, ln, params)
            )
            if result.ok:
                from ...core.batch import format_rows
                shown = format_rows(result.data)
                self.out_edit.set_result_text(shown)
        else:
            result = encoders.run(codec.id, direction, text, params)
            if result.ok:
                self.out_edit.set_result_text(result.data)

        if not result.ok:
            set_chip(self.out_header.chip_lbl, f"✕ {result.error}", "err")
            self.statusMsg.emit(f"执行失败：{result.error}")
            return
        ms = elapsed_ms(t0)
        ok_kind = "ok"
        if is_batch:
            failed = result.meta.get("failed", 0)
            total = result.meta.get("total", 0)
            kind = "ok" if failed == 0 else "warn"
            set_chip(self.out_header.chip_lbl,
                     f"✓ 批量完成 · {total} 行" + (f" · {failed} 行失败" if failed else "") + f" · {ms} 毫秒", kind)
            self.historyAdd.emit(PAGE_NAME,
                                 f"{codec.name} {'解码' if direction == 'decode' else '编码'}（批量）",
                                 f"{total} 行 · {failed} 失败")
        else:
            label = result.meta.get("label", codec.name)
            set_chip(self.out_header.chip_lbl,
                     f"✓ {'解码' if direction == 'decode' else '编码'}成功 · {ms} 毫秒", ok_kind)
            in_size = result.meta.get("in_bytes", len(text))
            out_size = result.meta.get("out_chars", result.meta.get("out_bytes", len(self.out_edit.result_text())))
            self.historyAdd.emit(PAGE_NAME,
                                 f"{label} {'解码' if direction == 'decode' else '编码'}",
                                 f"{in_size:,} → {out_size:,}")
        self.statusMsg.emit(f"{'解码' if direction == 'decode' else '编码'}完成（{codec.name}）· {ms} 毫秒")

    def _copy(self):
        from PySide6.QtWidgets import QApplication
        text = self.out_edit.result_text()
        if not text:
            self.statusMsg.emit("没有可复制的结果")
            return
        QApplication.clipboard().setText(text)
        self.statusMsg.emit(f"已复制完整结果（{len(text):,} 字符）")

    def _save(self):
        text = self.out_edit.result_text()
        if not text:
            self.statusMsg.emit("没有可保存的结果")
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存结果", "devtoolkit-output.txt", "文本文件 (*.txt);;所有文件 (*.*)")
        if not path:
            return
        try:
            Path(path).write_text(text, encoding="utf-8")
            self.statusMsg.emit(f"结果已保存：{Path(path).name}")
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", f"无法写入文件：{exc}")

    # ------------------------------------------------------------------
    def on_theme_changed(self, theme: str):
        from ..widgets import recolor_icons
        recolor_icons(self)
        self._refresh_fav()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self._load_file(urls[0].toLocalFile())
            event.acceptProposedAction()


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
