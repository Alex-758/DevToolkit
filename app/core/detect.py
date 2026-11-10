"""自动识别编码：根据字符特征给出「候选结果」，并附判断依据与解码预览。

注意：识别是启发式的，只提供候选与置信度，不保证 100% 准确。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .results import Result

# 解码预览时最多展示的字符数
PREVIEW_LIMIT = 64


@dataclass
class Candidate:
    codec_id: str          # 对应 encoders.ENCODERS 的 id
    name: str
    confidence: str        # high / medium / low
    basis: str             # 判断依据（中文）
    preview: str = ""      # 尝试解码后的预览（可能为空）


def _clip_preview(s: str) -> str:
    s = s.replace("\r", "").replace("\n", "⏎")
    if len(s) > PREVIEW_LIMIT:
        return s[:PREVIEW_LIMIT] + "…"
    return s


def _try_preview(codec_id: str, text: str) -> str:
    """用对应编解码器尝试解码，返回预览文本；失败返回空串。"""
    from . import encoders
    result = encoders.decode(codec_id, text, {"charset": "utf-8"})
    if result.ok and isinstance(result.data, str):
        decoded = result.data
        # 只显示「看起来有意义」的结果：无控制字符噪声
        if decoded and _printable_ratio(decoded) > 0.85:
            return _clip_preview(decoded)
    return ""


def _printable_ratio(s: str) -> float:
    if not s:
        return 0.0
    printable = sum(1 for ch in s if ch.isprintable() or ch in "\n\t")
    return printable / len(s)


def detect(text: str) -> Result:
    """识别输入可能的编码，返回候选列表。"""
    if text is None or not text.strip():
        return Result.failure("请先输入要识别的内容")
    s = text.strip()
    compact = re.sub(r"\s+", "", s)
    candidates: List[Candidate] = []

    # --- Hex ---
    if re.match(r"^[0-9a-fA-F]{8,}$", compact) and len(compact) % 2 == 0:
        candidates.append(Candidate(
            codec_id="hex", name="Hex / Base16", confidence="high",
            basis=f"仅含 0–9 A–F 且长度为偶数（{len(compact)} 位 = {len(compact) // 2} 字节）",
            preview=_try_preview("hex", compact),
        ))

    # --- Base64 / Base64URL ---
    if re.match(r"^[A-Za-z0-9+/]{8,}={0,2}$", s) and len(compact) % 4 == 0:
        extra = "（含 + / 标准字母表特征）" if ("/" in s or "+" in s) else ""
        candidates.append(Candidate(
            codec_id="base64", name="Base64", confidence="high",
            basis=f"字母表匹配且长度为 4 的倍数{extra}，含 '=' 填充" if "=" in s
                  else f"字母表匹配且长度为 4 的倍数{extra}",
            preview=_try_preview("base64", s),
        ))
    if re.match(r"^[A-Za-z0-9\-_]{8,}={0,2}$", s) and ("-" in s or "_" in s) and ("/" not in s and "+" not in s):
        candidates.append(Candidate(
            codec_id="base64url", name="Base64 URL Safe", confidence="medium",
            basis="检测到 - _ 字符（URL Safe 字母表特征），且不含标准字母表的 + /",
            preview=_try_preview("base64url", s),
        ))

    # --- Base32 ---
    if re.match(r"^[A-Z2-7]+={0,6}$", s) and len(s) % 8 == 0 and len(s) >= 8:
        candidates.append(Candidate(
            codec_id="base32", name="Base32", confidence="medium",
            basis="仅含 A–Z 2–7 且长度为 8 的倍数（RFC 4648 特征）",
            preview=_try_preview("base32", s),
        ))

    # --- Base58 ---
    if re.match(r"^[1-9A-HJ-NP-Za-km-z]{8,}$", s):
        candidates.append(Candidate(
            codec_id="base58", name="Base58", confidence="low",
            basis="不含 0 O I l 的高密度字母数字串（Base58 字母表特征），与 Base62 难以区分",
            preview=_try_preview("base58", s),
        ))

    # --- Base62 ---
    if re.match(r"^[0-9A-Za-z]{8,}$", s):
        candidates.append(Candidate(
            codec_id="base62", name="Base62", confidence="low",
            basis="纯字母数字串（与 Base58 / Base64 相似度较高，需人工确认）",
            preview=_try_preview("base62", s),
        ))

    # --- URL 编码 ---
    if re.search(r"%[0-9A-Fa-f]{2}", s):
        candidates.append(Candidate(
            codec_id="url", name="URL 编码", confidence="high",
            basis="检测到 %XX 百分号序列" + ("（含 + 代替空格特征）" if "+" in s and "%20" not in s else ""),
            preview=_try_preview("url", s),
        ))

    # --- Unicode 转义 ---
    if re.search(r"\\u[0-9a-fA-F]{4}", s):
        candidates.append(Candidate(
            codec_id="unicode", name="Unicode 转义", confidence="high",
            basis="检测到 \\uXXXX 转义序列",
            preview=_try_preview("unicode", s),
        ))

    # --- HTML 实体 ---
    if re.search(r"&(#[0-9]{2,}|#[xX][0-9a-fA-F]{2,}|[a-zA-Z]{2,8});", s):
        candidates.append(Candidate(
            codec_id="html", name="HTML 实体", confidence="high",
            basis="检测到 &…; 实体结构（命名 / 十进制 / 十六进制）",
            preview=_try_preview("html", s),
        ))

    # --- Quoted-Printable ---
    if re.search(r"=[0-9A-F]{2}", s) and ("=" in s and not re.search(r"\\u[0-9a-fA-F]{4}", s)):
        candidates.append(Candidate(
            codec_id="qp", name="Quoted-Printable", confidence="low",
            basis="检测到 =XX 十六进制转义序列（与 URL 编码特征相似，需人工确认）",
            preview=_try_preview("qp", s),
        ))

    # --- ROT13（永远只是候选，无法可靠识别） ---
    if re.search(r"[A-Za-z]", s):
        candidates.append(Candidate(
            codec_id="rot13", name="ROT13", confidence="low",
            basis="仅作候选：ROT13 无法通过特征可靠识别，若结果出现可读英文即可能命中",
        ))

    if not candidates:
        return Result.success([], note="未检测到常见编码特征，输入可能已是明文或不支持的格式")
    # 置信度排序
    order = {"high": 0, "medium": 1, "low": 2}
    candidates.sort(key=lambda c: order.get(c.confidence, 3))
    return Result.success(candidates, count=len(candidates))
