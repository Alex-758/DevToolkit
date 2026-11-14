"""通用 UI 组件：卡片、状态芯片、横幅、输入输出区、后台线程 Worker。"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core.results import Result

# 超长输出的显示截断阈值（复制 / 保存仍使用完整数据）
DISPLAY_TRUNCATE = 200_000

# 自动换行开关阈值：QPlainTextEdit 的 wrap 布局耗时随单块文本长度平方增长
# （实测 0.5MB ≈ 4.9s、1MB ≈ 20s、8MB 分钟级）；NoWrap 为线性（8MB ≈ 4.5s）。
# 超过阈值自动切为不换行（横向滚动），回落到阈值以内时恢复换行。
WRAP_TOGGLE_CHARS = 64_000

MONO_FONT = QFont("Consolas")
MONO_FONT.setStyleHint(QFont.StyleHint.Monospace)
MONO_FONT.setPointSize(9)


# ---------------------------------------------------------------------------
# 后台线程
# ---------------------------------------------------------------------------

class Worker(QThread):
    """通用后台任务：fn(worker) -> Result；worker.report(d, t) 上报进度。"""

    progress = Signal(int, int)
    done = Signal(object)  # Result

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._cancelled = False
        self.setObjectName("DevToolkitWorker")

    # 供 fn 内部调用 -----------------------------------------------------
    def report(self, done: int, total: int) -> None:
        self.progress.emit(int(done), int(total))

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    # --------------------------------------------------------------------
    def run(self) -> None:  # noqa: D102
        try:
            res = self._fn(self)
        except Exception as exc:  # 兜底：后台任务异常不终止程序
            res = Result.failure(f"后台任务失败：{exc}", repr(exc))
        self.done.emit(res)


class WorkerRunner(QObject):
    """管理页面的后台任务：新任务自动取代旧任务、过期结果不送达回调。

    竞态约束（实测旧实现会崩）：done 信号按 worker 身份配对清理。
    旧任务的 done 若在新任务启动后才送达，绝不能触碰当前正在运行的
    Worker（deleteLater 运行中的 QThread 会触发
    "QThread: Destroyed while thread is still running" 并可能崩溃）。

    语义：stop() 只请求协作取消，其终止结果仍会送达回调（通常为
    「已取消」失败）——页面依赖该回调恢复按钮 / 进度条等 UI 状态。
    只有 start()（发起新任务）才使旧结果过期。
    """

    def __init__(self, on_done, on_progress=None, parent=None):
        super().__init__(parent)
        self._worker = None
        self._generation = 0
        self.on_done = on_done
        self.on_progress = on_progress

    def start(self, fn) -> None:
        self.stop()
        self._generation += 1  # 使被取代任务的在途结果过期
        gen = self._generation
        worker = Worker(fn, self)
        worker.progress.connect(self._on_progress)
        worker.done.connect(lambda res, wk=worker, g=gen: self._on_done(res, wk, g))
        self._worker = worker
        worker.start()

    def stop(self) -> None:
        """请求协作取消当前任务；其终止结果仍会送达回调。"""
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()

    def busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def shutdown(self, wait_ms: int = 3000) -> None:
        """窗口关闭时调用：请求取消并短暂等待。"""
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(wait_ms)

    def _on_progress(self, done: int, total: int) -> None:
        if self.on_progress:
            self.on_progress(done, total)

    def _on_done(self, res, worker, gen: int) -> None:
        # 只回收发出本次信号的 worker；被新任务取代的旧 worker 绝不
        # 触碰当前 _worker（旧实现曾 deleteLater 正在运行的新线程）
        worker.wait(50)
        worker.deleteLater()
        if worker is not self._worker:
            return  # 过期 Worker：当前任务另有其人
        self._worker = None
        if gen != self._generation:
            return  # 过期结果：新任务已发起
        self.on_done(res)


# ---------------------------------------------------------------------------
# 基础部件
# ---------------------------------------------------------------------------

def make_card() -> QFrame:
    card = QFrame()
    card.setProperty("dtCard", True)
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    return card


def chip(text: str = "", kind: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("dtChip", True)
    if kind:
        lbl.setProperty("kind", kind)
    lbl.hide()
    return lbl


def set_chip(lbl: QLabel, text: str, kind: str) -> None:
    """更新芯片文本与颜色；kind 为空则隐藏。"""
    lbl.setText(text)
    lbl.setProperty("kind", kind)
    lbl.style().unpolish(lbl)
    lbl.style().polish(lbl)
    lbl.setVisible(bool(text) and bool(kind))


def banner(kind: str, text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("dtBanner", True)
    lbl.setProperty("kind", kind)
    lbl.setWordWrap(True)
    # 同 PageHeader：wordWrap 标签会参与富余空间分配，横幅高度应贴住内容
    lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    return lbl


def hline() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background: rgba(128,128,128,0.18); border: none;")
    return line


class IOEditor(QPlainTextEdit):
    """等宽输入 / 输出编辑器。

    占位文本自绘而非用 QPlainTextEdit.setPlaceholderText：Qt 原生占位文本
    只检查「文档为空」就绘制，而输入法合成（预编辑）文字不写入文档，
    合成期间会与预编辑文字重叠；QLineEdit 的实现检查了 preedit，无此问题。
    """

    def __init__(self, readonly: bool = False, parent=None):
        super().__init__(parent)
        self.setProperty("mono", True)
        self.setFont(MONO_FONT)
        self.setReadOnly(readonly)
        self.setAcceptDrops(False)
        self.setTabChangesFocus(True)
        self._full_text = ""
        self._placeholder = ""
        self._preedit = ""
        self.set_placeholder("在此粘贴或输入内容…" if not readonly else "结果将显示在这里")
        self.textChanged.connect(self._update_wrap_mode)

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self.update()

    # ------------------------------------------------------------------
    # 大文本换行策略：wrap 布局对超长单块文本是平方级卡顿（分钟级），
    # 超过阈值切为不换行；所有写入路径都要先经过 _preset_wrap 预判，
    # 否则会先在 wrap 模式下卡完全程再切换（失去意义）。
    # ------------------------------------------------------------------
    def _preset_wrap(self, n_chars: int) -> None:
        """按即将写入的长度预设换行模式。

        缩小方向不立即恢复 wrap：若当前文档仍超阈值，切换模式会对旧内容
        触发平方级重排；维持 NoWrap，等 textChanged 在文档更新后收敛。
        """
        if n_chars > WRAP_TOGGLE_CHARS:
            self._set_wrap(QPlainTextEdit.LineWrapMode.NoWrap)
        elif self.document().characterCount() <= WRAP_TOGGLE_CHARS:
            self._set_wrap(QPlainTextEdit.LineWrapMode.WidgetWidth)

    def _set_wrap(self, mode) -> None:
        if mode != self.lineWrapMode():
            self.setLineWrapMode(mode)

    def _update_wrap_mode(self) -> None:
        # characterCount 为 Qt 维护的缓存计数，O(1)
        self._preset_wrap(self.document().characterCount())

    def setPlainText(self, text: str) -> None:
        self._preset_wrap(len(text or ""))
        super().setPlainText(text)

    def insertFromMimeData(self, source) -> None:
        # 粘贴 / 拖放：预先按剪贴板内容长度切换换行模式
        text = source.text() if source is not None else ""
        if text:
            self._preset_wrap(len(text))
        super().insertFromMimeData(source)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._placeholder and self.document().isEmpty() and not self._preedit:
            painter = QPainter(self.viewport())
            painter.setFont(self.font())
            # 用主题 fg3 作占位色：QSS repolish 对 palette PlaceholderText 的
            # 写入时序不确定，主题色是唯一可靠来源
            from .context import CTX
            painter.setPen(QColor(CTX.pal().get("fg3", "#8f8f8f")))
            # 与真实文本同起点：空文档时光标矩形即第一行文本的位置
            cr = self.cursorRect(self.textCursor())
            baseline = cr.y() + QFontMetrics(self.font()).ascent()
            painter.drawText(cr.x(), baseline, self._placeholder)

    def inputMethodEvent(self, event) -> None:
        old = self._preedit
        self._preedit = event.preeditString()
        super().inputMethodEvent(event)
        if old != self._preedit:
            self.update()  # 预编辑开始 / 结束时刷新占位文本显隐

    def focusOutEvent(self, event) -> None:
        if self._preedit:
            self._preedit = ""
            self.update()
        super().focusOutEvent(event)

    def set_result_text(self, text: str) -> None:
        """显示结果：超长时截断显示，完整内容保存在 full_text。"""
        self._full_text = text or ""
        if len(self._full_text) > DISPLAY_TRUNCATE:
            head = self._full_text[:DISPLAY_TRUNCATE]
            self.setPlainText(
                f"{head}\n\n[已截断显示：完整内容共 {len(self._full_text):,} 字符，"
                "复制 / 保存结果仍为完整内容]"
            )
        else:
            self.setPlainText(self._full_text)

    def result_text(self) -> str:
        """完整结果文本（未截断）。"""
        return self._full_text if self._full_text else self.toPlainText()


class PageHeader(QWidget):
    """页面标题行：标题 + 副标题 + 右侧动作区。"""

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        # 垂直方向贴住内容高度：内部 wordWrap 标签会把容器标记为可扩展，
        # 页面富余空间会被按 sizeHint 权重错误分给标题行（如历史页被拉高 3 倍）
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        left = QVBoxLayout()
        left.setSpacing(5)
        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("dtTitle")
        # CJK 回退字体的行高大于拉丁字体的 sizeHint，留足高度防止字形被裁切
        self.title_lbl.setMinimumHeight(30)
        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setObjectName("dtSub")
        self.sub_lbl.setWordWrap(True)
        left.addWidget(self.title_lbl)
        if subtitle:
            left.addWidget(self.sub_lbl)
        layout.addLayout(left, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        layout.addLayout(self.actions)

    def add_action(self, btn: QWidget) -> None:
        self.actions.addWidget(btn)


class CardHeader(QWidget):
    """卡片标题行：标题 + 元信息 + 芯片 + 右侧按钮区。"""

    def __init__(self, title: str, meta: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(10)
        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("dtCardTitle")
        layout.addWidget(self.title_lbl)
        self.meta_lbl = QLabel(meta)
        self.meta_lbl.setObjectName("dtMeta")
        layout.addWidget(self.meta_lbl)
        self.chip_lbl = chip()
        layout.addWidget(self.chip_lbl)
        layout.addStretch(1)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(6)
        layout.addLayout(self.buttons)

    def set_meta(self, text: str) -> None:
        self.meta_lbl.setText(text)
        self.meta_lbl.setVisible(bool(text))

    def add_button(self, btn: QWidget) -> None:
        self.buttons.addWidget(btn)


def io_card(title: str, meta: str = "", readonly: bool = False, min_lines: int = 5) -> tuple:
    """构造「卡片头 + 等宽编辑区」组合，返回 (card, header, editor)。"""
    card = make_card()
    v = QVBoxLayout(card)
    v.setContentsMargins(1, 1, 1, 1)
    v.setSpacing(0)
    header = CardHeader(title, meta)
    v.addWidget(header)
    editor = IOEditor(readonly=readonly)
    editor.setMinimumHeight(22 * min_lines + 16)
    v.addWidget(editor)
    return card, header, editor


def btn(text: str = "", icon_name: str = "", icon_color: str = "#8f8f8f", variant: str = "", parent=None) -> QPushButton:
    b = QPushButton(text, parent)
    if variant:
        b.setProperty("variant", variant)
    if icon_name:
        from . import icons
        b.setIcon(icons.icon(icon_name, icon_color))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def set_btn_icon(btn: QPushButton, name: str, role: str = "fg2", size: int = 15) -> None:
    """给按钮设置主题色图标，并记录 (图标名, 色彩角色) 供主题切换时重着色。"""
    from . import icons
    from .context import CTX
    btn.setProperty("dtIcon", name)
    btn.setProperty("dtRole", role)
    btn.setIcon(icons.icon(name, CTX.pal().get(role, "#8f8f8f"), size))


def recolor_icons(widget: QWidget) -> None:
    """主题切换后按新配色重建所有按钮图标。"""
    from . import icons
    from .context import CTX
    icons.clear_cache()
    pal = CTX.pal()
    for child in widget.findChildren(QPushButton):
        name = child.property("dtIcon")
        if name:
            role = child.property("dtRole") or "fg2"
            child.setIcon(icons.icon(name, pal.get(role, "#8f8f8f")))
    for toolbtn in widget.findChildren(__import__("PySide6.QtWidgets", fromlist=["QToolButton"]).QToolButton):
        name = toolbtn.property("dtIcon")
        if name:
            role = toolbtn.property("dtRole") or "fg2"
            toolbtn.setIcon(icons.icon(name, pal.get(role, "#8f8f8f")))


def elapsed_ms(t0: float) -> int:
    return max(1, int((time.perf_counter() - t0) * 1000))
