"""压缩解压页：GZIP / ZLIB / DEFLATE / ZIP / Brotli / Zstandard / LZ4。"""

from __future__ import annotations

import base64
import binascii
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
    QPushButton,
    QVBoxLayout,
)

from ...core import compress_tools as cp
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

PAGE_NAME = "压缩解压"


class CompressPage(PageBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        header = PageHeader(
            PAGE_NAME,
            "GZIP · ZLIB · DEFLATE · ZIP · Brotli · Zstandard · LZ4；支持文本与二进制，输出可用 Base64 展示",
        )
        root.addWidget(header)

        # ---- 输入区 ----
        self.in_card, self.in_header, self.in_edit = io_card("输入内容", "0 字符", min_lines=4)
        self.in_edit.textChanged.connect(lambda: self.in_header.set_meta(
            f"{len(self.in_edit.toPlainText()):,} 字符" if self.in_edit.toPlainText() else "0 字符"))
        self.paste_btn = btn("粘贴", "paste")
        set_btn_icon(self.paste_btn, "paste")
        self.paste_btn.clicked.connect(self._paste)
        self.in_clear_btn = btn("清空", "eraser")
        set_btn_icon(self.in_clear_btn, "eraser")
        self.in_clear_btn.clicked.connect(lambda: self.in_edit.setPlainText(""))
        self.in_header.add_button(self.paste_btn)
        self.in_header.add_button(self.in_clear_btn)
        root.addWidget(self.in_card)

        # ---- 操作区 ----
        op_card = make_card()
        op_v = QVBoxLayout(op_card)
        op_v.setContentsMargins(14, 11, 14, 11)
        op_v.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(10)
        fmt_lbl = QLabel("压缩格式")
        fmt_lbl.setObjectName("dtMeta")
        self.fmt_combo = QComboBox()
        for fmt in cp.FORMATS:
            self.fmt_combo.addItem(cp.FORMAT_NAMES[fmt], fmt)
        lvl_lbl = QLabel("级别")
        lvl_lbl.setObjectName("dtMeta")
        self.lvl_combo = QComboBox()
        self.lvl_combo.addItem("1（最快）", 1)
        self.lvl_combo.addItem("6（推荐）", 6)
        self.lvl_combo.addItem("9（最大压缩）", 9)
        self.lvl_combo.setCurrentIndex(1)

        dir_lbl = QLabel("方向")
        dir_lbl.setObjectName("dtMeta")
        self.seg_frame = QFrame()
        self.seg_frame.setObjectName("dtSegFrame")
        seg_h = QHBoxLayout(self.seg_frame)
        seg_h.setContentsMargins(2, 2, 2, 2)
        seg_h.setSpacing(2)
        self.comp_btn = QPushButton("压缩")
        self.decomp_btn = QPushButton("解压")
        for b in (self.comp_btn, self.decomp_btn):
            b.setObjectName("dtSeg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.comp_btn.setChecked(True)
        seg_h.addWidget(self.comp_btn)
        seg_h.addWidget(self.decomp_btn)

        self.b64_chk = QCheckBox("输出以 Base64 显示")
        self.b64_chk.setChecked(True)
        self.auto_b64_chk = QCheckBox("解压前自动尝试 Base64 解码")
        self.auto_b64_chk.setChecked(True)

        self.exec_btn = btn("执行", "play", variant="primary")
        set_btn_icon(self.exec_btn, "play", "accent_fg")
        self.exec_btn.clicked.connect(self._execute)

        for w in (fmt_lbl, self.fmt_combo, lvl_lbl, self.lvl_combo, dir_lbl, self.seg_frame,
                  self.b64_chk, self.auto_b64_chk):
            row.addWidget(w)
        row.addStretch(1)
        row.addWidget(self.exec_btn)
        op_v.addLayout(row)
        root.addWidget(op_card)

        # ---- 输出区 ----
        self.out_card, self.out_header, self.out_edit = io_card("输出结果", "", readonly=True, min_lines=4)
        self.copy_btn = btn("复制结果", "copy")
        set_btn_icon(self.copy_btn, "copy")
        self.copy_btn.clicked.connect(self._copy)
        self.save_btn = btn("保存二进制结果", "save")
        set_btn_icon(self.save_btn, "save")
        self.save_btn.clicked.connect(self._save)
        self.out_clear_btn = btn("清空", "eraser")
        set_btn_icon(self.out_clear_btn, "eraser")
        self.out_clear_btn.clicked.connect(lambda: (self.out_edit.set_result_text(""), set_chip(self.out_header.chip_lbl, "", "")))
        self.out_header.add_button(self.copy_btn)
        self.out_header.add_button(self.save_btn)
        self.out_header.add_button(self.out_clear_btn)
        root.addWidget(self.out_card)

        self.cap_note = banner("info", "解压防护：输出上限 512 MB（可在设置调整），超限自动终止 —— 防压缩炸弹；无法识别的格式会提示并保留原始输入。")
        root.addWidget(self.cap_note)
        root.addStretch(1)

        self._binary_out = None
        QShortcut(QKeySequence("Ctrl+Return"), self, self._execute)

    # ------------------------------------------------------------------
    def _direction(self) -> str:
        return "decompress" if self.decomp_btn.isChecked() else "compress"

    def _paste(self):
        from PySide6.QtWidgets import QApplication
        text = QApplication.clipboard().text()
        if text:
            self.in_edit.setPlainText(text)
            self.statusMsg.emit(f"已粘贴剪贴板内容（{len(text):,} 字符）")
        else:
            self.statusMsg.emit("剪贴板为空")

    # ------------------------------------------------------------------
    def _execute(self):
        import time as _time

        from ...core import config
        cap_mb = int(config.get_setting("decompress_cap_mb") or 512)
        self.cap_note.setText(
            f"解压防护：输出上限 {cap_mb} MB（可在设置调整），超限自动终止 —— 防压缩炸弹；"
            "无法识别的格式会提示并保留原始输入。"
        )
        t0 = _time.perf_counter()
        text = self.in_edit.toPlainText()
        self._binary_out = None
        if not text.strip():
            set_chip(self.out_header.chip_lbl, "✕ 输入为空：请输入待处理内容", "err")
            return
        fmt = self.fmt_combo.currentData()
        direction = self._direction()

        if direction == "compress":
            data = text.encode("utf-8")
            r = cp.compress(data, fmt, self.lvl_combo.currentData())
            if not r.ok:
                set_chip(self.out_header.chip_lbl, f"✕ {r.error}", "err")
                self.statusMsg.emit(f"压缩失败：{r.error}")
                return
            self._binary_out = r.data
            if self.b64_chk.isChecked():
                self.out_edit.set_result_text(base64.b64encode(r.data).decode("ascii"))
            else:
                self.out_edit.set_result_text(r.data.hex())
            ratio = (1 - len(r.data) / len(data)) * 100 if len(data) else 0
            set_chip(self.out_header.chip_lbl,
                     f"✓ 压缩成功 · {len(data):,} B → {len(r.data):,} B（-{ratio:.1f}%）· {elapsed_ms(t0)} 毫秒", "ok")
            self.historyAdd.emit(PAGE_NAME, f"{cp.FORMAT_NAMES[fmt]} 压缩",
                                 f"{len(data):,} B → {len(r.data):,} B")
            self.statusMsg.emit(f"压缩完成 · {elapsed_ms(t0)} 毫秒")
        else:
            raw = text.encode("utf-8")
            data = None
            if self.auto_b64_chk.isChecked():
                compact = "".join(text.split())
                try:
                    data = base64.b64decode(compact, validate=True)
                except (binascii.Error, ValueError):
                    data = None
            if data is None:
                data = raw
            # 自动识别格式兜底：用户选的格式解不开时，尝试按魔数识别
            r = cp.decompress(data, fmt, cap_mb)
            if not r.ok and fmt != "deflate":
                sniffed = cp.sniff(data)
                if sniffed and sniffed != fmt:
                    r2 = cp.decompress(data, sniffed, cap_mb)
                    if r2.ok:
                        r = r2
            if not r.ok:
                set_chip(self.out_header.chip_lbl, f"✕ {r.error}", "err")
                self.statusMsg.emit(f"解压失败：{r.error}")
                return
            self._binary_out = r.data
            try:
                text_out = r.data.decode("utf-8")
                self.out_edit.set_result_text(text_out)
                self._binary_out = None
                kind_note = "（UTF-8 文本）"
            except UnicodeDecodeError:
                head = r.data[:96].hex(" ").upper()
                self.out_edit.set_result_text(
                    f"[二进制结果 {len(r.data):,} 字节，前 96 字节预览]\n{head}\n\n请点击「保存二进制结果」导出完整数据。"
                )
                kind_note = "（二进制）"
            set_chip(self.out_header.chip_lbl,
                     f"✓ 解压成功 · {len(data):,} B → {len(r.data):,} B{kind_note} · {elapsed_ms(t0)} 毫秒", "ok")
            self.historyAdd.emit(PAGE_NAME, f"{cp.FORMAT_NAMES[r.meta['fmt']]} 解压",
                                 f"{len(data):,} B → {len(r.data):,} B")
            self.statusMsg.emit(f"解压完成 · {elapsed_ms(t0)} 毫秒")

    def _copy(self):
        from PySide6.QtWidgets import QApplication
        if self._binary_out is not None:
            self.statusMsg.emit("二进制结果请使用「保存二进制结果」导出（复制仅支持文本）")
            return
        text = self.out_edit.result_text()
        if not text:
            self.statusMsg.emit("没有可复制的结果")
            return
        QApplication.clipboard().setText(text)
        self.statusMsg.emit(f"已复制完整结果（{len(text):,} 字符）")

    def _save(self):
        if self._binary_out is not None:
            ext = {fmt: (".gz" if fmt == "gzip" else ".zip" if fmt == "zip" else ".zst" if fmt == "zstd" else ".lz4" if fmt == "lz4" else ".bin")
                   for fmt in cp.FORMATS}
            fmt = self.fmt_combo.currentData()
            default = "devtoolkit-output" + ext.get(fmt, ".bin")
            path, _ = QFileDialog.getSaveFileName(self, "保存二进制结果", default, "所有文件 (*.*)")
            if path:
                try:
                    Path(path).write_bytes(self._binary_out)
                    self.statusMsg.emit(f"已保存二进制结果（{len(self._binary_out):,} 字节）")
                except OSError as exc:
                    QMessageBox.warning(self, "保存失败", f"无法写入文件：{exc}")
            return
        text = self.out_edit.result_text()
        if not text:
            self.statusMsg.emit("没有可保存的结果")
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存结果", "devtoolkit-output.txt", "文本文件 (*.txt);;所有文件 (*.*)")
        if path:
            try:
                Path(path).write_text(text, encoding="utf-8")
                self.statusMsg.emit(f"结果已保存：{Path(path).name}")
            except OSError as exc:
                QMessageBox.warning(self, "保存失败", f"无法写入文件：{exc}")

    def on_theme_changed(self, theme: str):
        from ..widgets import recolor_icons
        recolor_icons(self)
