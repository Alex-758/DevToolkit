"""加密 / 解密算法层：AES-128/192/256（GCM / CBC / ECB）、ChaCha20-Poly1305、RSA。

安全设计：
- 默认推荐 AEAD 模式（GCM / ChaCha20-Poly1305），ECB 属不安全模式，UI 层会显示红色风险标记。
- 口令从不直接用作密钥：经 PBKDF2-HMAC-SHA256（默认 210,000 次迭代 + 随机盐）派生。
- Nonce / IV 每次加密随机生成。
- 密文使用自描述信封格式：
    口令模式：  b"DTK1" + salt(16) + nonce/iv + ciphertext(+tag)
    原始密钥：  nonce/iv + ciphertext(+tag)   （ECB 为裸密文）
- 本模块绝不记录、存储任何密钥与口令。
"""

from __future__ import annotations

import os
import secrets
from typing import Optional, Tuple

from Crypto.Cipher import AES, ChaCha20_Poly1305, PKCS1_OAEP
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5, pss
from Crypto.Util.Padding import pad, unpad

from .results import Result

ENV_MAGIC = b"DTK1"
DEFAULT_ITERATIONS = 210_000
MIN_ITERATIONS = 50_000
MAX_ITERATIONS = 2_000_000
MAX_DATA_BYTES = 64 * 1024 * 1024
MAX_RSA_ENCRYPT_BYTES = {2048: 190, 3072: 318, 4096: 446}  # OAEP-SHA256

ALGORITHMS = {
    "aes-gcm": {"name": "AES-GCM", "aead": True, "nonce_len": 12, "sizes": (128, 192, 256), "risk": "ok"},
    "aes-cbc": {"name": "AES-CBC", "aead": False, "iv_len": 16, "sizes": (128, 192, 256), "risk": "warn"},
    "aes-ecb": {"name": "AES-ECB", "aead": False, "iv_len": 0, "sizes": (128, 192, 256), "risk": "err"},
    "chacha20-poly1305": {"name": "ChaCha20-Poly1305", "aead": True, "nonce_len": 12, "sizes": (256,), "risk": "ok"},
    "rsa-oaep": {"name": "RSA-OAEP", "aead": True, "sizes": (), "risk": "ok"},
    "rsa-pss": {"name": "RSA-PSS（签名 / 验签）", "aead": True, "sizes": (), "risk": "ok"},
}

ALGO_ORDER = ["aes-gcm", "aes-cbc", "aes-ecb", "chacha20-poly1305", "rsa-oaep", "rsa-pss"]


def _safe_int(value, default: int) -> int:
    """cfg 数值清洗：非法类型 / 非法值回落默认（与 config 层「越界回落」策略一致）。

    旧实现 int(value) 直接暴露在 try 之外，字符串参数会让 ValueError
    逃出本应绝不抛异常的核心层。
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _brief(text, limit: int = 60) -> str:
    """错误信息中的用户输入回显截断：防止超长输入撑爆错误提示。"""
    s = str(text)
    return s if len(s) <= limit else s[:limit] + "…"


# ---------------------------------------------------------------------------
# 密钥相关
# ---------------------------------------------------------------------------

def derive_key(passphrase: str, salt: bytes, key_bytes: int, iterations: int = DEFAULT_ITERATIONS) -> bytes:
    iterations = max(MIN_ITERATIONS, min(int(iterations), MAX_ITERATIONS))
    return hashlib_pbkdf2(passphrase, salt, iterations, key_bytes)


def hashlib_pbkdf2(passphrase: str, salt: bytes, iterations: int, key_bytes: int) -> bytes:
    import hashlib
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations, dklen=key_bytes)


def parse_raw_key(raw: str, key_bytes: int) -> Result:
    """解析用户提供的原始密钥：支持 Hex 与 Base64，校验长度。"""
    s = (raw or "").strip()
    if not s:
        return Result.failure("密钥为空：请输入密钥、粘贴 Hex/Base64 或点击生成随机密钥")
    key = None
    hex_re_norm = s.replace(" ", "").replace(":", "").lower()
    if s.lower().startswith("hex:"):
        # 注意：先去掉前缀再归一化，避免冒号被删除后索引偏移
        candidate = s[4:].replace(" ", "").replace(":", "").lower()
        if len(candidate) % 2 or not all(c in "0123456789abcdef" for c in candidate):
            return Result.failure("Hex 密钥格式无效：长度必须为偶数且仅含 0–9 A–F")
        key = bytes.fromhex(candidate)
    elif s.lower().startswith("b64:"):
        import base64 as _b64
        try:
            key = _b64.b64decode(s[4:], validate=True)
        except Exception:
            return Result.failure("Base64 密钥格式无效")
    elif all(c in "0123456789abcdefABCDEF" for c in hex_re_norm) and len(hex_re_norm) % 2 == 0 and len(hex_re_norm) > 0:
        # 不带前缀时优先按 Hex 解析（最常见）
        key = bytes.fromhex(hex_re_norm)
    else:
        import base64 as _b64
        try:
            key = _b64.b64decode(s, validate=True)
        except Exception:
            return Result.failure("无法识别密钥格式：请使用 Hex 或 Base64，或加前缀 hex:/b64: 强制指定")
    if len(key) != key_bytes:
        return Result.failure(
            f"密钥长度不正确：当前 {len(key)} 字节，算法需要 {key_bytes} 字节"
            f"（{key_bytes * 8} 位）"
        )
    return Result.success(key, key_bytes=len(key))


def generate_random_key(key_bytes: int) -> Result:
    if key_bytes not in (16, 24, 32):
        return Result.failure("密钥长度必须是 16 / 24 / 32 字节（128 / 192 / 256 位）")
    return Result.success(secrets.token_hex(key_bytes), key_bytes=key_bytes)


def _resolve_key(cfg: dict, algo_id: str) -> Tuple[Optional[bytes], Optional[Result]]:
    """根据配置返回 (key, error_result)。口令模式返回 None 交由信封处理。"""
    info = ALGORITHMS[algo_id]
    key_bytes = _safe_int(cfg.get("key_size", 256), 256) // 8 if info["sizes"] else 32
    if cfg.get("key_source", "passphrase") == "raw":
        parsed = parse_raw_key(cfg.get("raw_key", ""), key_bytes)
        if not parsed.ok:
            return None, parsed
        return parsed.data, None
    passphrase = cfg.get("passphrase", "")
    if not passphrase:
        return None, Result.failure("口令为空：请输入口令，或切换为「原始密钥」模式")
    return passphrase, None


# ---------------------------------------------------------------------------
# 信封格式
# ---------------------------------------------------------------------------

def _pack_envelope(passphrase_mode: bool, salt: bytes, nonce: bytes, body: bytes) -> bytes:
    if passphrase_mode:
        return ENV_MAGIC + salt + nonce + body
    return nonce + body if nonce else body


def _unpack_envelope(data: bytes, passphrase_mode: bool, nonce_len: int) -> Tuple[bytes, bytes, bytes]:
    """返回 (salt, nonce, body)。原始密钥模式 salt 为空。"""
    if passphrase_mode:
        if len(data) < len(ENV_MAGIC) + 16 + nonce_len:
            raise ValueError("密文长度不完整（信封格式损坏）")
        if data[:4] != ENV_MAGIC:
            raise ValueError("密文缺少 DevToolkit 信封头（DTK1）：口令模式下加密时会自动附加")
        salt = data[4:20]
        nonce = data[20:20 + nonce_len]
        body = data[20 + nonce_len:]
        return salt, nonce, body
    if nonce_len:
        if len(data) < nonce_len:
            raise ValueError("密文长度不完整（缺少 Nonce / IV）")
        return b"", data[:nonce_len], data[nonce_len:]
    return b"", b"", data


# ---------------------------------------------------------------------------
# 对称加密
# ---------------------------------------------------------------------------

def encrypt(data: bytes, cfg: dict) -> Result:
    if data is None:
        return Result.failure("输入为空")
    if len(data) > MAX_DATA_BYTES:
        return Result.failure(f"输入过大（超过 64 MB 上限），请使用文件处理")
    algo_id = cfg.get("algorithm", "aes-gcm")
    if algo_id not in ALGORITHMS or algo_id.startswith("rsa"):
        return Result.failure(f"对称加密不支持算法：{_brief(algo_id)}")
    info = ALGORITHMS[algo_id]
    key_size = _safe_int(cfg.get("key_size", 256), 256)
    if info["sizes"] and key_size not in info["sizes"]:
        return Result.failure(f"{info['name']} 密钥长度必须是 {info['sizes']} 位之一")
    key_bytes = key_size // 8
    passphrase_mode = cfg.get("key_source", "passphrase") != "raw"
    iterations = _safe_int(cfg.get("pbkdf2_iterations", DEFAULT_ITERATIONS), DEFAULT_ITERATIONS)

    key_or_err = _resolve_key(cfg, algo_id)
    if key_or_err[1] is not None:
        return key_or_err[1]
    key, _ = key_or_err

    salt = b""
    try:
        if passphrase_mode:
            if not cfg.get("passphrase", ""):
                return Result.failure("口令为空：请输入口令")
            salt = secrets.token_bytes(16)
            key = derive_key(cfg["passphrase"], salt, key_bytes, iterations)

        if algo_id == "aes-gcm":
            nonce = secrets.token_bytes(12)
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=16)
            ct, tag = cipher.encrypt_and_digest(data)
            body = ct + tag
            envelope = _pack_envelope(passphrase_mode, salt, nonce, body)
        elif algo_id == "chacha20-poly1305":
            nonce = secrets.token_bytes(12)
            cipher = ChaCha20_Poly1305.new(key=key, nonce=nonce)
            ct, tag = cipher.encrypt_and_digest(data)
            body = ct + tag
            envelope = _pack_envelope(passphrase_mode, salt, nonce, body)
        elif algo_id == "aes-cbc":
            iv = secrets.token_bytes(16)
            cipher = AES.new(key, AES.MODE_CBC, iv=iv)
            ct = cipher.encrypt(pad(data, 16, style="pkcs7"))
            envelope = _pack_envelope(passphrase_mode, salt, iv, ct)
        elif algo_id == "aes-ecb":
            cipher = AES.new(key, AES.MODE_ECB)
            ct = cipher.encrypt(pad(data, 16, style="pkcs7"))
            envelope = _pack_envelope(passphrase_mode, salt, b"", ct)
        else:
            return Result.failure(f"未知算法：{algo_id}")
        meta = {
            "algorithm": algo_id, "label": info["name"], "key_size": key_size,
            "risk": info["risk"], "iterations": iterations if passphrase_mode else 0,
            "in_bytes": len(data), "out_bytes": len(envelope),
        }
        if info["risk"] == "err":
            meta["warning"] = "ECB 模式不安全：相同明文块产生相同密文，泄露数据模式，仅限兼容旧系统使用"
        elif info["risk"] == "warn":
            meta["warning"] = "CBC 模式无认证：建议配合 HMAC 使用，或改用 GCM"
        return Result.success(envelope, **meta)
    except Exception as exc:
        return Result.failure(f"加密失败：{exc}", repr(exc))


def decrypt(data: bytes, cfg: dict) -> Result:
    if data is None or len(data) == 0:
        return Result.failure("输入为空：请提供待解密的密文")
    if len(data) > MAX_DATA_BYTES:
        return Result.failure(f"输入过大（超过 64 MB 上限）")
    algo_id = cfg.get("algorithm", "aes-gcm")
    if algo_id not in ALGORITHMS or algo_id.startswith("rsa"):
        return Result.failure(f"对称解密不支持算法：{_brief(algo_id)}")
    info = ALGORITHMS[algo_id]
    key_size = _safe_int(cfg.get("key_size", 256), 256)
    key_bytes = key_size // 8
    passphrase_mode = cfg.get("key_source", "passphrase") != "raw"
    iterations = _safe_int(cfg.get("pbkdf2_iterations", DEFAULT_ITERATIONS), DEFAULT_ITERATIONS)
    nonce_len = info.get("nonce_len", info.get("iv_len", 0))

    try:
        if passphrase_mode:
            if not cfg.get("passphrase", ""):
                return Result.failure("口令为空：请输入加密时使用的口令")
            salt, nonce, body = _unpack_envelope(data, True, nonce_len)
            key = derive_key(cfg["passphrase"], salt, key_bytes, iterations)
        else:
            salt, nonce, body = _unpack_envelope(data, False, nonce_len)
            parsed = parse_raw_key(cfg.get("raw_key", ""), key_bytes)
            if not parsed.ok:
                return parsed
            key = parsed.data

        if algo_id == "aes-gcm":
            if len(body) < 16:
                # 16 字节 = 纯认证 Tag：0 字节明文是合法输入（R5 B1 修复，
                # 旧实现要求至少 1 字节密文，导致空明文加密成功却永远无法解密）
                return Result.failure("密文不完整：GCM 密文至少包含 16 字节认证 Tag")
            ct, tag = body[:-16], body[-16:]
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=16)
            try:
                plain = cipher.decrypt_and_verify(ct, tag)
            except (ValueError, KeyError):
                return Result.failure("解密失败：认证校验未通过（密钥错误或密文已被篡改）")
        elif algo_id == "chacha20-poly1305":
            if len(body) < 16:
                # 同 GCM：0 字节明文 + 16 字节 Tag 是合法密文（R5 B1 修复）
                return Result.failure("密文不完整：Poly1305 密文至少包含 16 字节认证 Tag")
            ct, tag = body[:-16], body[-16:]
            cipher = ChaCha20_Poly1305.new(key=key, nonce=nonce)
            try:
                plain = cipher.decrypt_and_verify(ct, tag)
            except (ValueError, KeyError):
                return Result.failure("解密失败：认证校验未通过（密钥错误或密文已被篡改）")
        elif algo_id == "aes-cbc":
            if len(body) == 0 or len(body) % 16:
                return Result.failure("密文长度不合法：CBC 密文长度必须是 16 字节的整数倍")
            cipher = AES.new(key, AES.MODE_CBC, iv=nonce)
            try:
                plain = unpad(cipher.decrypt(body), 16, style="pkcs7")
            except ValueError:
                return Result.failure("解密失败：PKCS#7 填充无效（密钥错误或密文已损坏）")
        elif algo_id == "aes-ecb":
            if len(body) == 0 or len(body) % 16:
                return Result.failure("密文长度不合法：ECB 密文长度必须是 16 字节的整数倍")
            cipher = AES.new(key, AES.MODE_ECB)
            try:
                plain = unpad(cipher.decrypt(body), 16, style="pkcs7")
            except ValueError:
                return Result.failure("解密失败：PKCS#7 填充无效（密钥错误或密文已损坏）")
        else:
            return Result.failure(f"未知算法：{algo_id}")
        return Result.success(
            plain, algorithm=algo_id, label=info["name"], key_size=key_size,
            in_bytes=len(data), out_bytes=len(plain),
        )
    except ValueError as exc:
        # 信封解析错误
        return Result.failure(str(exc))
    except Exception as exc:
        return Result.failure(f"解密失败：{exc}", repr(exc))


# ---------------------------------------------------------------------------
# RSA
# ---------------------------------------------------------------------------

def generate_keypair(bits: int = 2048) -> Result:
    if bits not in (1024, 2048, 3072, 4096):
        return Result.failure("RSA 密钥长度必须是 1024 / 2048 / 3072 / 4096 位")
    if bits == 1024:
        pass  # 允许生成，但 UI 标注不安全
    try:
        key = RSA.generate(bits)
        private_pem = key.export_key(format="PEM", pkcs=8, protection=None)
        public_pem = key.publickey().export_key(format="PEM")
        return Result.success(
            {"private_pem": private_pem.decode("ascii"), "public_pem": public_pem.decode("ascii")},
            bits=bits,
        )
    except Exception as exc:
        return Result.failure(f"密钥生成失败：{exc}", repr(exc))


def _load_key(pem_text: str, expect_private: Optional[bool]) -> Result:
    s = (pem_text or "").strip()
    if not s:
        return Result.failure("密钥为空：请粘贴 PEM 格式密钥或导入密钥文件")
    try:
        key = RSA.import_key(s)
    except (ValueError, IndexError) as exc:
        return Result.failure(
            "无法解析 RSA 密钥：请确认是 PEM 格式（-----BEGIN PUBLIC KEY----- 或 -----BEGIN PRIVATE KEY-----）",
            str(exc),
        )
    if expect_private is True and not key.has_private():
        return Result.failure("这不是私钥：该操作需要私钥（应包含 BEGIN PRIVATE KEY / BEGIN RSA PRIVATE KEY）")
    if expect_private is False and key.has_private():
        return Result.failure("这是私钥：该操作需要公钥（应包含 BEGIN PUBLIC KEY）")
    return Result.success(key)


def _parse_envelope(data: bytes) -> Tuple[bytes, bytes]:
    """RSA 密文信封：b"DTK1" + ct（OAEP 无 nonce）。兼容裸密文。"""
    if data[:4] == ENV_MAGIC:
        return data[4:20], data[20:]
    return b"", data


def rsa_encrypt(pub_pem: str, data: bytes) -> Result:
    if data is None or len(data) == 0:
        return Result.failure("输入为空")
    loaded = _load_key(pub_pem, expect_private=False)
    if not loaded.ok:
        return loaded
    key = loaded.data
    limit = MAX_RSA_ENCRYPT_BYTES.get(key.size_in_bits(), key.size_in_bits() // 8 - 66)
    if len(data) > limit:
        return Result.failure(
            f"明文过长：RSA-OAEP 一次最多加密 {limit} 字节（{key.size_in_bits()} 位密钥）。"
            "更大数据请使用 AES 加密后再用 RSA 加密密钥（混合加密）"
        )
    try:
        cipher = PKCS1_OAEP.new(key, hashAlgo=SHA256)
        ct = cipher.encrypt(data)
        envelope = ENV_MAGIC + secrets.token_bytes(16) + ct
        return Result.success(
            envelope, label="RSA-OAEP", bits=key.size_in_bits(),
            in_bytes=len(data), out_bytes=len(envelope),
        )
    except Exception as exc:
        return Result.failure(f"RSA 加密失败：{exc}", repr(exc))


def rsa_decrypt(priv_pem: str, data: bytes) -> Result:
    if data is None or len(data) == 0:
        return Result.failure("输入为空：请提供待解密的密文")
    loaded = _load_key(priv_pem, expect_private=True)
    if not loaded.ok:
        return loaded
    key = loaded.data
    try:
        _, ct = _parse_envelope(data)
        if len(ct) != key.size_in_bytes():
            return Result.failure(
                f"密文长度不正确：当前 {len(ct)} 字节，{key.size_in_bits()} 位密钥的密文应为 "
                f"{key.size_in_bytes()} 字节"
            )
        cipher = PKCS1_OAEP.new(key, hashAlgo=SHA256)
        plain = cipher.decrypt(ct)
        return Result.success(plain, label="RSA-OAEP", bits=key.size_in_bits(), out_bytes=len(plain))
    except ValueError:
        return Result.failure("RSA 解密失败：密钥与密文不匹配或密文已损坏")
    except Exception as exc:
        return Result.failure(f"RSA 解密失败：{exc}", repr(exc))


def rsa_sign(priv_pem: str, data: bytes, scheme: str = "pss") -> Result:
    if data is None:
        return Result.failure("输入为空")
    loaded = _load_key(priv_pem, expect_private=True)
    if not loaded.ok:
        return loaded
    key = loaded.data
    try:
        digest = SHA256.new(data)
        if scheme == "pss":
            signer = pss.new(key)
        else:
            signer = PKCS1_v1_5.new(key)
        sig = signer.sign(digest)
        return Result.success(sig, label=f"RSA-{scheme.upper()}-SHA256", bits=key.size_in_bits(), out_bytes=len(sig))
    except Exception as exc:
        return Result.failure(f"签名失败：{exc}", repr(exc))


def rsa_verify(pub_pem: str, data: bytes, sig: bytes, scheme: str = "pss") -> Result:
    if data is None or sig is None or len(sig) == 0:
        return Result.failure("请提供原文与签名")
    loaded = _load_key(pub_pem, expect_private=False)
    if not loaded.ok:
        return loaded
    key = loaded.data
    try:
        digest = SHA256.new(data)
        try:
            if scheme == "pss":
                # PyCryptodome 的 pss.verify() 成功时返回 None，失败抛 ValueError
                pss.new(key).verify(digest, sig)
                ok = True
            else:
                ok = bool(PKCS1_v1_5.new(key).verify(digest, sig))
        except (ValueError, TypeError):
            ok = False
        return Result.success(bool(ok), label=f"RSA-{scheme.upper()}-SHA256")
    except Exception as exc:
        return Result.failure(f"验签失败：{exc}", repr(exc))


def looks_like_private_key(pem_text: str) -> bool:
    s = (pem_text or "").strip()
    return "BEGIN PRIVATE KEY" in s or "BEGIN RSA PRIVATE KEY" in s or "BEGIN ENCRYPTED PRIVATE KEY" in s


def risk_of(algo_id: str) -> str:
    return ALGORITHMS.get(algo_id, {}).get("risk", "warn")
