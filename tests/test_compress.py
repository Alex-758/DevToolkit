"""压缩 / 解压测试：7 种格式往返、魔数识别、压缩炸弹防护、错误路径。"""

import gzip
import zlib

import pytest

from app.core import compress_tools as cp


TEXT_SAMPLES = [
    b"Hello, DevToolkit! compress test",
    "你好，世界，压缩测试，重复重复重复重复重复重复".encode("utf-8"),
    bytes(range(256)) * 10,           # 二进制
    b"a",
]


@pytest.mark.parametrize("fmt", cp.FORMATS)
@pytest.mark.parametrize("data", TEXT_SAMPLES)
def test_roundtrip(fmt, data):
    enc = cp.compress(data, fmt)
    assert enc.ok, f"{fmt} compress failed: {enc.error}"
    dec = cp.decompress(enc.data, fmt)
    assert dec.ok, f"{fmt} decompress failed: {dec.error}"
    assert dec.data == data


def test_compression_actually_reduces():
    data = b"repeated " * 1000
    for fmt in cp.FORMATS:
        enc = cp.compress(data, fmt)
        assert enc.ok
        assert enc.meta["out_bytes"] < len(data) / 5, f"{fmt} 压缩率异常"


def test_sniff_magics():
    assert cp.sniff(gzip.compress(b"x")) == "gzip"
    assert cp.sniff(zlib.compress(b"x")) == "zlib"
    assert cp.sniff(b"PK\x03\x04xxxx") == "zip"
    zstd = cp.compress(b"x" * 100, "zstd")
    assert zstd.ok and cp.sniff(zstd.data) == "zstd"
    lz4 = cp.compress(b"x" * 100, "lz4")
    assert lz4.ok and cp.sniff(lz4.data) == "lz4"
    # deflate 无魔数：sniff 识别不了是正常行为
    dfl = cp.compress(b"xxxx", "deflate")
    assert cp.sniff(dfl.data) is None or cp.sniff(dfl.data) == "zlib"


def test_auto_decompress():
    data = gzip.compress("自动识别 gzip".encode())
    r = cp.decompress(data, None)
    assert r.ok and r.data == "自动识别 gzip".encode() and r.meta["fmt"] == "gzip"


def test_unrecognized_format_friendly_error():
    r = cp.decompress(b"this is not compressed data at all!", None)
    assert not r.ok and "无法识别" in r.error


def test_bomb_guard_gzip():
    """压缩炸弹：50MB 的 0 字节压缩后只有几 KB，1MB 上限应触发终止。"""
    bomb = zlib.compress(b"\x00" * (50 * 1024 * 1024))
    # 用 gzip 信封再测一次
    gz = gzip.compress(b"\x00" * (50 * 1024 * 1024))
    for payload, fmt in ((bomb, "zlib"), (gz, "gzip")):
        r = cp.decompress(payload, fmt, cap_mb=1)
        assert not r.ok and "上限" in r.error


def test_bomb_guard_zstd():
    zstd = cp._load_zstd()
    if zstd is None:
        pytest.skip("zstandard 未安装")
    big = zstd.ZstdCompressor(level=19).compress(b"\x00" * (50 * 1024 * 1024))
    r = cp.decompress(big, "zstd", cap_mb=1)
    assert not r.ok and "上限" in r.error


def test_zip_entry_roundtrip_and_bad_zip():
    enc = cp.compress(b"zip content", "zip")
    assert enc.ok
    dec = cp.decompress(enc.data, "zip")
    assert dec.ok and dec.data == b"zip content"
    r = cp.decompress(b"PK\x03\x04corrupt", "zip")
    assert not r.ok


def test_corrupt_streams_fail_cleanly():
    assert not cp.decompress(b"\x1f\x8b\x08broken", "gzip").ok
    assert not cp.decompress(b"\x78\x9c\x00broken!!", "zlib").ok
    assert not cp.decompress(b"", "gzip").ok


def test_level_validation():
    data = b"level test" * 100
    assert cp.compress(data, "brotli", level=11).ok
    assert cp.compress(data, "zstd", level=22).ok
    assert cp.compress(data, "gzip", level=9).ok


def test_unknown_format():
    assert not cp.compress(b"x", "rar5").ok
    assert not cp.decompress(b"x", "rar5").ok


def test_try_auto_decompress():
    data = zlib.compress(b"fallback zlib")
    r = cp.try_auto_decompress(data)
    assert r.ok and r.data == b"fallback zlib"
    r2 = cp.try_auto_decompress(b"plain text not compressed")
    assert not r2.ok
