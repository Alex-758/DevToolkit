"""应用级上下文：当前主题与配色（页面内需要动态取色时使用）。"""

from __future__ import annotations

from . import theme


class _Ctx:
    def __init__(self):
        self.theme = "dark"
        self._pal = theme.palette("dark")

    def set_theme(self, name: str) -> None:
        self.theme = name if name in theme.PALETTES else "dark"
        self._pal = theme.palette(self.theme)

    def pal(self) -> dict:
        return self._pal


CTX = _Ctx()
