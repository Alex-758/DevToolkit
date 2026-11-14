"""文件处理页：二进制安全读取，Base64 / Hex / 哈希 / GZIP，后台线程 + 进度 + 保存。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ...core import compress_tools as cp
from ...core import hashing
from ...core.results import Result
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

PAGE_NAME = "文件处理"

OPS = [
    ("base64", "Base64 编码"),
    ("hex", "Hex 编码"),
    ("hash", "SHA-256 校验值"),
    ("gzip", "GZIP 压缩"),
    ("gunzip", "GZIP 解压（自动识别格式）"),
]

MAX_FILE_BYTES = 256 * 1024 * 1024


class FilesPage(PageBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        header = PageHeader(
            PAGE_NAME,
            "二进制安全读取（不强制按 UTF-8 解码）· 超过 10 MB 自动转入后台线程 · 结果可保存为文件",
        )
        root.addWidget(header)

        # ---- 拖放区 ----
        self.drop_lbl = QLabel("拖放文件到此处，或点击选择文件\n\n支持任意格式（.png .pdf .zip …）· 大文件在后台线程处理，界面不卡顿")
        self.drop_lbl.setObjectName("dtDrop")
        self.drop_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.drop_lbl.mousePressEvent = lambda _evt: self._pick_file()
        root.addWidget(self.drop_lbl)

        # ---- 已载入文件 + 操作 ----
        self.file_card = make_card()
        self.file_header = CardHeader("未载入文件", "")
        self.remove_btn = btn("移除", "trash")
        set_btn_icon(self.remove_btn, "trash")
        self.remove_btn.clicked.connect(self._remove_file)
        self.file_header.add_button(self.remove_btn)
        op_h = QHBoxLayout()
        op_h.setContentsMargins(12, 4, 12, 12)
        op_h.setSpacing(10)
        op_lbl = QLabel("处理操作")
        op_lbl.setObjectName("dtMeta")
        self.op_combo = QComboBox()
        for value, text in OPS:
            self.op_combo.addItem(text, value)
        self.run_btn = btn("开始处理", "play", variant="primary")
        set_btn_icon(self.run_btn, "play", "accent_fg")
        self.run_btn.clicked.connect(self._run)
        self.run_btn.setEnabled(False)
        op_h.addWidget(op_lbl)
        op_h.addWidget(self.op_combo)
        op_h.addStretch(1)
        op_h.addWidget(self.run_btn)
        op_wrap = QVBoxLayout()
        op_wrap.setContentsMargins(1, 1, 1, 1)
        op_wrap.addWidget(self.file_header)
        op_wrap.addLayout(op_h)
        self.file_card.setLayout(op_wrap)
        self.file_card.hide()
        root.addWidget(self.file_card)

        # ---- 后台任务进度 ----
        self.prog_card = make_card()
        prog_h = QHBoxLayout(self.prog_card)
        prog_h.setContentsMargins(14, 11, 14, 11)
        self.prog_lbl = QLabel("后台任务")
        self.prog_lbl.setObjectName("dtCardTitle")
        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.cancel_btn = btn("取消", "alert")
        set_btn_icon(self.cancel_btn, "alert")
        self.cancel_btn.clicked.connect(self._cancel)
        prog_h.addWidget(self.prog_lbl)
        prog_h.addWidget(self.prog_bar, 1)
        prog_h.addWidget(self.cancel_btn)
        self.prog_card.hide()
        root.addWidget(self.prog_card)

        # ---- 结果区 ----
        self.out_card, self.out_header, self.out_edit = io_card("处理结果", "", readonly=True, min_lines=5)
        self.copy_btn = btn("复制结果", "copy")
        set_btn_icon(self.copy_btn, "copy")
        self.copy_btn.clicked.connect(self._copy)
        self.save_btn = btn("保存结果", "save")
        set_btn_icon(self.save_btn, "save")
        self.save_btn.clicked.connect(self._save)
        self.out_header.add_button(self.copy_btn)
        self.out_header.add_button(self.save_btn)
        root.addWidget(self.out_card)

        self.note_banner = banner("info", "读取始终按字节处理（二进制安全）；仅当操作需要文本（如哈希展示）时才尝试 UTF-8 解码，失败则显示字节预览。")
        root.addWidget(self.note_banner)
        root.addStretch(1)

        self._file_path = ""
        self._run_path = ""   # 本次任务锁定的文件路径（运行中换文件不影响结果与历史）
        self._binary_out = None
        self.file_runner = WorkerRunner(self._on_done, self._on_progress, self)
        QShortcut(QKeySequence("Ctrl+Return"), self, self._run)

    # ------------------------------------------------------------------
    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", "所有文件 (*.*)")
        if path:
            self._load_file(path)

    def _load_file(self, path: str):
        try:
            size = Path(path).stat().st_size
        except OSError as exc:
            QMessageBox.warning(self, "载入失败", f"无法读取文件：{exc}")
            return
        if size > MAX_FILE_BYTES:
            QMessageBox.warning(self, "文件过大", f"文件超过 256 MB 上限（当前 {size / 1024 / 1024:.1f} MB）")
            return
        self._file_path = path
        self.file_card.show()
        self.file_header.title_lbl.setText(Path(path).name)
        self.file_header.set_meta(f"{size:,} 字节（{size / 1024:.1f} KB）")
        # 有任务在跑时保持禁用：按钮由任务完成回调统一恢复
        self.run_btn.setEnabled(not self.file_runner.busy())
        self.out_edit.set_result_text("")
        self._binary_out = None
        set_chip(self.out_header.chip_lbl, "", "")
        self.statusMsg.emit(f"已载入 {Path(path).name}（{size:,} 字节）")

    def _remove_file(self):
        self._file_path = ""
        self.file_card.hide()
        self.run_btn.setEnabled(False)
        self.statusMsg.emit("已移除文件")

    # ------------------------------------------------------------------
    def _run(self):
        if not self._file_path:
            self.statusMsg.emit("请先选择文件")
            return
        if self.file_runner.busy():
            # Ctrl+Return 快捷键不经过按钮禁用态；任务运行中不允许再起任务
            self.statusMsg.emit("已有任务正在处理，请等待完成或点击「取消」")
            return
        op = self.op_combo.currentData()
        self._run_path = self._file_path  # 锁定路径：运行中载入新文件不影响本任务
        self.run_btn.setEnabled(False)
        self.prog_card.show()
        self.prog_bar.setValue(0)
        self.prog_lbl.setText(f"正在处理：{Path(self._run_path).name}（后台线程，界面不卡顿）")

        def job(worker):
            return self._do_process(op, worker, self._run_path)

        self.file_runner.start(job)

    def _do_process(self, op: str, worker, path: str):
        import time as _time

        t0 = _time.perf_counter()
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            return Result.failure(
                f"读取文件失败：{exc.strerror or exc}")
        if op == "base64":
            import base64 as _b64
            out = _b64.b64encode(data)
            return Result.success(
                {"kind": "text", "text": out.decode("ascii"), "meta": f"Base64 编码 · {len(data):,} B → {len(out):,} 字符",
                 "binary": None, "ms": elapsed_ms(t0)},
            )
        if op == "hex":
            out = data.hex()
            return Result.success(
                {"kind": "text", "text": out, "meta": f"Hex 编码 · {len(data):,} B → {len(out):,} 字符",
                 "binary": None, "ms": elapsed_ms(t0)},
            )
        if op == "hash":
            r = hashing.file_hash(path, ["sha256", "md5", "sha1"], progress=lambda d, t: worker.report(d, t),
                                  cancel_check=worker.is_cancelled)
            if not r.ok:
                return r
            lines = [f"{hashing.algo_display(a)}: {v}" for a, v in r.data.items()]
            return Result.success(
                {"kind": "text", "text": "\n".join(lines),
                 "meta": f"文件哈希 · {Path(path).name} · {r.meta['in_bytes']:,} 字节",
                 "binary": None, "ms": elapsed_ms(t0)},
            )
        if op == "gzip":
            import gzip as _gzip
            import io as _io
            # 分块写入以支持进度上报与取消（gzip.compress 一次性完成，大文件期间进度条静止）
            buf = _io.BytesIO()
            total = len(data)
            step = 4 * 1024 * 1024
            with _gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as gz:
                for i in range(0, total, step):
                    if worker.is_cancelled():
                        return Result.failure("已取消")
                    gz.write(data[i:i + step])
                    worker.report(min(i + step, total), total)
            out = buf.getvalue()
            return Result.success(
                {"kind": "binary", "text": "", "meta": f"GZIP 压缩 · {len(data):,} B → {len(out):,} B",
                 "binary": out, "out_name": Path(path).name + ".gz", "ms": elapsed_ms(t0)},
            )
        if op == "gunzip":
            r = cp.decompress(data, None)
            if not r.ok:
                return r
            try:
                text = r.data.decode("utf-8")
                return Result.success(
                    {"kind": "text", "text": text,
                     "meta": f"解压成功（{cp.FORMAT_NAMES[r.meta['fmt']]}）· {len(data):,} B → {len(r.data):,} 字符（UTF-8 文本）",
                     "binary": None, "ms": elapsed_ms(t0)},
                )
            except UnicodeDecodeError:
                return Result.success(
                    {"kind": "binary", "text": "", "meta": f"解压成功（{cp.FORMAT_NAMES[r.meta['fmt']]}）· {len(r.data):,} 字节二进制",
                     "binary": r.data, "out_name": Path(path).name + ".out", "ms": elapsed_ms(t0)},
                )
        return Result.failure(f"未知操作：{op}")

    def _on_progress(self, done: int, total: int):
        pct = int(done * 100 / total) if total else 0
        self.prog_bar.setValue(pct)

    def _on_done(self, result):
        self.run_btn.setEnabled(True)
        self.prog_card.hide()
        if not result.ok:
            if "已取消" in result.error:
                self.statusMsg.emit("任务已取消")
                return
            set_chip(self.out_header.chip_lbl, f"✕ {result.error}", "err")
            self.statusMsg.emit(f"处理失败：{result.error}")
            return
        payload = result.data
        self._binary_out = payload.get("binary")
        if payload["kind"] == "text":
            self.out_edit.set_result_text(payload["text"])
            self._binary_out = None
        else:
            self.out_edit.setPlainText(
                f"[二进制结果 {len(payload['binary']):,} 字节]\n请点击「保存结果」导出文件"
                + (f"（建议文件名：{payload.get('out_name', 'output.bin')}）" if payload.get("out_name") else "")
            )
            self.out_edit._full_text = ""
        set_chip(self.out_header.chip_lbl, f"✓ {payload['meta']} · {payload['ms']} 毫秒", "ok")
        self.historyAdd.emit(PAGE_NAME, payload["meta"], Path(self._run_path).name if self._run_path else "")
        self.statusMsg.emit(f"处理完成 · {payload['ms']} 毫秒")

    def _cancel(self):
        self.file_runner.stop()
        self.statusMsg.emit("正在取消后台任务…")

    # ------------------------------------------------------------------
    def _copy(self):
        from PySide6.QtWidgets import QApplication
        if self._binary_out is not None:
            self.statusMsg.emit("二进制结果请使用「保存结果」导出")
            return
        text = self.out_edit.result_text()
        if not text:
            self.statusMsg.emit("没有可复制的结果")
            return
        QApplication.clipboard().setText(text)
        self.statusMsg.emit(f"已复制完整结果（{len(text):,} 字符）")

    def _save(self):
        if self._binary_out is not None:
            default = "output.bin"
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
        path, _ = QFileDialog.getSaveFileName(self, "保存结果", "devtoolkit-file-output.txt", "文本文件 (*.txt);;所有文件 (*.*)")
        if path:
            try:
                Path(path).write_text(text, encoding="utf-8")
                self.statusMsg.emit(f"结果已保存：{Path(path).name}")
            except OSError as exc:
                QMessageBox.warning(self, "保存失败", f"无法写入文件：{exc}")

    # ------------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self._load_file(urls[0].toLocalFile())
            event.acceptProposedAction()

    def on_theme_changed(self, theme: str):
        from ..widgets import recolor_icons
        recolor_icons(self)
