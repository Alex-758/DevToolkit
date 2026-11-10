"""智能解码页：多层链路解码 + 处理步骤展示。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core import smart_decode
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

PAGE_NAME = "智能解码"


class SmartPage(PageBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        header = PageHeader(
            PAGE_NAME,
            "自动尝试「编码 + 压缩」的多层组合链路，逐层展示处理过程；仅给出候选结果，不保证 100% 准确",
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

        # ---- 参数区 ----
        op_card = make_card()
        op_v = QVBoxLayout(op_card)
        op_v.setContentsMargins(14, 11, 14, 11)
        op_v.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(12)
        layers_lbl = QLabel("最大解码层数")
        layers_lbl.setObjectName("dtMeta")
        self.layers_spin = QSpinBox()
        self.layers_spin.setRange(1, smart_decode.MAX_LAYERS)
        self.layers_spin.setValue(int(smart_decode.DEFAULT_LAYERS))
        self.layers_spin.setToolTip("防止无限递归；超过层数自动终止并保留当前结果")
        self.try_comp_chk = QCheckBox("自动尝试压缩格式（GZIP / ZLIB / ZIP / Zstd / LZ4）")
        self.try_comp_chk.setChecked(True)
        self.run_btn = btn("开始分析", "smart", variant="primary")
        set_btn_icon(self.run_btn, "smart", "accent_fg")
        self.run_btn.clicked.connect(self._run)
        row.addWidget(layers_lbl)
        row.addWidget(self.layers_spin)
        row.addWidget(self.try_comp_chk)
        row.addStretch(1)
        row.addWidget(self.run_btn)
        op_v.addLayout(row)
        self.param_banner = banner("info", "防压缩炸弹：单次解压输出上限 512 MB（可在设置调整）；已处理内容不会重复解码；解码失败保留原始输入。")
        op_v.addWidget(self.param_banner)
        root.addWidget(op_card)

        # ---- 链路卡 ----
        self.chain_card = make_card()
        self.chain_header = CardHeader("处理链路", "")
        self.chain_inner = QWidget()
        self.chain_v = QVBoxLayout(self.chain_inner)
        self.chain_v.setContentsMargins(12, 4, 12, 10)
        self.chain_v.setSpacing(8)
        chain_scroll = QScrollArea()
        chain_scroll.setWidgetResizable(True)
        chain_scroll.setWidget(self.chain_inner)
        chain_scroll.setMinimumHeight(120)
        chain_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        chain_wrap = QVBoxLayout()
        chain_wrap.setContentsMargins(1, 1, 1, 1)
        chain_wrap.addWidget(chain_scroll)
        self.chain_card_layout = QVBoxLayout(self.chain_card)
        self.chain_card_layout.setContentsMargins(1, 1, 1, 1)
        self.chain_card_layout.addWidget(self.chain_header)
        self.chain_card_layout.addLayout(chain_wrap)
        self.chain_card.hide()
        root.addWidget(self.chain_card)

        # ---- 结果区 ----
        self.out_card, self.out_header, self.out_edit = io_card("解码结果", "", readonly=True, min_lines=4)
        self.copy_btn = btn("复制结果", "copy")
        set_btn_icon(self.copy_btn, "copy")
        self.copy_btn.clicked.connect(self._copy)
        self.save_btn = btn("保存链路报告", "save")
        set_btn_icon(self.save_btn, "save")
        self.save_btn.clicked.connect(self._save_report)
        self.out_header.add_button(self.copy_btn)
        self.out_header.add_button(self.save_btn)
        root.addWidget(self.out_card)
        root.addStretch(1)

        self.smart_runner = WorkerRunner(self._on_done, None, self)
        QShortcut(QKeySequence("Ctrl+Return"), self, self._run)

    # ------------------------------------------------------------------
    def _paste(self):
        from PySide6.QtWidgets import QApplication
        text = QApplication.clipboard().text()
        if text:
            self.in_edit.setPlainText(text)
            self.statusMsg.emit(f"已粘贴剪贴板内容（{len(text):,} 字符）")
        else:
            self.statusMsg.emit("剪贴板为空")

    def _run(self):
        import time as _time

        text = self.in_edit.toPlainText()
        if not text.strip():
            set_chip(self.out_header.chip_lbl, "✕ 输入为空：请输入待解码内容", "err")
            return
        self.run_btn.setEnabled(False)
        set_chip(self.out_header.chip_lbl, "… 正在分析", "info")
        max_layers = self.layers_spin.value()
        cap_mb = int(self._setting("decompress_cap_mb") or 512)

        def job(worker):
            t0 = _time.perf_counter()
            r = smart_decode.smart_decode(text, max_layers=max_layers, cap_mb=cap_mb)
            return r

        self.smart_runner.start(job)

    def _setting(self, key):
        from ...core import config
        return config.get_setting(key)

    def _on_done(self, result):
        import time as _time
        self.run_btn.setEnabled(True)
        if not result.ok:
            set_chip(self.out_header.chip_lbl, f"✕ {result.error}", "err")
            self.statusMsg.emit(f"分析失败：{result.error}")
            return
        sr = result.data
        # 渲染链路
        while self.chain_v.count():
            item = self.chain_v.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not sr.steps:
            self.chain_card.hide()
        else:
            self.chain_card.show()
            self.chain_header.set_meta(f"{sr.chain} · 共 {sr.layers_used} 层 · {result.meta.get('note', '')}")
            for step in sr.steps:
                self.chain_v.addWidget(self._step_widget(step))
            self.chain_v.addStretch(1)
        self.out_edit.set_result_text(sr.final_text)
        set_chip(self.out_header.chip_lbl,
                 f"✓ 完成 · {sr.layers_used} 层解码 · {len(sr.final_text):,} 字符" if sr.layers_used
                 else "未识别到可解码特征，保留原始输入",
                 "ok" if sr.layers_used else "")
        self.historyAdd.emit(PAGE_NAME, "智能解码",
                             f"{sr.chain} · {sr.layers_used} 层 · 输出 {len(sr.final_text):,} 字符" if sr.layers_used
                             else "无特征，保留原文")
        self.statusMsg.emit(f"智能解码完成：{result.meta.get('note', '')}")

    def _step_widget(self, step):
        card = make_card()
        card.setProperty("dtStep", step)  # 保存步骤对象供重绘与报告使用
        v = QVBoxLayout(card)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(4)
        top = QHBoxLayout()
        num = QLabel(f"{step.index}")
        num.setFixedSize(24, 24)
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setStyleSheet(
            f"border-radius:12px; background: {self._accent_soft()}; color: {self._accent()}; font-weight:600;"
        )
        name = QLabel(step.action)
        name.setObjectName("dtCardTitle")
        meta = QLabel(f"{step.before_size} → {step.after_size}")
        meta.setObjectName("dtMeta")
        top.addWidget(num)
        top.addWidget(name)
        top.addStretch(1)
        top.addWidget(meta)
        v.addLayout(top)
        detail = QLabel(step.detail)
        detail.setObjectName("dtHint")
        detail.setWordWrap(True)
        v.addWidget(detail)
        after = QLabel(f"结果预览：{_escape(step.after_preview)}")
        after.setProperty("mono", True)
        after.setFont(MONO_FONT_S())
        after.setWordWrap(True)
        after.setObjectName("dtMeta")
        v.addWidget(after)
        return card

    def _accent(self):
        from ..context import CTX
        return CTX.pal()["accent"]

    def _accent_soft(self):
        from ..context import CTX
        return CTX.pal()["accent_soft"]

    def _copy(self):
        from PySide6.QtWidgets import QApplication
        text = self.out_edit.result_text()
        if not text:
            self.statusMsg.emit("没有可复制的结果")
            return
        QApplication.clipboard().setText(text)
        self.statusMsg.emit(f"已复制结果（{len(text):,} 字符）")

    def _save_report(self):
        sr_text = []
        sr_text.append(f"DevToolkit 智能解码链路报告")
        sr_text.append(f"输入：{len(self.in_edit.toPlainText()):,} 字符")
        for step in self._last_steps() or []:
            sr_text.append(f"{step.index}. {step.action} —— {step.detail}")
            sr_text.append(f"   {step.before_size} → {step.after_size}")
            sr_text.append(f"   结果预览：{step.after_preview}")
        sr_text.append(f"最终结果：\n{self.out_edit.result_text()}")
        path, _ = QFileDialog.getSaveFileName(self, "保存链路报告", "devtoolkit-smart-report.txt", "文本文件 (*.txt);;所有文件 (*.*)")
        if not path:
            return
        try:
            Path(path).write_text("\n".join(sr_text), encoding="utf-8")
            self.statusMsg.emit(f"链路报告已保存：{Path(path).name}")
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", f"无法写入文件：{exc}")

    def _last_steps(self):
        if not self.chain_card.isVisible():
            return []
        steps = []
        for i in range(self.chain_v.count()):
            w = self.chain_v.itemAt(i).widget()
            if w is not None and w.property("dtStep") is not None:
                steps.append(w.property("dtStep"))
        return steps

    def on_theme_changed(self, theme: str):
        from ..widgets import recolor_icons
        recolor_icons(self)
        # 重绘步骤徽标颜色
        for i in range(self.chain_v.count()):
            w = self.chain_v.itemAt(i).widget()
            if w is not None and w.property("dtStep") is not None:
                step = w.property("dtStep")
                num = w.findChild(QLabel)
                if num is not None:
                    num.setStyleSheet(
                        f"border-radius:12px; background: {self._accent_soft()}; color: {self._accent()}; font-weight:600;"
                    )


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def MONO_FONT_S():
    from ..widgets import MONO_FONT
    return MONO_FONT
