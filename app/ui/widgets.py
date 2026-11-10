"""通用 UI 组件：卡片、状态芯片、横幅、输入输出区、后台线程 Worker。"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QFont
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
    """管理页面的后台任务：自动取消上一次未完成任务、忽略过期结果。"""

    def __init__(self, on_done, on_progress=None, parent=None):
        super().__init__(parent)
        self._worker = None
        self._generation = 0
        self.on_done = on_done
        self.on_progress = on_progress

    def start(self, fn) -> None:
        self.stop()
        self._generation += 1
        gen = self._generation
        worker = Worker(fn, self)
        worker.progress.connect(self._on_progress)
        worker.done.connect(lambda res: self._on_done(res, gen))
        self._worker = worker
        worker.start()

    def stop(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
        self._generation += 1  # 使在途结果过期

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

    def _on_done(self, res, gen: int) -> None:
        if self._worker is not None:
            self._worker.wait(50)
            self._worker.deleteLater()
            self._worker = None
        if gen != self._generation:
            return  # 过期结果：用户已发起新任务或页面已重置
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
    return lbl


def hline() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background: rgba(128,128,128,0.18); border: none;")
    return line


class IOEditor(QPlainTextEdit):
    """等宽输入 / 输出编辑器。"""

    def __init__(self, readonly: bool = False, parent=None):
        super().__init__(parent)
        self.setProperty("mono", True)
        self.setFont(MONO_FONT)
        self.setReadOnly(readonly)
        self.setPlaceholderText("在此粘贴或输入内容…" if not readonly else "结果将显示在这里")
        self.setAcceptDrops(False)
        self.setTabChangesFocus(True)
        self._full_text = ""

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
