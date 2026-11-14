"""设置对话框：主题、智能解码层数、解压上限、历史容量等。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from ..core import config, history
from .context import CTX


class SettingsDialog(QDialog):
    def __init__(self, parent=None, on_theme_change=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(420)
        self.on_theme_change = on_theme_change
        self._orig_theme = str(config.get_setting("theme"))

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 14)
        v.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        # 标签右对齐：标签列被最长标签撑宽，左对齐会让短标签离字段很远，
        # 长短行的「标签→字段」间距不一致；右对齐后所有标签紧贴各自字段
        from PySide6.QtCore import Qt
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("深色（默认）", "dark")
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.setCurrentIndex(0 if self._orig_theme == "dark" else 1)
        self.theme_combo.currentIndexChanged.connect(self._theme_preview)
        form.addRow("界面主题", self.theme_combo)

        self.layers_spin = QSpinBox()
        self.layers_spin.setRange(1, 10)
        self.layers_spin.setValue(int(config.get_setting("max_layers") or 5))
        form.addRow("智能解码最大层数", self.layers_spin)

        self.cap_combo = QComboBox()
        for mb in (64, 128, 256, 512, 1024):
            self.cap_combo.addItem(f"{mb} MB", mb)
        cur = int(config.get_setting("decompress_cap_mb") or 512)
        idx = self.cap_combo.findData(cur)
        self.cap_combo.setCurrentIndex(idx if idx >= 0 else 3)
        form.addRow("解压输出上限（防压缩炸弹）", self.cap_combo)

        self.hist_spin = QSpinBox()
        self.hist_spin.setRange(10, 1000)
        self.hist_spin.setSingleStep(50)
        self.hist_spin.setValue(int(config.get_setting("history_limit") or 200))
        form.addRow("历史记录容量", self.hist_spin)

        self.skip_empty_chk = QCheckBox("跳过空行")
        self.skip_empty_chk.setChecked(bool(config.get_setting("batch_skip_empty")))
        form.addRow("批量处理", self.skip_empty_chk)

        v.addLayout(form)

        clear_btn = QLabel()
        clear_btn.setText('<a href="#" style="color: #ef6a6a;">清空全部历史记录</a>')
        clear_btn.linkActivated.connect(self._clear_history)
        v.addWidget(clear_btn)

        note = QLabel("所有设置与数据均保存在本地 %APPDATA%\\DevToolkit\\，程序完全离线运行。")
        note.setObjectName("dtHint")
        note.setWordWrap(True)
        v.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("确定")
        # 主操作强调：与全应用按钮层级一致（否则确定/取消同权重，且默认英文）
        ok_btn.setProperty("variant", "primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        # 内部布局默认带边距：按钮右缘会缩进于字段列右缘，视觉上不对齐
        buttons.layout().setContentsMargins(0, 0, 0, 0)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)

    def _theme_preview(self, _idx):
        """选择主题时立即预览。"""
        theme_name = self.theme_combo.currentData()
        if self.on_theme_change:
            self.on_theme_change(theme_name)

    def _clear_history(self):
        box = QMessageBox(self)
        box.setWindowTitle("清空历史记录")
        box.setText("确定要清空全部历史记录吗？此操作不可恢复。")
        clear_btn = box.addButton("清空", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is clear_btn:
            history.clear_entries()
            self.status_msg = "历史记录已清空"

    def _save(self):
        settings = {
            "theme": self.theme_combo.currentData(),
            "max_layers": self.layers_spin.value(),
            "decompress_cap_mb": self.cap_combo.currentData(),
            "history_limit": self.hist_spin.value(),
            "batch_skip_empty": self.skip_empty_chk.isChecked(),
        }
        config.save_settings(settings)
        CTX.set_theme(settings["theme"])
        if self.on_theme_change and settings["theme"] != self._orig_theme:
            self.on_theme_change(settings["theme"])
        self.accept()

    def reject(self):
        # 取消时恢复原主题预览
        if self.on_theme_change:
            self.on_theme_change(self._orig_theme)
        super().reject()
