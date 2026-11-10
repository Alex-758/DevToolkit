"""智能多层解码：自动尝试「编码 + 压缩」的组合链路，逐层展示处理过程。

安全与可靠性设计：
- 最大层数限制（默认 5，可配 1–10），防止无限递归。
- 解压输出上限复用 compress_tools 的压缩炸弹防护。
- 已处理过的内容不再重复处理（防止循环）。
- 解码失败 / 无可识别特征时保留原始输入。
- ROT13 不参与自动链路（会对文本造成不可控变形）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import compress_tools
from .results import Result

MAX_INPUT_CHARS = 4_000_000
MAX_LAYERS = 10
DEFAULT_LAYERS = 5
PREVIEW_LIMIT = 96


@dataclass
class Step:
    index: int
    action: str          # 如 "Base64 解码" / "GZIP 解压"
    detail: str          # 判断依据 / 备注
    before_preview: str
    after_preview: str
    before_size: str
    after_size: str


@dataclass
class SmartResult:
    final_text: str
    steps: List[Step] = field(default_factory=list)
    chain: str = "（未做任何处理）"
    layers_used: int = 0


COMPRESS_NAMES = {
    "gzip": "GZIP", "zlib": "ZLIB", "deflate": "DEFLATE", "zip": "ZIP",
    "zstd": "Zstandard", "lz4": "LZ4", "brotli": "Brotli",
}


def _preview(data) -> str:
    """生成单步结果的人类可读预览。"""
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8")
            if _printable_ratio(text) > 0.8:
                return _clip(text)
        except UnicodeDecodeError:
            pass
        head = data[:16].hex().upper()
        spaced = " ".join(head[i: i + 2] for i in range(0, len(head), 2))
        return f"{spaced} …（二进制 {len(data):,} 字节）"
    return _clip(data)


def _clip(s: str) -> str:
    s = s.replace("\r", "").replace("\n", "⏎")
    if len(s) > PREVIEW_LIMIT:
        return s[:PREVIEW_LIMIT] + "…"
    return s


def _printable_ratio(s: str) -> float:
    if not s:
        return 0.0
    return sum(1 for ch in s if ch.isprintable() or ch in "\t") / len(s)


def _try_string_decoders(text: str) -> Optional[Tuple[str, str, object]]:
    """尝试各解码器，返回 (动作名, codec_id, 结果)。

    字节型编解码器返回 bytes（供压缩魔数检测），文本型返回 str。
    严格校验，宁缺毋滥：只对结构特征明显的输入下手。
    """
    from . import encoders

    compact = re.sub(r"\s+", "", text)
    trials = []

    if re.match(r"^[A-Za-z0-9+/]{16,}={0,2}$", compact) and len(compact) % 4 == 0:
        trials.append(("Base64 解码", "base64", True))
    if re.match(r"^[A-Za-z0-9\-_]{16,}={0,2}$", compact) and len(compact) % 4 != 1:
        trials.append(("Base64URL 解码", "base64url", True))
    if re.match(r"^[0-9a-fA-F]{16,}$", compact) and len(compact) % 2 == 0:
        trials.append(("Hex 解码", "hex", True))
    if re.match(r"^[A-Z2-7]+={0,6}$", compact) and len(compact) % 8 == 0 and len(compact) >= 8:
        trials.append(("Base32 解码", "base32", True))
    if re.search(r"%[0-9A-Fa-f]{2}", text):
        trials.append(("URL 解码", "url", False))
    if re.search(r"\\u[0-9a-fA-F]{4}", text):
        trials.append(("Unicode 转义解码", "unicode", False))
    if re.search(r"&(#[0-9]{2,}|#[xX][0-9a-fA-F]{2,}|[a-zA-Z]{2,8});", text):
        trials.append(("HTML 实体解码", "html", False))

    for action, codec_id, byte_mode in trials:
        if byte_mode:
            result = encoders.decode_bytes(codec_id, compact)
            if not result.ok:
                continue
            return (action, codec_id, result.data)
        result = encoders.decode(codec_id, text)
        if not result.ok:
            continue
        decoded = result.data
        if decoded == text:
            continue  # 解码无变化则跳过
        return (action, codec_id, decoded)
    return None


def _try_decompress(data: bytes, cap_mb: int) -> Optional[Tuple[str, bytes]]:
    """若字节含压缩魔数则尝试解压，返回 (动作名, 解压结果 bytes)。"""
    fmt = compress_tools.sniff(data)
    if fmt is None:
        return None
    result = compress_tools.decompress(data, fmt, cap_mb)
    if not result.ok:
        return None
    return (f"{COMPRESS_NAMES.get(fmt, fmt)} 解压", result.data)


def smart_decode(text: str, max_layers: int = DEFAULT_LAYERS, cap_mb: int = 512) -> Result:
    """执行多层解码。返回 Result[SmartResult]。"""
    if text is None or not text.strip():
        return Result.failure("请先输入待解码内容")
    if len(text) > MAX_INPUT_CHARS:
        return Result.failure("输入过大（超过 4 MB），智能解码请使用文件处理页")
    max_layers = max(1, min(int(max_layers), MAX_LAYERS))

    steps: List[Step] = []
    seen = set()
    current: object = text  # str 或 bytes
    chain: List[str] = []
    layers = 0

    while layers < max_layers:
        if isinstance(current, str):
            key = current[:4096]
            if key in seen:
                break
            seen.add(key)
            trial = _try_string_decoders(current)
            if trial is None:
                break
            action, codec_id, decoded = trial
            before = current
            if isinstance(decoded, bytes):
                before_size = f"{len(before):,} 字符"
                after_size = f"{len(decoded):,} 字节"
                comp = _try_decompress(decoded, cap_mb)
                if comp is not None:
                    steps.append(Step(
                        index=len(steps) + 1, action=action,
                        detail="解码为二进制后检测到压缩魔数",
                        before_preview=_preview(before), after_preview=_preview(decoded),
                        before_size=before_size, after_size=after_size,
                    ))
                    chain.append(codec_id)
                    layers += 1
                    current = decoded
                    if layers >= max_layers:
                        break
                    comp_action, comp_data = comp
                    steps.append(Step(
                        index=len(steps) + 1, action=comp_action,
                        detail="压缩魔数命中，解压成功",
                        before_preview=_preview(current), after_preview=_preview(comp_data),
                        before_size=f"{len(current):,} 字节",
                        after_size=f"{len(comp_data):,} 字节",
                    ))
                    chain.append(comp_action.split(" ")[0].lower())
                    layers += 1
                    try:
                        current = comp_data.decode("utf-8")
                    except UnicodeDecodeError:
                        current = comp_data
                    continue
                # 不是压缩数据：尝试按 UTF-8 转为文本
                try:
                    current = decoded.decode("utf-8")
                except UnicodeDecodeError:
                    break  # 无法展示的二进制：终止并保留原文
                steps.append(Step(
                    index=len(steps) + 1, action=action, detail="特征匹配并解码成功",
                    before_preview=_preview(before), after_preview=_preview(current),
                    before_size=before_size,
                    after_size=f"{len(current):,} 字符",
                ))
                chain.append(codec_id)
                layers += 1
            else:
                before_size = f"{len(before):,} 字符"
                steps.append(Step(
                    index=len(steps) + 1, action=action, detail="特征匹配并解码成功",
                    before_preview=_preview(before), after_preview=_preview(decoded),
                    before_size=before_size, after_size=f"{len(decoded):,} 字符",
                ))
                chain.append(codec_id)
                layers += 1
                current = decoded
        else:
            # bytes：尝试解压或转文本
            comp = _try_decompress(current, cap_mb)
            if comp is not None:
                comp_action, comp_data = comp
                steps.append(Step(
                    index=len(steps) + 1, action=comp_action, detail="压缩魔数命中，解压成功",
                    before_preview=_preview(current), after_preview=_preview(comp_data),
                    before_size=f"{len(current):,} 字节", after_size=f"{len(comp_data):,} 字节",
                ))
                chain.append(comp_action.split(" ")[0].lower())
                layers += 1
                try:
                    current = comp_data.decode("utf-8")
                except UnicodeDecodeError:
                    current = comp_data
                continue
            try:
                text_out = current.decode("utf-8")
            except UnicodeDecodeError:
                break
            steps.append(Step(
                index=len(steps) + 1, action="UTF-8 文本确认", detail="二进制数据为有效 UTF-8 文本",
                before_preview=_preview(current), after_preview=_preview(text_out),
                before_size=f"{len(current):,} 字节", after_size=f"{len(text_out):,} 字符",
            ))
            chain.append("utf-8")
            layers += 1
            current = text_out

    # 最终结果整理
    if isinstance(current, bytes):
        try:
            current = current.decode("utf-8")
        except UnicodeDecodeError:
            return Result.failure(
                "解码终止：结果为二进制数据且无法进一步解压或按文本显示。已保留原始输入",
                data_repr=current[:64].hex(),
            )

    chain_names = {
        "base64": "Base64", "base64url": "Base64URL", "hex": "Hex", "base32": "Base32",
        "url": "URL", "unicode": "Unicode", "html": "HTML 实体",
        "gzip": "GZIP", "zlib": "ZLIB", "deflate": "DEFLATE", "zip": "ZIP",
        "zstd": "Zstandard", "lz4": "LZ4", "utf-8": "UTF-8",
    }
    chain_str = " → ".join(chain_names.get(c, c) for c in chain) if chain else "（未做任何处理）"
    if layers >= max_layers and chain:
        note = f"已达最大层数（{max_layers} 层）自动终止"
    elif chain:
        note = "链路自然终止（结果已是可读文本且无进一步特征）"
    else:
        note = "未识别到可解码的编码特征，保留原始输入"
    result = SmartResult(
        final_text=current, steps=steps, chain=chain_str, layers_used=layers,
    )
    return Result.success(result, note=note, layers_used=layers, max_layers=max_layers)
