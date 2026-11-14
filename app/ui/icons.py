"""内置线性图标：24×24 viewBox 的极简 SVG，按主题色实时渲染为 QIcon。

GPT / Codex 风格：统一 1.7px 圆头描边，无填充，色彩跟随主题。
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer

# 每个图标只含路径/形状，公共属性（描边色、线宽、圆头）由外壳统一提供
_PATHS = {
    "encode": '<path d="M8 6 3 12l5 6M16 6l5 6-5 6"/>',
    "crypto": '<circle cx="8" cy="16" r="3.5"/><path d="M10.5 13.5 20 4M17 7l3 3"/>',
    "compress": '<rect x="3" y="4" width="18" height="5" rx="1.5"/><path d="M5 9v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9M10 13h4"/>',
    "hash": '<path d="M4 9h16M4 15h16M10 4 8 20M16 4l-2 16"/>',
    "smart": '<path d="M12 3.2l1.7 4.6 4.6 1.7-4.6 1.7L12 15.8l-1.7-4.6-4.6-1.7 4.6-1.7zM18.6 15.4l.7 1.9 1.9.7-1.9.7-.7 1.9-.7-1.9-1.9-.7 1.9-.7z"/>',
    "files": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "history": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2.5"/>',
    "about": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5 5l1.8 1.8M17.2 17.2 19 19M19 5l-1.8 1.8M6.8 17.2 5 19"/>',
    "moon": '<path d="M20.5 13.5A8.5 8.5 0 1 1 10.5 3.5a7 7 0 0 0 10 10z"/>',
    "settings": '<path d="M4 7h7M17 7h3M4 12h3M11 12h9M4 17h9M17 17h3"/><circle cx="13.5" cy="7" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="15" cy="17" r="2"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
    "save": '<path d="M12 3v11m0 0 4-4m-4 4-4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
    "paste": '<rect x="5" y="5" width="14" height="16" rx="2"/><path d="M9 5a3 3 0 0 1 6 0M9 11h6M9 15h4"/>',
    "eraser": '<path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13"/>',
    "play": '<path d="M8 5.5v13l11-6.5z"/>',
    "swap": '<path d="M4 8h12M13 4l4 4-4 4M20 16H8m3 4-4-4 4-4"/>',
    "detect": '<path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><circle cx="11" cy="11" r="3"/><path d="M13.5 13.5 16 16"/>',
    "star": '<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1.1 5.8L12 16.8l-5.3 2.8 1.1-5.8L3.5 9.7l5.9-.8z"/>',
    "trash": '<path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13M10 11v6M14 11v6"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5"/>',
    "upload": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M12 16.5v-6M9.5 13 12 10.5 14.5 13"/>',
    "check": '<path d="M5 13l4 4L19 7"/>',
    "shield_ok": '<path d="M12 3l7.5 2.8V12c0 4.6-3.2 7.6-7.5 8.8C7.7 19.6 4.5 16.6 4.5 12V5.8z"/><path d="M9 12l2 2 4-4.5"/>',
    "shield_warn": '<path d="M12 3l7.5 2.8V12c0 4.6-3.2 7.6-7.5 8.8C7.7 19.6 4.5 16.6 4.5 12V5.8z"/><path d="M12 8.5v4M12 15.5h.01"/>',
    "alert": '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4M12 16.8h.01"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v4h-4"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "signature": '<path d="M3 20h18M4 17c3-1 4-9 6.5-9s2.5 5 4 5 2-3 3.5-3"/><path d="M17 4l3 3"/>',
    "dot": '<circle cx="12" cy="12" r="5" fill="COLOR" stroke="none"/>',
}

_cache: dict = {}


def _svg_bytes(name: str, color: str, stroke_width: float = 1.7, filled: bool = False) -> QByteArray:
    path = _PATHS[name]
    if filled:
        path = path.replace('fill="none"', "").replace("/>", ' fill="COLOR" stroke="none"/>')
        path = path.replace("COLOR", color)
    body = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" '
        f'stroke-linejoin="round">{path}</svg>'
    )
    return QByteArray(body.encode("utf-8"))


def pixmap(name: str, color: str, size: int = 16, filled: bool = False, stroke_width: float = 1.7) -> QPixmap:
    """渲染单个图标 QPixmap（2x 超采样保证高分屏清晰）。"""
    key = (name, color, size, filled, stroke_width)
    if key in _cache:
        return _cache[key]
    renderer = QSvgRenderer(_svg_bytes(name, color, stroke_width, filled))
    img = QImage(size * 2, size * 2, QImage.Format.Format_ARGB32)
    img.fill(0)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * 2, size * 2))
    painter.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(2.0)
    _cache[key] = pm
    return pm


def icon(name: str, color: str, size: int = 16, filled: bool = False, stroke_width: float = 1.7) -> QIcon:
    return QIcon(pixmap(name, color, size, filled, stroke_width))


def clear_cache() -> None:
    """主题切换后调用：旧颜色的缓存全部失效。"""
    _cache.clear()


# ---------------------------------------------------------------------------
# 品牌应用图标（与 assets/icon.ico 同源）：黑色圆角方底 + 白色扳手描边。
# 扳手路径来自 Lucide "wrench"（ISC 许可），加粗 2.4 —— 与 EXE 图标一致，
# 窗口 / 任务栏不再用主题图标，深浅色标题栏下都成立。
# ---------------------------------------------------------------------------

_APP_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="#ffffff" stroke-width="2.4" stroke-linecap="round" '
    'stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 '
    '1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91'
    'a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>'
)

_app_icon_cache: dict = {}


def app_icon(size: int = 32) -> QIcon:
    """品牌应用图标（窗口 / 任务栏）。矢量渲染，4x 超采样。"""
    if size in _app_icon_cache:
        return _app_icon_cache[size]
    S = size * 4
    img = QImage(S, S, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    bg = QPainterPath()
    bg.addRoundedRect(QRectF(0, 0, S, S), S * 0.22, S * 0.22)
    p.fillPath(bg, QColor("#0d0d0d"))
    QSvgRenderer(QByteArray(_APP_ICON_SVG.encode("utf-8"))).render(
        p, QRectF(S * 0.19, S * 0.19, S * 0.62, S * 0.62))
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(4.0)
    out = QIcon(pm)
    _app_icon_cache[size] = out
    return out
