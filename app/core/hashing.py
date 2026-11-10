"""哈希计算：MD5 / SHA 全系 / SHA3 / BLAKE2，支持文本与文件流式计算。

注意：哈希是不可逆摘要，不属于加密 —— UI 层会明确区分两者。
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .results import Result

MAX_TEXT_CHARS = 8_000_000

# (算法 id, 显示名, 摘要长度提示)
HASH_ALGOS: List[tuple] = [
    ("md5", "MD5", "128 位 · 已不安全，仅用于非安全场景校验"),
    ("sha1", "SHA-1", "160 位 · 已不安全，仅用于非安全场景校验"),
    ("sha224", "SHA-224", "224 位"),
    ("sha256", "SHA-256", "256 位 · 推荐"),
    ("sha384", "SHA-384", "384 位"),
    ("sha512", "SHA-512", "512 位 · 推荐"),
    ("sha3_256", "SHA3-256", "256 位"),
    ("sha3_512", "SHA3-512", "512 位"),
    ("blake2b", "BLAKE2b-512", "512 位"),
    ("blake2s", "BLAKE2s-256", "256 位"),
]

ALGO_IDS = [a[0] for a in HASH_ALGOS]


def _new(algo: str) -> "hashlib._Hash":
    if algo == "blake2b":
        return hashlib.blake2b(digest_size=64)
    if algo == "blake2s":
        return hashlib.blake2s(digest_size=32)
    return hashlib.new(algo)


def text_hash(text: str, algo: str) -> Result:
    """计算文本（UTF-8 字节）的单个哈希。"""
    if text is None:
        return Result.failure("输入为空：请输入待哈希内容")
    if algo not in ALGO_IDS:
        return Result.failure(f"未知哈希算法：{algo}")
    if len(text) > MAX_TEXT_CHARS:
        return Result.failure(f"输入过大（超过 8 MB），请使用文件哈希")
    data = text.encode("utf-8")
    h = _new(algo)
    h.update(data)
    digest = h.hexdigest()
    return Result.success(digest, algo=algo, in_bytes=len(data))


def text_hash_all(text: str, algos: Optional[List[str]] = None) -> Result:
    """一次计算多种哈希。返回 dict: algo -> hexdigest。"""
    if text is None:
        return Result.failure("输入为空：请输入待哈希内容")
    if len(text) > MAX_TEXT_CHARS:
        return Result.failure(f"输入过大（超过 8 MB），请使用文件哈希")
    algos = algos or ALGO_IDS
    data = text.encode("utf-8")
    out: Dict[str, str] = {}
    for algo in algos:
        if algo not in ALGO_IDS:
            return Result.failure(f"未知哈希算法：{algo}")
        h = _new(algo)
        h.update(data)
        out[algo] = h.hexdigest()
    return Result.success(out, in_bytes=len(data))


def file_hash(
    path: str,
    algos: Optional[List[str]] = None,
    progress: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Result:
    """流式计算文件哈希，支持大文件；progress(已处理字节, 总字节)。"""
    algos = algos or ALGO_IDS
    for algo in algos:
        if algo not in ALGO_IDS:
            return Result.failure(f"未知哈希算法：{algo}")
    try:
        file_path = Path(path)
        total = file_path.stat().st_size
    except OSError as exc:
        return Result.failure(f"无法读取文件：{exc.strerror or exc}", str(exc))
    digesters = [_new(algo) for algo in algos]
    try:
        with open(file_path, "rb") as fh:
            done = 0
            while True:
                if cancel_check is not None and cancel_check():
                    return Result.failure("已取消")
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                for d in digesters:
                    d.update(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
    except OSError as exc:
        return Result.failure(f"读取文件失败：{exc.strerror or exc}", str(exc))
    out = {algo: d.hexdigest() for algo, d in zip(algos, digesters)}
    return Result.success(out, in_bytes=total, path=str(file_path))


def compare(a: str, b: str) -> Result:
    """比较两个哈希值（忽略大小写与空白）。"""
    a_clean = (a or "").strip().lower().replace(" ", "")
    b_clean = (b or "").strip().lower().replace(" ", "")
    if not a_clean or not b_clean:
        return Result.failure("请输入两个哈希值进行比较")
    same = a_clean == b_clean
    return Result.success(same, a=a_clean, b=b_clean)


def algo_display(algo: str) -> str:
    for aid, name, _ in HASH_ALGOS:
        if aid == algo:
            return name
    return algo
