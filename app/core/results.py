"""统一的操作结果对象：所有 core 函数返回 Result，UI 层只做展示，不处理异常细节。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Result:
    """操作结果。

    ok        是否成功
    data      成功时的数据（str / bytes / dict / list 等）
    meta      成功时的附加信息（字节数、耗时、算法标签等）
    error     失败时的用户可读中文错误信息
    error_detail  失败时的技术细节（用于调试，不直接展示给用户）
    """

    ok: bool
    data: Any = None
    meta: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    error_detail: str = ""

    @classmethod
    def success(cls, data: Any, **meta: Any) -> "Result":
        return cls(ok=True, data=data, meta=meta)

    @classmethod
    def failure(cls, error: str, detail: str = "", **meta: Any) -> "Result":
        return cls(ok=False, data=None, meta=meta, error=error, error_detail=detail)
