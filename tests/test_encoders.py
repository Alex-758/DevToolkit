"""编码 / 解码算法测试：往返一致性 + 已知向量 + 错误路径。"""

import pytest

from app.core import encoders


SAMPLES = [
    "Hello, World!",
    "你好，世界",                     # 中文
    "Hello, DevToolkit! 你好，世界",   # 混合
    "emoji: 😀🎉🚀",                  # 超出 BMP（代理对）
    "",                              # 空串（编码应成功，结果为空）
    "a",                             # 单字符（填充边界）
    "ab",                            # 2 字节（填充边界）
    "abc",                           # 3 字节（整块）
    "特殊字符 &<>\"' %20 \\u4f60 日本語 한국어",
]


@pytest.mark.parametrize("codec_id", encoders.CODEC_ORDER)
@pytest.mark.parametrize("text", SAMPLES)
def test_roundtrip(codec_id, text):
    """所有编解码器：encode → decode 必须还原原文。

    两个例外（均为设计行为，不是 Bug）：
    - ASCII 编码器对非 ASCII 输入必须明确报错；
    - 含 \\u 字面量的文本与 Unicode 转义语义天然冲突，无法保证往返还原。
    """
    if codec_id == "ascii" and any(ord(ch) > 127 for ch in text):
        enc = encoders.encode(codec_id, text)
        assert not enc.ok and "超出 ASCII" in enc.error
        return
    if codec_id == "unicode" and "\\u" in text:
        pytest.skip("含 \\u 字面量的文本与转义语义冲突")
    enc = encoders.encode(codec_id, text, {"charset": "utf-8"})
    assert enc.ok, f"{codec_id} encode failed: {enc.error}"
    dec = encoders.decode(codec_id, enc.data, {"charset": "utf-8"})
    assert dec.ok, f"{codec_id} decode failed: {dec.error} (input={enc.data!r})"
    assert dec.data == text, f"{codec_id} roundtrip mismatch"


def test_base64_known_vector():
    assert encoders.encode("base64", "Hello").data == "SGVsbG8="
    assert encoders.decode("base64", "SGVsbG8=").data == "Hello"
    # 中文
    enc = encoders.encode("base64", "你好，世界")
    assert enc.ok and enc.meta["in_bytes"] == 15
    assert encoders.decode("base64", enc.data).data == "你好，世界"


def test_base64_urlsafe_differs_on_special_bytes():
    # 0xFB 0xFF 使标准字母表出现 + /，URL Safe 应为 - _
    raw = "ÿý"
    std = encoders.encode("base64", raw).data
    url = encoders.encode("base64url", raw).data
    assert "/" not in url and "+" not in url
    assert std != url


def test_base64_decode_tolerates_whitespace_and_missing_padding():
    assert encoders.decode("base64", "SGVs bG8=").data == "Hello"
    assert encoders.decode("base64", "SGVsbG8").data == "Hello"


def test_base64_invalid_input():
    r = encoders.decode("base64", "!!!!不是base64!!!!")
    assert not r.ok and "非 Base64 字符" in r.error
    r = encoders.decode("base64", "A")  # 4n+1
    assert not r.ok and "4n+1" in r.error or "长度" in r.error


def test_hex_known_vector():
    enc = encoders.encode("hex", "AB")
    assert enc.data == "4142"
    assert encoders.encode("hex", "AB", {"case": "upper"}).data == "4142"
    assert encoders.decode("hex", "41 42").data == "AB"
    assert encoders.decode("hex", "0x4142").data == "AB"
    assert encoders.decode("hex", "0X4142").data == "AB"
    # 大小写混合
    assert encoders.decode("hex", "4a4B").data == "JK"


def test_hex_invalid():
    assert not encoders.decode("hex", "41g2").ok
    assert not encoders.decode("hex", "414").ok  # 奇数长度
    assert not encoders.decode("hex", "xyz").ok


def test_unicode_escape_surrogate_pair():
    enc = encoders.encode("unicode", "😀")            # U+1F600 → 代理对
    assert enc.data.lower() == "\\ud83d\\ude00"
    dec = encoders.decode("unicode", enc.data)
    assert dec.ok and dec.data == "😀"


def test_unicode_escape_invalid():
    r = encoders.decode("unicode", "\\u12g4")
    assert not r.ok and "无效" in r.error
    r = encoders.decode("unicode", "\\uD83D")        # 孤立高代理
    assert not r.ok and "孤立代理" in r.error


def test_url_encode_variants():
    enc = encoders.encode("url", "a/b c")
    assert enc.data == "a/b%20c"                      # 标准保留 /
    full = encoders.encode("url", "a/b", {"mode": "full"})
    assert "%2F" in full.data
    plus = encoders.encode("url", "a c", {"space": "plus"})
    assert plus.data == "a+c"
    # 解码自动处理 + 与 %20
    assert encoders.decode("url", "a+b").data == "a b"
    assert encoders.decode("url", "a%20b").data == "a b"


def test_url_decode_invalid():
    r = encoders.decode("url", "%E4%BD")             # 不完整 UTF-8
    assert not r.ok and "无效" in r.error


def test_html_entity():
    enc = encoders.encode("html", "<div>你好 &</div>")
    assert "&lt;" in enc.data and "&amp;" in enc.data and "&#x4f60;" in enc.data
    dec = encoders.decode("html", enc.data)
    assert dec.data == "<div>你好 &</div>"
    # 命名实体
    assert encoders.decode("html", "&amp; &lt; &#20320; &#x4f60;").data == "& < 你 你"


def test_ascii_non_ascii_error():
    r = encoders.encode("ascii", "你好")
    assert not r.ok and "超出 ASCII" in r.error
    assert encoders.encode("ascii", "AB").data == "65 66"
    assert encoders.decode("ascii", "65 66").data == "AB"
    assert encoders.decode("ascii", "0x41 0x42").data == "AB"
    r = encoders.decode("ascii", "200")
    assert not r.ok and "超出 ASCII" in r.error


def test_rot13_only_letters():
    assert encoders.encode("rot13", "Hello").data == "Uryyb"
    assert encoders.decode("rot13", "Uryyb").data == "Hello"
    assert encoders.encode("rot13", "你好！").data == "你好！"


def test_base58_rejects_confusable():
    r = encoders.decode("base58", "0OIl")
    assert not r.ok and "Base58" in r.error
    # Bitcoin 地址风格往返
    enc = encoders.encode("base58", "Hello 你好")
    assert encoders.decode("base58", enc.data).data == "Hello 你好"


def test_base62_roundtrip_leading_zero():
    enc = encoders.encode("base62", "\x00\x01")
    assert enc.data.startswith("0")
    assert encoders.decode("base62", enc.data).data == "\x00\x01"


def test_base32_known():
    assert encoders.encode("base32", "Hello").data == "JBSWY3DP"
    assert encoders.decode("base32", "JBSWY3DP").data == "Hello"


def test_qp_roundtrip_and_multiline():
    text = "Hello 你好\nSecond line=1"
    enc = encoders.encode("qp", text)
    assert enc.ok and "=E4=BD=A0" in enc.data
    dec = encoders.decode("qp", enc.data)
    assert dec.ok and dec.data == text


def test_html_and_qp_preserve_boundary_whitespace():
    text = "  lead and trail  "
    for codec_id in ("html", "qp"):
        enc = encoders.encode(codec_id, text)
        dec = encoders.decode(codec_id, enc.data)
        assert enc.ok and dec.ok and dec.data == text


def test_charset_gbk():
    enc = encoders.encode("hex", "中文", {"charset": "gbk"})
    # 中文 in GBK = D6D0 CEC4
    assert enc.data == "d6d0cec4"
    dec = encoders.decode("hex", "d6d0cec4", {"charset": "gbk"})
    assert dec.data == "中文"


def test_empty_decode_returns_empty():
    """空输入的编解码在 core 层是自洽的空变换；UI 层负责空输入引导提示。"""
    for codec_id in encoders.CODEC_ORDER:
        enc = encoders.encode(codec_id, "")
        assert enc.ok, codec_id
        dec = encoders.decode(codec_id, enc.data)
        assert dec.ok and dec.data == "", codec_id


def test_oversized_input():
    big = "a" * (encoders.MAX_INPUT_CHARS + 1)
    r = encoders.encode("base64", big)
    assert not r.ok and "过大" in r.error


def test_run_unknown_codec():
    assert not encoders.run("nope", "encode", "x").ok
    assert not encoders.run("base64", "sideways", "x").ok


def test_run_never_raises_on_any_garbage():
    """兜底测试：任何垃圾输入都不应抛异常，只返回失败 Result。"""
    for codec_id in encoders.CODEC_ORDER:
        for text in ("", " ", "\x00\x01\x02", "∑∑∑", "\ud800x" if False else "🙂", "-" * 100):
            r1 = encoders.run(codec_id, "encode", text)
            r2 = encoders.run(codec_id, "decode", text)
            assert isinstance(r1.ok, bool) and isinstance(r2.ok, bool)


# ---------------------------------------------------------------------------
# Base58 / Base62 长度上限（R2 修复回归：纯 Python 大数解码 O(n²)，
# 实测 8MB 输入小时级卡死；上限 32K 字符并给出明确错误）
# ---------------------------------------------------------------------------

def test_b58_b62_decode_over_limit_fails_fast():
    import time
    for cid in ("base58", "base62"):
        t0 = time.perf_counter()
        r = encoders.run(cid, "decode", "3" * (encoders.B58_B62_MAX_CHARS + 1))
        elapsed = time.perf_counter() - t0
        assert not r.ok and "过大" in r.error
        assert elapsed < 1.0, f"{cid} over-limit decode must fail fast, took {elapsed:.2f}s"


def test_b58_b62_encode_over_limit_fails_fast():
    for cid in ("base58", "base62"):
        r = encoders.run(cid, "encode", "x" * (encoders.B58_B62_MAX_CHARS + 1))
        assert not r.ok and "过大" in r.error


def test_b58_b62_within_limit_still_works():
    """上限内的大输入正常编解码（Base58 输出会膨胀约 1.4 倍，样本需留余量）。"""
    payload = "测试负载 " * 800  # 7200 字符文本，Base58 编码后约 1 万字符，低于上限
    for cid in ("base58", "base62"):
        enc = encoders.run(cid, "encode", payload)
        assert enc.ok, f"{cid}: {enc.error}"
        dec = encoders.run(cid, "decode", enc.data)
        assert dec.ok, f"{cid}: {dec.error}"
        assert dec.data == payload


def test_qp_encode_no_trailing_newline():
    """QP 编码不应给短输入附加多余换行（曾疑似 quopri 尾部换行，实测不存在）。"""
    r = encoders.run("qp", "encode", "hello")
    assert r.ok and r.data == "hello"


# ---------------------------------------------------------------------------
# R5 回归修复：ASCII 解码严格词法校验（B10）
# ---------------------------------------------------------------------------

def test_ascii_decode_strict_tokens():
    """int() 宽松解析曾接受下划线分隔符 / 全角与阿拉伯-印度数字 / 带符号数。"""
    for bad in ("1_0", "١٢٣", "１２３", "+1", "0x", "0xZZ", "ABC"):
        r = encoders.decode("ascii", bad, {})
        assert not r.ok, bad
    for good, expect in (("65", "A"), ("65 66", "AB"), ("0x41", "A"),
                         ("0X41 0x42", "AB"), ("007", "\x07")):
        r = encoders.decode("ascii", good, {})
        assert r.ok and r.data == expect, (good, r.error)
