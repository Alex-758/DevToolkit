"""主题系统：GPT / Codex 风格的极简配色，深色默认、浅色可切换。

所有颜色集中在 PALETTES，QSS 由模板生成；切换主题 = 重新设置应用样式表。
"""

from __future__ import annotations

from typing import Dict

PALETTES: Dict[str, Dict[str, str]] = {
    "dark": {
        "bg": "#212121",
        "side": "#171717",
        "card": "#2f2f2f",
        "field": "#2f2f2f",
        "hover": "rgba(255,255,255,0.06)",
        "border": "rgba(255,255,255,0.08)",
        "border_strong": "rgba(255,255,255,0.16)",
        "fg": "#ececec",
        "fg2": "#b4b4b4",
        "fg3": "#8f8f8f",
        "accent": "#10a37f",
        "accent_hover": "#0d8f70",
        "accent_fg": "#ffffff",
        "accent_soft": "rgba(16,163,127,0.18)",
        "warn": "#e0a960",
        "warn_soft": "rgba(224,169,96,0.14)",
        "err": "#ef6a6a",
        "err_soft": "rgba(239,106,106,0.14)",
        "menu": "#2f2f2f",
        "shadow": "rgba(0,0,0,0.4)",
        "nav_checked": "#2f2f2f",
    },
    "light": {
        "bg": "#ffffff",
        "side": "#f9f9f9",
        "card": "#ffffff",
        "field": "#f4f4f4",
        "hover": "rgba(0,0,0,0.05)",
        "border": "rgba(0,0,0,0.09)",
        "border_strong": "rgba(0,0,0,0.18)",
        "fg": "#0d0d0d",
        "fg2": "#5d5d5d",
        "fg3": "#8f8f8f",
        "accent": "#0e9f77",
        "accent_hover": "#0c8f6c",
        "accent_fg": "#ffffff",
        "accent_soft": "rgba(16,163,127,0.12)",
        "warn": "#a97208",
        "warn_soft": "rgba(169,114,8,0.10)",
        "err": "#d5484f",
        "err_soft": "rgba(213,72,79,0.10)",
        "menu": "#ffffff",
        "shadow": "rgba(0,0,0,0.10)",
        "nav_checked": "#ececec",
    },
}


def palette(theme: str) -> Dict[str, str]:
    return PALETTES.get(theme, PALETTES["dark"])


QSS_TEMPLATE = """
* {{
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
    color: {fg};
    selection-background-color: {accent_soft};
    selection-color: {fg};
}}
QWidget {{ background: transparent; }}
/* 注意：主窗口规则必须放在 QWidget 透明规则之后（同为类选择器，后者覆盖前者） */
QMainWindow, QDialog {{ background: {bg}; }}
QFrame#dtSide {{ background: {side}; border-right: 1px solid {border}; }}

/* ---------- 卡片与布局 ---------- */
QFrame[dtCard="true"] {{
    background: {card};
    border: 1px solid {border};
    border-radius: 10px;
}}
QLabel#dtTitle {{ font-size: 17px; font-weight: 600; }}
QLabel#dtSub {{ color: {fg3}; font-size: 12px; }}
QLabel#dtCardTitle {{ font-weight: 600; }}
QLabel#dtMeta {{ color: {fg3}; font-size: 11px; }}
QLabel#dtHint {{ color: {fg3}; font-size: 11.5px; }}
QLabel#dtDrop {{
    border: 1.5px dashed {border_strong};
    border-radius: 10px;
    color: {fg3};
    padding: 26px;
}}
QLabel#dtDrop:hover {{ border-color: {accent}; color: {fg2}; }}

/* ---------- 状态芯片 ---------- */
QLabel[dtChip="true"] {{
    border-radius: 9px;
    padding: 2px 9px;
    font-size: 11px;
    background: {hover};
    color: {fg2};
}}
QLabel[dtChip="true"][kind="ok"] {{ background: {accent_soft}; color: {accent}; }}
QLabel[dtChip="true"][kind="warn"] {{ background: {warn_soft}; color: {warn}; }}
QLabel[dtChip="true"][kind="err"] {{ background: {err_soft}; color: {err}; }}
QLabel[dtChip="true"][kind="info"] {{ background: {accent_soft}; color: {accent}; }}
QLabel[dtChip="true"][kind="accent"] {{ background: {accent_soft}; color: {accent}; }}

/* ---------- 横幅 ---------- */
QLabel[dtBanner="true"] {{
    border-radius: 8px;
    padding: 9px 12px;
    font-size: 12px;
}}
QLabel[dtBanner="true"][kind="ok"] {{ background: {accent_soft}; color: {accent}; }}
QLabel[dtBanner="true"][kind="warn"] {{ background: {warn_soft}; color: {warn}; }}
QLabel[dtBanner="true"][kind="err"] {{ background: {err_soft}; color: {err}; }}
QLabel[dtBanner="true"][kind="info"] {{ background: {accent_soft}; color: {accent}; }}

/* ---------- 按钮 ---------- */
QPushButton {{
    background: transparent;
    border: 1px solid {border_strong};
    border-radius: 8px;
    padding: 4px 12px;
    min-height: 22px;
}}
QPushButton:hover {{ background: {hover}; }}
QPushButton:pressed {{ background: {border}; }}
QPushButton:disabled {{ color: {fg3}; border-color: {border}; }}
QPushButton[variant="primary"] {{
    background: {accent};
    border: 1px solid {accent};
    color: {accent_fg};
    font-weight: 600;
    padding: 5px 18px;
}}
QPushButton[variant="primary"]:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QPushButton[variant="primary"]:pressed {{ background: {accent_hover}; }}
QPushButton[variant="ghost"] {{ border: 1px solid transparent; color: {fg2}; }}
QPushButton[variant="ghost"]:hover {{ background: {hover}; color: {fg}; }}
QPushButton[variant="danger"] {{ color: {err}; }}
QPushButton[variant="danger"]:hover {{ background: {err_soft}; }}
QToolButton {{ background: transparent; border: none; border-radius: 7px; padding: 5px; }}
QToolButton:hover {{ background: {hover}; }}

/* ---------- 侧边导航 ---------- */
QPushButton#dtNav {{
    border: none;
    border-radius: 8px;
    padding: 7px 12px;
    text-align: left;
    color: {fg2};
    font-size: 13px;
    min-height: 22px;
}}
QPushButton#dtNav:hover {{ background: {hover}; color: {fg}; }}
QPushButton#dtNav:checked {{ background: {nav_checked}; color: {fg}; font-weight: 600; }}
QLabel#dtSideTitle {{ color: {fg3}; font-size: 11px; letter-spacing: 1px; }}

/* ---------- 输入控件 ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{
    background: {field};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 4px 9px;
}}
QPlainTextEdit {{ padding: 8px 10px; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus {{
    border-color: {accent};
}}
/* 自绘上下按钮：不定制会露出 Windows 原生 ▲▼，与应用风格割裂 */
QSpinBox::up-button, QSpinBox::down-button {{
    subcontrol-origin: border;
    width: 20px;
    border: none;
    background: transparent;
}}
QSpinBox::up-button {{ subcontrol-position: top right; }}
QSpinBox::down-button {{ subcontrol-position: bottom right; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {hover}; }}
QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{ background: {border}; }}
QSpinBox::up-arrow {{
    image: url("{arrow_up}");
    width: 12px;
    height: 8px;
}}
QSpinBox::down-arrow {{
    image: url("{arrow_down}");
    width: 12px;
    height: 8px;
}}
QLineEdit:disabled, QPlainTextEdit:disabled {{ color: {fg3}; }}
QLineEdit[mono="true"], QPlainTextEdit[mono="true"] {{
    font-family: Consolas, "Cascadia Mono", "Courier New", monospace;
    font-size: 12.5px;
}}

/* ---------- 下拉框 ---------- */
QComboBox {{
    background: {field};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 4px 26px 4px 10px;
    min-height: 22px;
}}
QComboBox:hover {{ border-color: {border_strong}; }}
QComboBox:focus {{ border-color: {accent}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{
    /* Qt QSS 不支持 CSS border 三角技巧（border 画成矩形块），
    箭头必须用主题色 PNG（见 _arrow_image） */
    image: url("{arrow_down}");
    width: 12px;
    height: 8px;
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: {menu};
    border: 1px solid {border_strong};
    border-radius: 8px;
    padding: 4px;
    color: {fg};
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    min-height: 26px;
    border-radius: 6px;
    padding: 2px 8px;
}}
QComboBox QAbstractItemView::item:selected {{ background: {hover}; color: {fg}; }}
QComboBox:disabled {{ color: {fg3}; }}

/* ---------- 分段按钮（编码/解码方向） ---------- */
QPushButton#dtSeg {{
    border: none;
    border-radius: 7px;
    padding: 4px 16px;
    color: {fg2};
    min-height: 20px;
}}
QPushButton#dtSeg:checked {{
    background: {accent};
    color: {accent_fg};
    font-weight: 600;
}}
QFrame#dtSegFrame {{
    background: {field};
    border: 1px solid {border};
    border-radius: 9px;
}}

/* ---------- 复选框 / 单选 ---------- */
QCheckBox, QRadioButton {{ spacing: 7px; color: {fg2}; }}
QCheckBox:hover, QRadioButton:hover {{ color: {fg}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QCheckBox::indicator {{
    border: 1px solid {border_strong};
    border-radius: 4px;
    background: {field};
}}
QCheckBox::indicator:checked {{
    background: {accent};
    border-color: {accent};
    image: url(:/qt-project.org/styles/commonstyle/images/standardbutton-apply-16.png);
}}
QRadioButton::indicator {{
    border: 1px solid {border_strong};
    border-radius: 8px;
    background: {field};
}}
QRadioButton::indicator:checked {{
    background: {accent};
    border-color: {accent};
}}

/* ---------- 滑块与进度 ---------- */
QSlider::groove:horizontal {{ height: 4px; background: {hover}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 14px; height: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: {accent};
}}
QProgressBar {{
    background: {hover};
    border: none;
    border-radius: 4px;
    min-height: 7px;
    max-height: 7px;
    text-align: left;
}}
QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}

/* ---------- 列表 / 表格 ---------- */
QTreeWidget, QListWidget {{
    background: transparent;
    border: none;
    outline: none;
}}
QTreeWidget::item, QListWidget::item {{ min-height: 26px; border-radius: 6px; padding: 1px 4px; }}
QTreeWidget::item:hover, QListWidget::item:hover {{ background: {hover}; }}
QTreeWidget::item:selected, QListWidget::item:selected {{ background: {hover}; color: {fg}; }}
QHeaderView::section {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {border};
    color: {fg3};
    font-size: 11px;
    padding: 4px 6px;
}}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {border_strong};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {fg3}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {border_strong}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; }}

/* ---------- 菜单 / 提示 ---------- */
QMenu {{
    background: {menu};
    border: 1px solid {border_strong};
    border-radius: 8px;
    padding: 5px;
}}
QMenu::item {{ padding: 5px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {hover}; }}
QToolTip {{
    background: {menu};
    color: {fg};
    border: 1px solid {border_strong};
    border-radius: 6px;
    padding: 4px 8px;
}}
QStatusBar {{
    background: {side};
    border-top: 1px solid {border};
    color: {fg3};
    font-size: 11px;
}}
QStatusBar::item {{ border: none; }}
QSplitter::handle {{ background: {border}; width: 1px; }}
"""


# ---------------------------------------------------------------------------
# 主题色箭头图片：Qt QSS 不支持 CSS 的 border 三角技巧（border 会被画成
# 矩形块，实测下拉 / 步进箭头渲染为实心方块），子控件箭头必须用真实
# 图片文件。按主题 fg3 色生成小三角 PNG 缓存在数据目录，随主题换色。
# ---------------------------------------------------------------------------

_arrow_cache: Dict[str, str] = {}


def _arrow_image(theme: str, direction: str) -> str:
    """生成（或复用缓存）主题色小三角箭头 PNG，返回 QSS url 路径。"""
    key = (theme, direction)
    if key in _arrow_cache:
        return _arrow_cache[key]
    color = palette(theme)["fg3"].lstrip("#")
    from ..core.config import get_data_dir
    path = get_data_dir() / "cache" / f"arrow-{direction}-{color}.png"
    if not path.exists():
        try:
            from PySide6.QtCore import QByteArray, QRectF, Qt
            from PySide6.QtGui import QPainter, QPixmap
            from PySide6.QtSvg import QSvgRenderer

            # viewBox 12x8：向下 / 向上的实心小三角
            if direction == "down":
                d = "M1 2 L11 2 L6 7 Z"
            elif direction == "up":
                d = "M1 6 L11 6 L6 1 Z"
            else:
                return ""
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 8">'
                   f'<path d="{d}" fill="#{color}"/></svg>')
            ss = 4
            pm = QPixmap(12 * ss, 8 * ss)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(
                p, QRectF(0, 0, 12 * ss, 8 * ss))
            p.end()
            path.parent.mkdir(parents=True, exist_ok=True)
            if not pm.save(str(path)):
                return ""  # 图片不可用时 QSS 规则降级为无箭头，不影响功能
        except Exception:
            return ""
    result = path.as_posix()
    _arrow_cache[key] = result
    return result


def build_qss(theme: str) -> str:
    args = dict(palette(theme))
    args["arrow_down"] = _arrow_image(theme, "down")
    args["arrow_up"] = _arrow_image(theme, "up")
    return QSS_TEMPLATE.format(**args)
