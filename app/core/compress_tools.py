"""压缩 / 解压算法层：GZIP / ZLIB / DEFLATE / ZIP / Brotli / Zstandard / LZ4。

安全设计：
- 所有解压操作都有输出大小上限（默认 512 MB），逐块解压、超限立即终止，防止压缩炸弹。
- 解压失败返回友好错误，原始输入不受影响。
"""

from __future__ import annotations

import gzip
import io
import zipfile
import zlib
from typing import Optional, Tuple

from .results import Result

DEFAULT_CAP_MB = 512
MAX_INPUT_BYTES = 256 * 1024 * 1024

FORMATS = ["gzip", "zlib", "deflate", "zip", "brotli", "zstd", "lz4"]
FORMAT_NAMES = {
    "gzip": "GZIP",
    "zlib": "ZLIB",
    "deflate": "DEFLATE（裸流）",
    "zip": "ZIP",
    "brotli": "Brotli",
    "zstd": "Zstandard",
    "lz4": "LZ4",
}

MAGICS: list = [
    ("gzip", bytes([0x1F, 0x8B])),
    ("zip", b"PK\x03\x04"),
    ("zstd", bytes([0x28, 0xB5, 0x2F, 0xFD])),
    ("lz4", bytes([0x04, 0x22, 0x4D, 0x18])),
]


class _CapExceeded(Exception):
    pass


# ---------------------------------------------------------------------------
# 可选依赖的加载
# ---------------------------------------------------------------------------

def _load_brotli():
    try:
        import brotli as _brotli  # type: ignore
        return _brotli
    except ImportError:
        try:
            import brotlicffi as _brotli  # type: ignore
            return _brotli
        except ImportError:
            return None


def _load_zstd():
    try:
        import zstandard as _zstd  # type: ignore
        return _zstd
    except ImportError:
        return None


def _load_lz4():
    try:
        import lz4.frame as _lz4frame  # type: ignore
        return _lz4frame
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# 逐块解压保护
# ---------------------------------------------------------------------------

def _accumulate(chunks, cap: int) -> bytes:
    total = 0
    out = []
    for chunk in chunks:
        total += len(chunk)
        if total > cap:
            raise _CapExceeded()
        if chunk:
            out.append(chunk)
    return b"".join(out)


def _guarded_zlib(data: bytes, wbits: int, cap: int) -> bytes:
    dec = zlib.decompressobj(wbits)
    out = bytearray()
    # 分块喂入，限制输出长度，超过上限立即停止
    pos = 0
    chunk_size = 1024 * 512
    while True:
        block = data[pos: pos + chunk_size]
        if block:
            out.extend(dec.decompress(block, max(0, cap - len(out) + 1)))
            if len(out) > cap:
                raise _CapExceeded()
            pos += chunk_size
        else:
            out.extend(dec.flush())
            if len(out) > cap:
                raise _CapExceeded()
            break
    return bytes(out)


def _guarded_zip_single(data: bytes, cap: int) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = zf.infolist()
        if not infos:
            raise ValueError("ZIP 中没有文件条目")
        # 优先 data.txt，否则取第一个条目
        target = None
        for info in infos:
            if info.filename == "data.txt":
                target = info
                break
        target = target or infos[0]
        if target.file_size > cap:
            raise _CapExceeded()
        with zf.open(target) as fh:
            out = fh.read(cap + 1)
            if len(out) > cap:
                raise _CapExceeded()
            return out


def _guarded_brotli(data: bytes, cap: int) -> bytes:
    mod = _load_brotli()
    if mod is None:
        raise ModuleNotFoundError("brotli")
    dec = mod.Decompressor()
    out = bytearray()
    pos = 0
    chunk_size = 1024 * 64  # 小块喂入，限制单次输出峰值
    while pos < len(data):
        block = data[pos: pos + chunk_size]
        out.extend(dec.process(block))
        if len(out) > cap:
            raise _CapExceeded()
        pos += chunk_size
    if not dec.is_finished():
        # 输入提前结束
        raise ValueError("Brotli 流不完整或已损坏")
    return bytes(out)


def _guarded_zstd(data: bytes, cap: int) -> bytes:
    mod = _load_zstd()
    if mod is None:
        raise ModuleNotFoundError("zstandard")
    dctx = mod.ZstdDecompressor(max_window_size=2 ** 27)
    try:
        # 帧头声明的内容大小若已超上限，直接拒绝（max_output_size 对
        # 已知大小的帧可能被忽略，不能依赖它）
        params = mod.get_frame_parameters(data)
        if params.content_size >= 0 and params.content_size > cap:
            raise _CapExceeded()
    except mod.ZstdError:
        raise ValueError("不是有效的 Zstandard 数据")
    out = bytearray()
    try:
        with dctx.stream_reader(data) as reader:
            while True:
                room = max(0, cap - len(out) + 1)
                if room == 0:
                    raise _CapExceeded()
                chunk = reader.read(min(1024 * 512, room))
                if not chunk:
                    break
                out.extend(chunk)
                if len(out) > cap:
                    raise _CapExceeded()
    except _CapExceeded:
        raise
    except mod.ZstdError as exc:
        msg = str(exc)
        if "Unknown frame descriptor" in msg or "not a valid" in msg.lower():
            raise ValueError("不是有效的 Zstandard 数据")
        raise ValueError(f"Zstandard 解压失败：{msg}")
    return bytes(out)


def _guarded_lz4(data: bytes, cap: int) -> bytes:
    mod = _load_lz4()
    if mod is None:
        raise ModuleNotFoundError("lz4")
    dec = mod.LZ4FrameDecompressor()
    out = bytearray()
    pos = 0
    chunk_size = 1024 * 512
    while pos < len(data):
        block = data[pos: pos + chunk_size]
        chunk = dec.decompress(block, max_length=max(0, cap - len(out) + 1))
        out.extend(chunk)
        if len(out) > cap:
            raise _CapExceeded()
        pos += chunk_size
        if dec.eof:
            break
    if not out:
        raise ValueError("不是有效的 LZ4 数据")
    return bytes(out)


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------

def compress(data: bytes, fmt: str, level: int = 6) -> Result:
    """压缩字节，返回 Result[bytes]。"""
    if fmt not in FORMATS:
        return Result.failure(f"未知压缩格式：{fmt}")
    if data is None:
        return Result.failure("输入为空")
    if len(data) > MAX_INPUT_BYTES:
        return Result.failure(f"输入过大（超过 256 MB 上限）")
    try:
        if fmt == "gzip":
            out = gzip.compress(data, compresslevel=level)
        elif fmt == "zlib":
            out = zlib.compress(data, level)
        elif fmt == "deflate":
            co = zlib.compressobj(level, zlib.DEFLATED, -15)
            out = co.compress(data) + co.flush()
        elif fmt == "zip":
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=level) as zf:
                zf.writestr("data.txt", data)
            out = buf.getvalue()
        elif fmt == "brotli":
            mod = _load_brotli()
            if mod is None:
                return Result.failure(
                    "Brotli 库未安装。请运行：pip install brotli"
                )
            quality = min(max(level, 0), 11)
            out = mod.compress(data, quality=quality)
        elif fmt == "zstd":
            mod = _load_zstd()
            if mod is None:
                return Result.failure(
                    "Zstandard 库未安装。请运行：pip install zstandard"
                )
            level_clamped = min(max(level, 1), 22)
            out = mod.ZstdCompressor(level=level_clamped).compress(data)
        elif fmt == "lz4":
            mod = _load_lz4()
            if mod is None:
                return Result.failure(
                    "LZ4 库未安装。请运行：pip install lz4"
                )
            level_clamped = min(max(level, 0), 16)
            out = mod.compress(data, compression_level=level_clamped)
        else:
            return Result.failure(f"未知压缩格式：{fmt}")
        return Result.success(out, fmt=fmt, in_bytes=len(data), out_bytes=len(out), label=FORMAT_NAMES.get(fmt, fmt))
    except _CapExceeded:
        raise
    except Exception as exc:
        return Result.failure(f"压缩失败：{exc}", repr(exc))


def decompress(data: bytes, fmt: Optional[str] = None, cap_mb: int = DEFAULT_CAP_MB) -> Result:
    """解压字节；fmt 为 None 时尝试按魔数自动识别。返回 Result[bytes]。"""
    if data is None or len(data) == 0:
        return Result.failure("输入为空：请提供待解压数据")
    if len(data) > MAX_INPUT_BYTES:
        return Result.failure(f"输入过大（超过 256 MB 上限）")
    cap = int(cap_mb) * 1024 * 1024
    if fmt is None:
        fmt = sniff(data)
        if fmt is None:
            return Result.failure(
                "无法识别压缩格式：文件头不符合 GZIP / ZIP / Zstandard / LZ4 / ZLIB 特征。"
                "请在参数中手动指定格式后重试"
            )
    if fmt not in FORMATS:
        return Result.failure(f"未知压缩格式：{fmt}")
    try:
        if fmt == "gzip":
            out = _guarded_zlib(data, 31, cap)
        elif fmt == "zlib":
            out = _guarded_zlib(data, 15, cap)
        elif fmt == "deflate":
            out = _guarded_zlib(data, -15, cap)
        elif fmt == "zip":
            out = _guarded_zip_single(data, cap)
        elif fmt == "brotli":
            out = _guarded_brotli(data, cap)
        elif fmt == "zstd":
            out = _guarded_zstd(data, cap)
        elif fmt == "lz4":
            out = _guarded_lz4(data, cap)
        else:
            return Result.failure(f"未知压缩格式：{fmt}")
        return Result.success(
            out, fmt=fmt, in_bytes=len(data), out_bytes=len(out),
            label=FORMAT_NAMES.get(fmt, fmt),
        )
    except _CapExceeded:
        return Result.failure(
            f"解压结果超过 {cap_mb} MB 上限，已终止（压缩炸弹防护）。"
            "如确需处理更大文件，请在设置中调高上限"
        )
    except ModuleNotFoundError as exc:
        return Result.failure(f"{exc.name} 库未安装。请运行：pip install {exc.name}")
    except zipfile.BadZipFile:
        return Result.failure("不是有效的 ZIP 数据（文件头损坏或不完整）")
    except zlib.error as exc:
        return Result.failure(f"解压失败：数据不是有效的 {FORMAT_NAMES.get(fmt, fmt)} 流", str(exc))
    except ValueError as exc:
        return Result.failure(f"解压失败：{exc}")
    except Exception as exc:
        return Result.failure(f"解压失败：{exc.__class__.__name__}: {exc}", repr(exc))


def sniff(data: bytes) -> Optional[str]:
    """按魔数识别压缩格式；ZLIB 用 0x78 头 + 双字节校验做启发式判断。"""
    if not data or len(data) < 2:
        return None
    for fmt, magic in MAGICS:
        if data[: len(magic)] == magic:
            return fmt
    if data[0] == 0x78:
        # ZLIB 头校验：CMF 低 4 位是压缩方法（须为 8 = deflate），
        # (CMF<<8 | FLG) % 31 == 0
        cm = data[0] & 0x0F
        check = ((data[0] << 8) + data[1]) % 31
        if cm == 8 and check == 0:
            return "zlib"
    return None


def try_auto_decompress(data: bytes, cap_mb: int = DEFAULT_CAP_MB) -> Result:
    """魔数识别失败时，再尝试裸 DEFLATE / ZLIB / GZIP 三种 wbits。"""
    for fmt, wbits in (("gzip", 31), ("zlib", 15), ("deflate", -15)):
        try:
            out = _guarded_zlib(data, wbits, int(cap_mb) * 1024 * 1024)
            return Result.success(out, fmt=fmt, in_bytes=len(data), out_bytes=len(out))
        except (_CapExceeded, zlib.error):
            continue
    return Result.failure("无法解压：不是有效的 GZIP / ZLIB / DEFLATE 数据")
