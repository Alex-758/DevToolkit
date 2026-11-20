"""编码 / 解码算法层。

所有编解码器遵循统一接口：
    encode(text, params) -> Result[str]        文本 → 编码文本
    decode(text, params) -> Result[str]        编码文本 → 文本
    decode_bytes(codec_id, text, params) -> Result[bytes]
                （仅字节型编解码器支持，供智能解码链路使用）

- 文本一律按所选字符集（默认 UTF-8）转字节，全面支持中文等 Unicode 字符。
- 字节型编解码器的 decode 结果若不是有效文本，会返回明确错误；
  需要原始字节时请用 decode_bytes。
- 对无效输入返回明确的中文错误信息，绝不抛出未处理异常。
- 空输入的编码与解码都返回空字符串（数学上自洽）；UI 层负责空输入引导。
"""

from __future__ import annotations

import base64 as _base64
import binascii
import html as _html
import quopri
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .results import Result

MAX_INPUT_CHARS = 8_000_000  # 文本输入上限 8 MB，超大内容请走文件处理

# Base58 / Base62 的编解码是纯 Python 大数运算，耗时随输入长度平方增长：
# 实测 decode 32K 字符 ≈ 0.8s、128K ≈ 6.5s、8MB ≈ 小时级（等同卡死）；
# encode 更陡（64K ≈ 10.7s）。其用例（地址 / 短 ID / token）远小于此上限。
B58_B62_MAX_CHARS = 32_000

BYTE_CODECS = ("base64", "base64url", "base32", "hex", "base58", "base62", "qp")


@dataclass
class Codec:
    id: str
    name: str                     # 下拉框显示名
    hint: str                     # 参数区下方的说明文字
    encode: Callable[[str, dict], Result]
    decode: Callable[[str, dict], Result]
    params_schema: List[Tuple[str, str, List[Tuple[str, str]]]] = field(default_factory=list)
    # params_schema: (参数键, 显示标签, [(取值, 显示名), ...])


ENCODERS: Dict[str, Codec] = {}


def register(codec: Codec) -> None:
    ENCODERS[codec.id] = codec


def get_codec(codec_id: str) -> Optional[Codec]:
    return ENCODERS.get(codec_id)


# ---------------------------------------------------------------------------
# 通用辅助
# ---------------------------------------------------------------------------

def _check_input(text: str) -> Optional[Result]:
    if text is None:
        return Result.failure("输入为空：请输入待处理内容")
    if len(text) > MAX_INPUT_CHARS:
        return Result.failure(
            f"输入过大（{len(text):,} 字符，超过 8 MB 上限）",
            "超大内容请使用「文件处理」页，以字节方式处理。",
        )
    return None


def _to_bytes(text: str, charset: str) -> bytes:
    """按字符集编码为字节，charset 由 UI 提供，均为内置合法值。"""
    try:
        return text.encode(charset)
    except (UnicodeEncodeError, LookupError):
        raise ValueError(f"文本无法按 {charset} 字符集编码（包含该字符集不支持的字符）")


def _from_bytes(data: bytes, charset: str) -> str:
    try:
        return data.decode(charset)
    except UnicodeDecodeError:
        raise ValueError(f"解码结果不是有效的 {charset} 文本（输入可能不是文本数据或字符集选错）")


def _strip_ws(s: str) -> str:
    return re.sub(r"\s+", "", s)


# ---------------------------------------------------------------------------
# 字节级解码核心（供 str 解码与智能解码链路共用）
# ---------------------------------------------------------------------------

def _b64_bytes(compact: str, urlsafe: bool) -> bytes:
    pattern = re.compile(r"^[A-Za-z0-9\-_]+={0,2}$" if urlsafe else r"^[A-Za-z0-9+/]+={0,2}$")
    label = "Base64 URL Safe" if urlsafe else "Base64"
    allowed = "A–Z a–z 0–9 - _" if urlsafe else "A–Z a–z 0–9 + /"
    if not pattern.match(compact):
        bad = next((ch for ch in compact if not (
            ch.isascii() and ch.isalnum() or ch in "+/=-_"
        )), "?")
        raise ValueError(f"输入包含非 {label} 字符（「{bad}」）。允许字符：{allowed}，以及填充符 =")
    if len(compact) % 4 == 1:
        raise ValueError(f"{label} 长度不合法：去掉填充后长度不能是 4n+1")
    padding = "=" * (-len(compact) % 4)
    # URL Safe 变体：先还原为标准字母表再解码（b64decode 不认识 - _，
    # 且 validate=False 会把它们静默丢弃导致数据损坏）
    payload = compact.replace("-", "+").replace("_", "/") if urlsafe else compact
    try:
        return _base64.b64decode(payload + padding, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{label} 解码失败：{exc}")


def _b32_bytes(compact: str) -> bytes:
    if not re.match(r"^[A-Z2-7]+={0,6}$", compact):
        raise ValueError(
            "输入包含非 Base32 字符。Base32（RFC 4648）字母表为 A–Z 2–7，= 作为填充"
        )
    try:
        return _base64.b32decode(compact, casefold=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"Base32 解码失败：{exc}")


def _hex_bytes(compact: str) -> bytes:
    compact = re.sub(r"0x", "", compact, flags=re.IGNORECASE)
    compact = compact.replace(":", "").replace(",", "")
    if not re.match(r"^[0-9a-fA-F]+$", compact):
        bad = next((ch for ch in compact if ch not in "0123456789abcdefABCDEF"), "?")
        raise ValueError(
            f"输入包含非十六进制字符（「{bad}」）。仅允许 0–9 A–F a–f，可含空白与 0x 前缀"
        )
    if len(compact) % 2:
        raise ValueError("十六进制长度必须为偶数（每字节两位）")
    try:
        return bytes.fromhex(compact)
    except ValueError as exc:
        raise ValueError(f"Hex 解码失败：{exc}")


def _b58_bytes(s: str) -> bytes:
    if len(s) > B58_B62_MAX_CHARS:
        raise ValueError(
            f"输入过大（{len(s):,} 字符）：Base58 解码耗时随长度平方增长，上限 {B58_B62_MAX_CHARS:,} 字符。"
            "长内容请改用 Base64 / Hex"
        )
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    index = {ch: i for i, ch in enumerate(alphabet)}
    num = 0
    for pos, ch in enumerate(s):
        if ch not in index:
            raise ValueError(
                f"输入包含非 Base58 字符（「{ch}」）。Bitcoin 字母表不含 0、O、I、l"
            )
        num = num * 58 + index[ch]
    body = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    zeros = 0
    for ch in s:
        if ch == "1":
            zeros += 1
        else:
            break
    return b"\x00" * zeros + body


def _b62_bytes(s: str) -> bytes:
    if len(s) > B58_B62_MAX_CHARS:
        raise ValueError(
            f"输入过大（{len(s):,} 字符）：Base62 解码耗时随长度平方增长，上限 {B58_B62_MAX_CHARS:,} 字符。"
            "长内容请改用 Base64 / Hex"
        )
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    index = {ch: i for i, ch in enumerate(alphabet)}
    num = 0
    for pos, ch in enumerate(s):
        if ch not in index:
            raise ValueError(
                f"输入包含非 Base62 字符（「{ch}」）。字母表为 0–9 a–z A–Z"
            )
        num = num * 62 + index[ch]
    body = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    zeros = 0
    for ch in s:
        if ch == "0":
            zeros += 1
        else:
            break
    return b"\x00" * zeros + body


def _qp_bytes(s: str) -> bytes:
    try:
        return quopri.decodestring(s.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("QP 解码失败：输入包含非 ASCII 字符")


_BYTE_DECODERS = {
    "base64": lambda c: _b64_bytes(c, urlsafe=False),
    "base64url": lambda c: _b64_bytes(c, urlsafe=True),
    "base32": _b32_bytes,
    "hex": _hex_bytes,
    "base58": _b58_bytes,
    "base62": _b62_bytes,
    "qp": _qp_bytes,
}


def decode_bytes(codec_id: str, text: str, params: Optional[dict] = None) -> Result:
    """字节型编解码器的原始字节解码（智能解码链路使用）。"""
    if codec_id not in BYTE_CODECS:
        return Result.failure(f"{codec_id} 不支持字节级解码")
    guard = _check_input(text)
    if guard:
        return guard
    fn = _BYTE_DECODERS[codec_id]
    if codec_id in ("base64", "base64url", "base32", "hex"):
        compact = _strip_ws(text)
    else:
        compact = text.strip()
    try:
        raw = fn(compact)
    except ValueError as exc:
        return Result.failure(str(exc))
    return Result.success(raw, in_bytes=len(compact), out_bytes=len(raw))


# ---------------------------------------------------------------------------
# Base64 / Base64URL
# ---------------------------------------------------------------------------

def _wrap_lines(s: str, width: int) -> str:
    if width <= 0:
        return s
    return "\n".join(s[i: i + width] for i in range(0, len(s), width))


def _b64_encode(text: str, params: dict, urlsafe: bool) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    charset = params.get("charset", "utf-8")
    try:
        raw = _to_bytes(text, charset)
        if urlsafe:
            encoded = _base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        else:
            encoded = _base64.b64encode(raw).decode("ascii")
        wrap = int(params.get("wrap", 0) or 0)
        return Result.success(
            _wrap_lines(encoded, wrap),
            in_bytes=len(raw), out_chars=len(encoded),
            label="Base64 URL Safe" if urlsafe else "Base64（标准）",
        )
    except ValueError as exc:
        return Result.failure(str(exc))


def _b64_decode(text: str, params: dict, urlsafe: bool) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    charset = params.get("charset", "utf-8")
    compact = _strip_ws(text)
    if not compact:
        return Result.success("", in_bytes=0, out_bytes=0)
    try:
        raw = _b64_bytes(compact, urlsafe)
    except ValueError as exc:
        return Result.failure(str(exc), f"len={len(compact)}")
    try:
        label = "Base64 URL Safe" if urlsafe else "Base64（标准）"
        return Result.success(_from_bytes(raw, charset), in_bytes=len(compact), out_bytes=len(raw), label=label)
    except ValueError as exc:
        return Result.failure(str(exc), f"raw_head={raw[:16].hex()}")


register(Codec(
    id="base64", name="Base64（标准）",
    hint="每 3 字节映射为 4 字符；标准字母表 A–Z a–z 0–9 + /，= 作为填充。解码时自动忽略空白并补齐填充。",
    encode=lambda t, p: _b64_encode(t, p, urlsafe=False),
    decode=lambda t, p: _b64_decode(t, p, urlsafe=False),
    params_schema=[
        ("wrap", "每行字符数", [("0", "不换行"), ("76", "76（MIME）"), ("64", "64")]),
        ("charset", "字符集", [("utf-8", "UTF-8（默认）"), ("utf-16le", "UTF-16LE"), ("gbk", "GBK"), ("latin-1", "Latin-1")]),
    ],
))

register(Codec(
    id="base64url", name="Base64 URL Safe",
    hint="使用 - _ 替代 + / 并省略填充，可直接用于 URL 与 JWT。解码时自动补齐填充。",
    encode=lambda t, p: _b64_encode(t, p, urlsafe=True),
    decode=lambda t, p: _b64_decode(t, p, urlsafe=True),
    params_schema=[
        ("charset", "字符集", [("utf-8", "UTF-8（默认）"), ("utf-16le", "UTF-16LE"), ("gbk", "GBK"), ("latin-1", "Latin-1")]),
    ],
))


# ---------------------------------------------------------------------------
# Base32
# ---------------------------------------------------------------------------

def _b32_encode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    charset = params.get("charset", "utf-8")
    try:
        raw = _to_bytes(text, charset)
        encoded = _base64.b32encode(raw).decode("ascii")
        return Result.success(encoded, in_bytes=len(raw), out_chars=len(encoded), label="Base32")
    except ValueError as exc:
        return Result.failure(str(exc))


def _b32_decode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    charset = params.get("charset", "utf-8")
    compact = _strip_ws(text).upper()
    if not compact:
        return Result.success("", in_bytes=0, out_bytes=0)
    try:
        raw = _b32_bytes(compact)
    except ValueError as exc:
        return Result.failure(str(exc), f"len={len(compact)}")
    try:
        return Result.success(_from_bytes(raw, charset), in_bytes=len(compact), out_bytes=len(raw), label="Base32")
    except ValueError as exc:
        return Result.failure(str(exc))


register(Codec(
    id="base32", name="Base32",
    hint="RFC 4648：字母表 A–Z 2–7，= 填充，常用于一次性验证码（TOTP）与 DNS 记录。解码自动忽略空白并补齐大小写。",
    encode=_b32_encode, decode=_b32_decode,
    params_schema=[
        ("charset", "字符集", [("utf-8", "UTF-8（默认）"), ("utf-16le", "UTF-16LE"), ("gbk", "GBK"), ("latin-1", "Latin-1")]),
    ],
))


# ---------------------------------------------------------------------------
# Base16 / Hex
# ---------------------------------------------------------------------------

def _hex_encode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    charset = params.get("charset", "utf-8")
    try:
        raw = _to_bytes(text, charset)
    except ValueError as exc:
        return Result.failure(str(exc))
    sep = " " if params.get("sep") == "space" else ""
    case = params.get("case", "lower")
    body = raw.hex()
    if case == "upper":
        body = body.upper()
    encoded = sep.join(body[i: i + 2] for i in range(0, len(body), 2)) if sep else body
    return Result.success(encoded, in_bytes=len(raw), out_chars=len(encoded), label="Base16 / Hex")


def _hex_decode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    charset = params.get("charset", "utf-8")
    compact = _strip_ws(text)
    if not compact:
        return Result.success("", in_bytes=0, out_bytes=0)
    try:
        raw = _hex_bytes(compact)
    except ValueError as exc:
        return Result.failure(str(exc), f"len={len(compact)}")
    try:
        return Result.success(_from_bytes(raw, charset), in_bytes=len(raw), out_bytes=len(raw), label="Base16 / Hex")
    except ValueError as exc:
        return Result.failure(str(exc))


register(Codec(
    id="hex", name="Base16 / Hex",
    hint="支持大小写、有无空格分隔及 0x 前缀的输入；输出可选大小写与分隔符。",
    encode=_hex_encode, decode=_hex_decode,
    params_schema=[
        ("case", "输出大小写", [("lower", "小写（默认）"), ("upper", "大写")]),
        ("sep", "分隔符", [("none", "无分隔（默认）"), ("space", "空格分隔")]),
        ("charset", "字符集", [("utf-8", "UTF-8（默认）"), ("utf-16le", "UTF-16LE"), ("gbk", "GBK"), ("latin-1", "Latin-1")]),
    ],
))


# ---------------------------------------------------------------------------
# Base58（Bitcoin 字母表）
# ---------------------------------------------------------------------------

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {ch: i for i, ch in enumerate(_B58_ALPHABET)}


def _b58_encode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    if len(text) > B58_B62_MAX_CHARS:
        return Result.failure(
            f"输入过大（{len(text):,} 字符）：Base58 编码耗时随长度平方增长，上限 {B58_B62_MAX_CHARS:,} 字符。"
            "长内容请改用 Base64 / Hex"
        )
    charset = params.get("charset", "utf-8")
    try:
        raw = _to_bytes(text, charset)
    except ValueError as exc:
        return Result.failure(str(exc))
    num = int.from_bytes(raw, "big") if raw else 0
    out = ""
    while num > 0:
        num, rem = divmod(num, 58)
        out = _B58_ALPHABET[rem] + out
    for b in raw:
        if b == 0:
            out = "1" + out
        else:
            break
    return Result.success(out, in_bytes=len(raw), out_chars=len(out), label="Base58")


def _b58_decode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    charset = params.get("charset", "utf-8")
    s = text.strip()
    if not s:
        return Result.success("", in_bytes=0, out_bytes=0)
    try:
        raw = _b58_bytes(s)
    except ValueError as exc:
        return Result.failure(str(exc), f"len={len(s)}")
    try:
        return Result.success(_from_bytes(raw, charset), in_bytes=len(s), out_bytes=len(raw), label="Base58")
    except ValueError as exc:
        return Result.failure(str(exc))


register(Codec(
    id="base58", name="Base58",
    hint="Bitcoin 字母表，去掉易混淆的 0 O I l；常用于加密货币地址与 IPFS CID。",
    encode=_b58_encode, decode=_b58_decode,
    params_schema=[
        ("charset", "字符集", [("utf-8", "UTF-8（默认）"), ("utf-16le", "UTF-16LE"), ("gbk", "GBK"), ("latin-1", "Latin-1")]),
    ],
))


# ---------------------------------------------------------------------------
# Base62
# ---------------------------------------------------------------------------

_B62_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _b62_encode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    if len(text) > B58_B62_MAX_CHARS:
        return Result.failure(
            f"输入过大（{len(text):,} 字符）：Base62 编码耗时随长度平方增长，上限 {B58_B62_MAX_CHARS:,} 字符。"
            "长内容请改用 Base64 / Hex"
        )
    charset = params.get("charset", "utf-8")
    try:
        raw = _to_bytes(text, charset)
    except ValueError as exc:
        return Result.failure(str(exc))
    index = {ch: i for i, ch in enumerate(_B62_ALPHABET)}
    num = int.from_bytes(raw, "big") if raw else 0
    out = ""
    while num > 0:
        num, rem = divmod(num, 62)
        out = _B62_ALPHABET[rem] + out
    for b in raw:
        if b == 0:
            out = "0" + out
        else:
            break
    return Result.success(out, in_bytes=len(raw), out_chars=len(out), label="Base62")


def _b62_decode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    charset = params.get("charset", "utf-8")
    s = text.strip()
    if not s:
        return Result.success("", in_bytes=0, out_bytes=0)
    try:
        raw = _b62_bytes(s)
    except ValueError as exc:
        return Result.failure(str(exc), f"len={len(s)}")
    try:
        return Result.success(_from_bytes(raw, charset), in_bytes=len(s), out_bytes=len(raw), label="Base62")
    except ValueError as exc:
        return Result.failure(str(exc))


register(Codec(
    id="base62", name="Base62",
    hint="字母表 0–9 a–z A–Z，无填充；常用于短链接 ID 与业务编号。",
    encode=_b62_encode, decode=_b62_decode,
    params_schema=[
        ("charset", "字符集", [("utf-8", "UTF-8（默认）"), ("utf-16le", "UTF-16LE"), ("gbk", "GBK"), ("latin-1", "Latin-1")]),
    ],
))


# ---------------------------------------------------------------------------
# URL 编码
# ---------------------------------------------------------------------------

def _url_encode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    mode = params.get("mode", "std")
    safe = "/" if mode == "std" else ""
    encoded = urllib.parse.quote(text, safe=safe)
    if params.get("space", "%20") == "plus":
        encoded = encoded.replace("%20", "+")
    return Result.success(encoded, in_bytes=len(text.encode("utf-8")), out_chars=len(encoded), label="URL 编码")


def _url_decode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    s = text.strip()
    if not s:
        return Result.success("", in_bytes=0, out_bytes=0)
    # 查询串惯例：+ 一律先按空格还原（编码侧如需字面加号会输出 %2B）
    s = s.replace("+", "%20")
    try:
        decoded = urllib.parse.unquote(s, errors="strict")
    except UnicodeDecodeError as exc:
        return Result.failure(
            "URL 解码失败：存在无效的百分号序列或不完整的 UTF-8 编码",
            str(exc),
        )
    return Result.success(decoded, in_bytes=len(s), out_chars=len(decoded), label="URL 编码")


register(Codec(
    id="url", name="URL 编码",
    hint="UTF-8 百分号编码；空格可选 %20 或 +，解码时自动识别两种形式（字面加号请编码为 %2B）。",
    encode=_url_encode, decode=_url_decode,
    params_schema=[
        ("mode", "保留字符", [("std", "标准（保留 / 与 .-~_）"), ("full", "全部编码（含 /）")]),
        ("space", "空格形式", [("%20", "%20（默认）"), ("plus", "+ 号")]),
    ],
))


# ---------------------------------------------------------------------------
# HTML 实体
# ---------------------------------------------------------------------------

def _html_encode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    entity = params.get("entity", "hex")
    if entity == "named":
        encoded = _html.escape(text, quote=True)
    else:
        out = []
        for ch in text:
            if ch in ("&", "<", ">", '"', "'"):
                out.append(_html.escape(ch, quote=True))
            elif ord(ch) > 127:
                out.append(f"&#x{ord(ch):x};" if entity == "hex" else f"&#{ord(ch)};")
            else:
                out.append(ch)
        encoded = "".join(out)
    return Result.success(encoded, in_bytes=len(text.encode("utf-8")), out_chars=len(encoded), label="HTML 实体")


def _html_decode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    s = text.strip()
    if not s:
        return Result.success("", in_bytes=0, out_bytes=0)
    decoded = _html.unescape(s)
    return Result.success(decoded, in_bytes=len(s), out_chars=len(decoded), label="HTML 实体")


register(Codec(
    id="html", name="HTML 实体",
    hint="编码 & < > \" ' 及非 ASCII 字符；解码支持命名（&amp;）、十进制（&#20320;）与十六进制（&#x4f60;）实体。",
    encode=_html_encode, decode=_html_decode,
    params_schema=[
        ("entity", "非 ASCII 实体形式", [("hex", "十六进制（&#x4f60;）"), ("dec", "十进制（&#20320;）"), ("named", "仅编码 5 个保留字符")]),
    ],
))


# ---------------------------------------------------------------------------
# Unicode 转义（\uXXXX）
# ---------------------------------------------------------------------------

_UNI_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")
_UNI_BAD_RE = re.compile(r"\\u(?![0-9a-fA-F]{4})")


def _uni_encode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    upper = params.get("case", "lower") == "upper"
    out = []
    for ch in text:
        cp = ord(ch)
        if 0xD800 <= cp <= 0xDFFF:
            return Result.failure("输入包含孤立代理字符，无法进行 Unicode 转义编码")
        if cp > 0xFFFF:
            # 超出 BMP：按 UTF-16 代理对编码（与 JSON / Java 语义一致）
            v = cp - 0x10000
            hi, lo = 0xD800 + (v >> 10), 0xDC00 + (v & 0x3FF)
            hs = f"{hi:04x}"; ls = f"{lo:04x}"
            if upper:
                hs, ls = hs.upper(), ls.upper()
            out.append("\\u" + hs + "\\u" + ls)
        elif cp > 127:
            hs = f"{cp:04x}"
            out.append("\\u" + (hs.upper() if upper else hs))
        else:
            out.append(ch)
    encoded = "".join(out)
    return Result.success(encoded, in_bytes=len(text.encode("utf-8")), out_chars=len(encoded), label="Unicode 转义")


def _uni_decode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    s = text
    if not s.strip():
        return Result.success("", in_bytes=0, out_bytes=0)
    bad = _UNI_BAD_RE.search(s)
    if bad:
        return Result.failure(
            "Unicode 解码失败：存在无效的 \\u 序列（\\u 后必须跟 4 位十六进制）",
            f"pos={bad.start()}",
        )
    # 单遍重组：按匹配顺序消费，代理对（高代理 + 低代理）合并为一个码点
    pieces = []
    last = 0
    matches = list(_UNI_ESCAPE_RE.finditer(s))
    i = 0
    while i < len(matches):
        m = matches[i]
        u = int(m.group(1), 16)
        merged = False
        if 0xD800 <= u <= 0xDBFF and i + 1 < len(matches):
            u2 = int(matches[i + 1].group(1), 16)
            if 0xDC00 <= u2 <= 0xDFFF:
                cp = 0x10000 + ((u - 0xD800) << 10) + (u2 - 0xDC00)
                pieces.append(s[last:m.start()])
                pieces.append(chr(cp))
                last = matches[i + 1].end()
                merged = True
                i += 2
        if not merged:
            if 0xD800 <= u <= 0xDFFF:
                return Result.failure(
                    "Unicode 解码失败：检测到孤立代理对（\\uD800–\\uDFFF 必须成对出现）"
                )
            pieces.append(s[last:m.start()])
            pieces.append(chr(u))
            last = m.end()
            i += 1
    pieces.append(s[last:])
    decoded = "".join(pieces)
    return Result.success(decoded, in_bytes=len(s), out_chars=len(decoded), label="Unicode 转义")


register(Codec(
    id="unicode", name="Unicode 转义",
    hint="\\uXXXX 格式；自动处理代理对（emoji 等超出 BMP 的字符以 \\uD83D\\uDE00 形式转换）。",
    encode=_uni_encode, decode=_uni_decode,
    params_schema=[
        ("case", "字母大小写", [("lower", "小写（默认）"), ("upper", "大写")]),
    ],
))


# ---------------------------------------------------------------------------
# ASCII
# ---------------------------------------------------------------------------

def _ascii_encode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    radix = params.get("radix", "dec")
    out = []
    for idx, ch in enumerate(text):
        cp = ord(ch)
        if cp > 127:
            return Result.failure(
                f"第 {idx + 1} 个字符「{ch}」超出 ASCII 范围（0–127）。中文字符请改用 Hex 或 Base64"
            )
        if radix == "hex":
            out.append("0x%02X" % cp)
        else:
            out.append(str(cp))
    encoded = " ".join(out)
    return Result.success(encoded, in_bytes=len(text), out_chars=len(encoded), label="ASCII")


def _ascii_decode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    s = text.strip()
    if not s:
        return Result.success("", in_bytes=0, out_bytes=0)
    tokens = [t for t in re.split(r"[\s,]+", s) if t]
    out = []
    for t in tokens:
        # 严格词法校验（R5 B10）：int() 的宽松解析会接受 "1_0"（下划线
        # 分隔符）、全角 / 阿拉伯-印度数字、"＋1"，产出意外的控制字符
        if t[:2].lower() == "0x":
            body = t[2:]
            if not body or not re.fullmatch(r"[0-9a-fA-F]+", body):
                return Result.failure(f"「{t}」不是有效的十六进制码点数值")
            v = int(body, 16)
        elif re.fullmatch(r"[0-9]+", t):
            v = int(t, 10)
        else:
            return Result.failure(f"「{t}」不是有效的十进制 / 十六进制码点数值")
        if not 0 <= v <= 127:
            return Result.failure(f"「{t}」超出 ASCII 范围（0–127）")
        out.append(chr(v))
    decoded = "".join(out)
    return Result.success(decoded, in_bytes=len(s), out_chars=len(decoded), label="ASCII")


register(Codec(
    id="ascii", name="ASCII",
    hint="字符与码点互转（十进制或 0x 十六进制）；仅支持 0–127，中文等字符会明确报错。",
    encode=_ascii_encode, decode=_ascii_decode,
    params_schema=[
        ("radix", "码点形式", [("dec", "十进制（默认）"), ("hex", "十六进制（0x41）")]),
    ],
))


# ---------------------------------------------------------------------------
# ROT13
# ---------------------------------------------------------------------------

def _rot13(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    out = []
    for ch in text:
        cp = ord(ch)
        if 65 <= cp <= 90:
            out.append(chr((cp - 65 + 13) % 26 + 65))
        elif 97 <= cp <= 122:
            out.append(chr((cp - 97 + 13) % 26 + 97))
        else:
            out.append(ch)
    encoded = "".join(out)
    return Result.success(
        encoded, in_bytes=len(text.encode("utf-8")), out_chars=len(encoded),
        label="ROT13", symmetric=True,
    )


register(Codec(
    id="rot13", name="ROT13",
    hint="仅作用于 A–Z a–z 26 个字母，其余字符（含中文）保持不变；ROT13 的编码即解码。",
    encode=_rot13, decode=_rot13,
    params_schema=[],
))


# ---------------------------------------------------------------------------
# Quoted-Printable
# ---------------------------------------------------------------------------

def _qp_encode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    charset = params.get("charset", "utf-8")
    try:
        raw = _to_bytes(text, charset)
    except ValueError as exc:
        return Result.failure(str(exc))
    encoded = quopri.encodestring(raw, quotetabs=False).decode("ascii")
    return Result.success(encoded, in_bytes=len(raw), out_chars=len(encoded), label="Quoted-Printable")


def _qp_decode(text: str, params: dict) -> Result:
    guard = _check_input(text)
    if guard:
        return guard
    s = text.strip()
    if not s:
        return Result.success("", in_bytes=0, out_bytes=0)
    charset = params.get("charset", "utf-8")
    try:
        raw = _qp_bytes(s)
    except ValueError as exc:
        return Result.failure(str(exc))
    try:
        return Result.success(_from_bytes(raw, charset), in_bytes=len(s), out_bytes=len(raw), label="Quoted-Printable")
    except ValueError as exc:
        return Result.failure(str(exc))


register(Codec(
    id="qp", name="Quoted-Printable",
    hint="RFC 2045 =XX 十六进制转义，常用于邮件 MIME 正文；= 换行（软换行）解码时自动还原。",
    encode=_qp_encode, decode=_qp_decode,
    params_schema=[
        ("charset", "字符集", [("utf-8", "UTF-8（默认）"), ("utf-16le", "UTF-16LE"), ("gbk", "GBK"), ("latin-1", "Latin-1")]),
    ],
))


# ---------------------------------------------------------------------------
# 汇总入口
# ---------------------------------------------------------------------------

CODEC_ORDER = [
    "base64", "base64url", "base32", "hex", "base58", "base62",
    "url", "html", "unicode", "ascii", "rot13", "qp",
]


def run(codec_id: str, direction: str, text: str, params: Optional[dict] = None) -> Result:
    """统一入口：direction 为 'encode' 或 'decode'。"""
    codec = get_codec(codec_id)
    if codec is None:
        return Result.failure(f"未知算法：{codec_id}")
    if direction not in ("encode", "decode"):
        return Result.failure(f"未知方向：{direction}")
    params = params or {}
    try:
        if direction == "encode":
            return codec.encode(text, params)
        return codec.decode(text, params)
    except Exception as exc:  # 兜底：任何算法层异常都不应导致程序崩溃
        return Result.failure(f"处理失败：{exc.__class__.__name__}: {exc}")


def encode(codec_id: str, text: str, params: Optional[dict] = None) -> Result:
    return run(codec_id, "encode", text, params)


def decode(codec_id: str, text: str, params: Optional[dict] = None) -> Result:
    return run(codec_id, "decode", text, params)
