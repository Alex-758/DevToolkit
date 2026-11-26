"""哈希、自动识别、智能解码测试。"""

import base64
import gzip
import zlib

from app.core import detect, hashing, smart_decode


# ---------------------------------------------------------------------------
# 哈希
# ---------------------------------------------------------------------------

def test_known_vectors():
    assert hashing.text_hash("abc", "sha256").data == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert hashing.text_hash("", "md5").data == "d41d8cd98f00b204e9800998ecf8427e"
    assert hashing.text_hash("Hello", "sha1").data == (
        "f7ff9e8b7bb2e09b70935a5d785e0cc5d9d0abf0"
    )


def test_hash_all_consistency():
    text = "你好，世界"
    allr = hashing.text_hash_all(text)
    assert allr.ok and len(allr.data) == len(hashing.ALGO_IDS)
    single = hashing.text_hash(text, "sha3_256")
    assert single.data == allr.data["sha3_256"]


def test_blake2_lengths():
    assert len(hashing.text_hash("x", "blake2b").data) == 128
    assert len(hashing.text_hash("x", "blake2s").data) == 64


def test_file_hash_matches_text_hash(tmp_path):
    p = tmp_path / "sample.txt"
    content = "文件哈希测试 file hash 你好".encode("utf-8")
    p.write_bytes(content)
    r = hashing.file_hash(str(p), ["sha256", "md5"])
    assert r.ok and r.meta["in_bytes"] == len(content)
    assert r.data["sha256"] == hashing.text_hash(content.decode(), "sha256").data
    # 进度回调
    calls = []
    r2 = hashing.file_hash(str(p), ["sha256"], progress=lambda d, t: calls.append((d, t)))
    assert r2.ok and calls and calls[-1][0] == len(content)


def test_file_hash_missing_file():
    assert not hashing.file_hash("Z:/no/such/file.bin").ok


def test_compare():
    r = hashing.compare("ABC123", "abc123")
    assert r.ok and r.data is True
    r = hashing.compare("ABC123", "ABC124")
    assert r.ok and r.data is False
    r = hashing.compare("", "abc")
    assert not r.ok
    # 含空格的粘贴值
    r = hashing.compare("ab cd 12", "ABCD12")
    assert r.ok and r.data is True
    assert hashing.compare("ab\tcd\n12", "ABCD12").data is True


def test_smart_invalid_layer_count_returns_failure():
    from app.core import smart_decode
    for value in ("bad", None, float("inf")):
        r = smart_decode.smart_decode("SGVsbG8=", value)
        assert not r.ok and "层数" in r.error


def test_unknown_algo():
    assert not hashing.text_hash("x", "md6").ok


# ---------------------------------------------------------------------------
# 自动识别
# ---------------------------------------------------------------------------

def test_detect_base64():
    text = base64.b64encode("Hello, World".encode()).decode()
    r = detect.detect(text)
    assert r.ok and r.data
    top = r.data[0]
    assert top.codec_id == "base64" and top.confidence == "high"
    assert top.preview == "Hello, World"


def test_detect_hex():
    r = detect.detect("48656c6c6f")
    assert r.ok and any(c.codec_id == "hex" for c in r.data)


def test_detect_url():
    r = detect.detect("hello%20%E4%BD%A0%E5%A5%BD")
    assert r.ok and r.data[0].codec_id == "url"
    assert "你好" in r.data[0].preview


def test_detect_unicode_and_html():
    r = detect.detect("Hello \\u4f60\\u597d")
    assert r.ok and r.data[0].codec_id == "unicode"
    r2 = detect.detect("&#20320;&#22909;")
    assert r2.ok and r2.data[0].codec_id == "html"


def test_detect_plain_text_no_false_positive():
    r = detect.detect("这是一段普通中文文本 plain text")
    assert r.ok
    ids = [c.codec_id for c in r.data]
    # 普通文本不应高置信命中
    assert all(c.confidence != "high" for c in r.data)


def test_detect_empty():
    assert not detect.detect("   ").ok


def test_detect_rot13_always_candidate():
    r = detect.detect("Hello World abc")
    assert r.ok and any(c.codec_id == "rot13" for c in r.data)


# ---------------------------------------------------------------------------
# 智能解码
# ---------------------------------------------------------------------------

def test_smart_single_layer_base64():
    payload = base64.b64encode("Hello 智能解码".encode()).decode()
    r = smart_decode.smart_decode(payload)
    assert r.ok
    sr = r.data
    assert sr.final_text == "Hello 智能解码"
    assert sr.layers_used == 1 and sr.steps[0].action == "Base64 解码"
    assert "Base64" in sr.chain


def test_smart_base64_gzip_utf8_chain():
    inner = "原始字符串 → GZIP → Base64 智能链路 你好"
    compressed = gzip.compress(inner.encode("utf-8"), 6)
    payload = base64.b64encode(compressed).decode()
    r = smart_decode.smart_decode(payload)
    assert r.ok
    sr = r.data
    assert sr.final_text == inner
    actions = [s.action for s in sr.steps]
    assert any("Base64" in a for a in actions)
    assert any("GZIP" in a for a in actions)
    assert sr.layers_used == 2


def test_smart_zlib_chain():
    inner = "zlib chain 你好"
    payload = base64.b64encode(zlib.compress(inner.encode())).decode()
    r = smart_decode.smart_decode(payload)
    assert r.ok and r.data.final_text == inner


def test_smart_plain_text_untouched():
    text = "这就是普通文本 plain text"
    r = smart_decode.smart_decode(text)
    assert r.ok
    assert r.data.final_text == text
    assert r.data.layers_used == 0


def test_smart_url_layer():
    payload = "%E4%BD%A0%E5%A5%BD%20world"
    r = smart_decode.smart_decode(payload)
    assert r.ok and r.data.final_text == "你好 world"


def test_smart_respects_layer_cap():
    """嵌套 Base64：限制 1 层时只解 1 层；放宽层数后完全还原。"""
    inner = "深层数据 deep"
    nested = base64.b64encode(base64.b64encode(inner.encode())).decode()
    r = smart_decode.smart_decode(nested, max_layers=1)
    assert r.ok
    assert r.data.layers_used <= 1
    r2 = smart_decode.smart_decode(nested, max_layers=5)
    assert r2.ok and r2.data.final_text == inner


def test_smart_garbage_stays_original():
    garbage = "完全无法识别的内容 ∑∑∑ ?? ###"
    r = smart_decode.smart_decode(garbage)
    assert r.ok and r.data.final_text == garbage


def test_smart_invalid_base64_falls_back():
    # 看似 Base64 实际解码后是无效 UTF-8：应保留原文不崩溃
    payload = base64.b64encode(b"\xff\xfe\x00binary").decode()
    r = smart_decode.smart_decode(payload)
    assert r.ok  # 不崩溃


def test_smart_never_touches_rot13():
    """ROT13 不应出现在自动链路中（会破坏文本）。"""
    r = smart_decode.smart_decode("Uryyb Jbeyq")
    assert r.ok
    assert all("ROT13" not in s.action for s in r.data.steps)


def test_smart_empty():
    assert not smart_decode.smart_decode("   ").ok


def test_smart_layer_limit_enforced():
    # 连续 12 层 Base64（"x" 一直编码下去会循环，改用长文本避免退化）
    text = "深层测试 layer limit" .encode()
    payload = text
    for _ in range(12):
        payload = base64.b64encode(payload)
    payload_str = payload.decode()
    r = smart_decode.smart_decode(payload_str, max_layers=10)
    assert r.ok
    assert r.data.layers_used <= 10


# ---------------------------------------------------------------------------
# R5 回归修复：孤立代理字符友好失败（B4）/ 链路内炸弹如实上报（B13）
# ---------------------------------------------------------------------------

def test_text_hash_lone_surrogate_friendly_failure():
    r = hashing.text_hash("\ud800", "sha256")
    assert not r.ok and "编码" in r.error


def test_text_hash_all_lone_surrogate_friendly_failure():
    r = hashing.text_hash_all("\ud800")
    assert not r.ok and r.error


def test_batch_hash_surrogate_row_fails_not_crashes():
    from app.core import batch
    r = batch.batch_hash("\ud800", "sha256")
    assert r.ok and r.meta["failed"] == 1 and r.data[0].error


def test_smart_decode_bomb_in_chain_reports_bomb():
    """B13：链路中触发压缩炸弹防护时如实上报，不与「未识别特征」混淆。"""
    bomb = zlib.compress(b"\x00" * (64 * 1024 * 1024), 9)
    text = base64.b64encode(bomb).decode()
    r = smart_decode.smart_decode(text, 5, 16)
    assert not r.ok and "上限" in r.error
