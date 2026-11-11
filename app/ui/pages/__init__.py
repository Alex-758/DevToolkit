"""pages 子包：每个功能页一个模块。"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class PageBase(QWidget):
    """功能页基类：统一状态栏消息与历史记录信号。"""

    statusMsg = Signal(str)                 # 底部状态栏消息
    historyAdd = Signal(str, str, str)      # (页面, 操作, 脱敏摘要)
    themeChanged = Signal(str)              # 页面内触发主题相关刷新（极少用）

    def on_show(self) -> None:
        """页面被切换到前台时调用（用于刷新历史列表等）。"""

    def on_theme_changed(self, theme: str) -> None:
        """主题切换时刷新本页图标颜色。"""

    def shutdown_workers(self) -> None:
        """窗口关闭时取消本页所有后台任务。"""
        for attr in ("runner", "worker_runner", "hash_runner", "smart_runner", "file_runner", "rsa_runner"):
            runner = getattr(self, attr, None)
            if runner is not None:
                runner.shutdown()
