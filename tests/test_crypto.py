"""加密 / 解密测试：AES 三种模式与三种密钥长度、ChaCha20、RSA、错误路径。"""

import pytest

from app.core import crypto_tools as ct


DATA_SAMPLES = [
    b"Hello, DevToolkit!",
    "你好，世界，加密测试".encode("utf-8"),
    b"\x00\x01\x02binary\xff",
    "emoji 😀 data".encode("utf-8"),
]


def _cfg(**kw):
    cfg = {
        "algorithm": "aes-gcm", "key_size": 256, "key_source": "passphrase",
        "passphrase": "correct horse battery staple", "pbkdf2_iterations": 60000,
        "output_encoding": "base64",
    }
    cfg.update(kw)
    return cfg


@pytest.mark.parametrize("algo", ["aes-gcm", "aes-cbc", "aes-ecb", "chacha20-poly1305"])
@pytest.mark.parametrize("data", DATA_SAMPLES)
def test_symmetric_roundtrip_passphrase(algo, data):
    cfg = _cfg(algorithm=algo, key_size=256)
    enc = ct.encrypt(data, cfg)
    assert enc.ok, enc.error
    dec = ct.decrypt(enc.data, cfg)
    assert dec.ok, dec.error
    assert dec.data == data


@pytest.mark.parametrize("key_size", [128, 192, 256])
def test_aes_key_sizes(key_size):
    data = "roundtrip".encode()
    cfg = _cfg(key_size=key_size)
    enc = ct.encrypt(data, cfg)
    assert enc.ok and enc.meta["key_size"] == key_size
    assert ct.decrypt(enc.data, cfg).data == data


@pytest.mark.parametrize("algo", ["aes-gcm", "aes-cbc", "chacha20-poly1305"])
def test_raw_key_roundtrip(algo):
    raw = "a" * 64  # hex 32 字节
    data = "raw key test 你好".encode("utf-8")
    cfg = _cfg(algorithm=algo, key_source="raw", raw_key=raw)
    enc = ct.encrypt(data, cfg)
    assert enc.ok, enc.error
    dec = ct.decrypt(enc.data, cfg)
    assert dec.ok and dec.data == data


def test_raw_key_b64_and_prefixed():
    import base64
    raw_b64 = base64.b64encode(b"\x01" * 32).decode()
    data = b"x"
    cfg = _cfg(key_source="raw", raw_key=raw_b64)
    enc = ct.encrypt(data, cfg)
    assert enc.ok
    cfg2 = _cfg(key_source="raw", raw_key="hex:" + "ab" * 32)
    enc2 = ct.encrypt(data, cfg2)
    assert enc2.ok


def test_wrong_passphrase_fails_cleanly():
    data = b"secret"
    enc = ct.encrypt(data, _cfg())
    bad = _cfg(passphrase="wrong")
    dec = ct.decrypt(enc.data, bad)
    assert not dec.ok
    assert "认证" in dec.error or "密钥" in dec.error or "填充" in dec.error


def test_tampered_gcm_ciphertext_fails():
    data = b"tamper me"
    enc = ct.encrypt(data, _cfg())
    tampered = enc.data[:-3] + bytes([enc.data[-3] ^ 0xFF]) + enc.data[-2:]
    dec = ct.decrypt(tampered, _cfg())
    assert not dec.ok and "认证" in dec.error


def test_tampered_cbc_fails_padding():
    data = b"0123456789abcdef"
    enc = ct.encrypt(data, _cfg(algorithm="aes-cbc"))
    tampered = enc.data[:-1] + bytes([enc.data[-1] ^ 1])
    dec = ct.decrypt(tampered, _cfg(algorithm="aes-cbc"))
    assert not dec.ok


def test_ecb_marked_unsafe():
    enc = ct.encrypt(b"x", _cfg(algorithm="aes-ecb"))
    assert enc.ok and enc.meta.get("risk") == "err"
    assert "ECB" in enc.meta.get("warning", "")


def test_cbc_marked_warning():
    enc = ct.encrypt(b"x", _cfg(algorithm="aes-cbc"))
    assert enc.ok and enc.meta.get("risk") == "warn"


def test_gcm_marked_ok():
    enc = ct.encrypt(b"x", _cfg())
    assert enc.ok and enc.meta.get("risk") == "ok"


def test_invalid_raw_key_length():
    cfg = _cfg(key_source="raw", raw_key="aabb")  # 2 字节，不够 32
    enc = ct.encrypt(b"x", cfg)
    assert not enc.ok and "密钥长度不正确" in enc.error


def test_empty_passphrase_fails():
    enc = ct.encrypt(b"x", _cfg(passphrase=""))
    assert not enc.ok and "口令为空" in enc.error


def test_short_or_corrupt_ciphertext():
    assert not ct.decrypt(b"DTK1short", _cfg()).ok
    assert not ct.decrypt(b"", _cfg()).ok
    assert not ct.decrypt(b"garbage-not-envelope" * 4, _cfg()).ok


def test_envelope_has_magic():
    enc = ct.encrypt(b"envelope", _cfg())
    assert enc.data[:4] == b"DTK1"


def test_rsa_keypair_roundtrip():
    pair = ct.generate_keypair(2048)
    assert pair.ok
    pub, priv = pair.data["public_pem"], pair.data["private_pem"]
    data = "rsa test 你好".encode("utf-8")
    enc = ct.rsa_encrypt(pub, data)
    assert enc.ok
    dec = ct.rsa_decrypt(priv, enc.data)
    assert dec.ok and dec.data == data


def test_rsa_oaep_size_limit():
    pair = ct.generate_keypair(2048)
    pub = pair.data["public_pem"]
    too_big = b"A" * 191
    r = ct.rsa_encrypt(pub, too_big)
    assert not r.ok and "过长" in r.error


def test_rsa_sign_verify():
    pair = ct.generate_keypair(2048)
    pub, priv = pair.data["public_pem"], pair.data["private_pem"]
    data = "签名测试 signature".encode()
    sig = ct.rsa_sign(priv, data)
    assert sig.ok
    assert ct.rsa_verify(pub, data, sig.data).data is True
    # 篡改原文 → 验签失败
    assert ct.rsa_verify(pub, data + b"x", sig.data).data is False
    # 错误签名
    assert ct.rsa_verify(pub, data, b"\x00" * 256).data is False


def test_rsa_wrong_key_type_rejected():
    pair = ct.generate_keypair(2048)
    pub, priv = pair.data["public_pem"], pair.data["private_pem"]
    assert not ct.rsa_decrypt(pub, b"\x00" * 256).ok
    r = ct.rsa_encrypt(priv, b"x")
    assert not r.ok and "公钥" in r.error


def test_rsa_invalid_pem():
    assert not ct.rsa_encrypt("not a pem", b"x").ok
    assert not ct.rsa_encrypt("", b"x").ok


def test_key_not_in_envelope_meta():
    """安全约束：任何 meta 中都不应出现口令或原始密钥。"""
    secret = "TOP-SECRET-PASSPHRASE"
    enc = ct.encrypt(b"x", _cfg(passphrase=secret))
    blob = repr(enc.meta) + repr(enc.data[:64])
    assert secret not in blob


def test_iterations_respected():
    cfg = _cfg(pbkdf2_iterations=50000)
    enc = ct.encrypt(b"iter", cfg)
    assert enc.ok and enc.meta["iterations"] == 50000


# ---------------------------------------------------------------------------
# 密文解析（R1 修复回归：纯十六进制串是合法 Base64 字母表的子集，
# 先试 Base64 会把长度为 4 的倍数的 Hex 密文误解析成垃圾字节）
# ---------------------------------------------------------------------------

from app.ui.pages.crypto_page import encode_cipher_text, parse_cipher_text  # noqa: E402


def test_parse_cipher_text_hex_multiple_of_4():
    """Hex 密文长度恰为 4 的倍数时必须按 Hex 解析（曾误按 Base64 解析）。"""
    cfg = {"algorithm": "aes-gcm", "key_size": 256, "key_source": "passphrase",
           "passphrase": "test-parse-pass", "pbkdf2_iterations": 60000}
    enc = ct.encrypt("hex parse 回归测试".encode("utf-8"), cfg)
    assert enc.ok
    hex_ct = encode_cipher_text(enc.data, "hex")
    assert len(hex_ct) % 4 == 0  # 前置条件：长度确为 4 的倍数
    parsed, err = parse_cipher_text(hex_ct)
    assert err == ""
    assert parsed == enc.data


def test_parse_cipher_text_hex_odd_block():
    parsed, err = parse_cipher_text("9f86d081884c7d65")
    assert err == "" and parsed == bytes.fromhex("9f86d081884c7d65")


def test_parse_cipher_text_b64_prefix_forces_base64():
    import base64 as _b64
    raw = b"\x01\x02\x03\x04"
    parsed, err = parse_cipher_text("b64:" + _b64.b64encode(raw).decode())
    assert err == "" and parsed == raw


def test_parse_cipher_text_standard_b64():
    import base64 as _b64
    raw = b"anything-not-hex-chars-\xff\x00"
    parsed, err = parse_cipher_text(_b64.b64encode(raw).decode())
    assert err == "" and parsed == raw


def test_parse_cipher_text_invalid_reports_error():
    parsed, err = parse_cipher_text("!!!not-cipher!!!")
    assert parsed is None and err != ""
    parsed, err = parse_cipher_text("")
    assert parsed is None and "输入为空" in err


def test_encode_cipher_text_roundtrip():
    data = b"\x00\x01hello " + "你好".encode("utf-8")
    assert parse_cipher_text(encode_cipher_text(data, "base64"))[0] == data
    assert parse_cipher_text(encode_cipher_text(data, "hex"))[0] == data
