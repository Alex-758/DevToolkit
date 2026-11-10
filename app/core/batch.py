"""批量处理：多行文本逐行独立编码 / 解码 / 哈希。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from .results import Result

MAX_LINES = 20_000


@dataclass
class BatchRow:
    index: int          # 1 起始行号
    ok: bool
    output: str = ""    # 成功时该行结果
    error: str = ""     # 失败时该行错误信息


def process_lines(
    text: str,
    fn: Callable[[str], Result],
    skip_empty: bool = True,
    keep_index: bool = True,
) -> Result:
    """对多行文本逐行调用 fn，每行独立处理。

    - skip_empty=True 时跳过空行（输出行与输入行一一对应）。
    - keep_index=True 时保留行号（便于输出为 "行号 结果" 形式）。
    """
    if text is None:
        return Result.failure("输入为空：请提供多行文本")
    lines = text.split("\n")
    lines = [ln.rstrip("\r") for ln in lines]
    if len(lines) > MAX_LINES:
        return Result.failure(f"行数过多（{len(lines):,} 行，上限 {MAX_LINES:,} 行）")
    rows: List[BatchRow] = []
    for idx, line in enumerate(lines, start=1):
        if skip_empty and line.strip() == "":
            continue
        result = fn(line)
        if result.ok:
            out = str(result.data)
            rows.append(BatchRow(index=idx if keep_index else 0, ok=True, output=out))
        else:
            rows.append(BatchRow(index=idx if keep_index else 0, ok=False, error=result.error or "处理失败"))
    return Result.success(rows, total=len(rows), failed=sum(1 for r in rows if not r.ok))


def format_rows(rows: List[BatchRow], with_index: bool = True, with_errors: bool = True) -> str:
    """把批量结果格式化为多行文本。"""
    out = []
    for row in rows:
        if row.ok:
            out.append(f"{row.index}  {row.output}" if with_index else row.output)
        elif with_errors:
            out.append(f"{row.index}  ✕ {row.error}")
    return "\n".join(out)


def batch_encode(codec_id: str, direction: str, text: str, params: Optional[dict] = None) -> Result:
    """批量编码 / 解码便捷入口。"""
    from . import encoders
    return process_lines(text, lambda ln: encoders.run(codec_id, direction, ln, params))


def batch_hash(text: str, algo: str) -> Result:
    """批量哈希：每行独立计算。"""
    from . import hashing
    return process_lines(text, lambda ln: hashing.text_hash(ln, algo))
