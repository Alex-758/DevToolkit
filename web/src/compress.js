/* 压缩 / 解压：GZIP / ZLIB / DEFLATE 走浏览器原生 CompressionStream。
 * ZIP / Brotli / Zstandard / LZ4 浏览器无原生实现 —— 明确提示，不静默失败。
 * 解压带输出上限（默认 64 MB），防压缩炸弹。
 */
globalThis.DT = globalThis.DT || {};
globalThis.DT.compress = (({ ok, fail, concat }) => {
  const DEFAULT_CAP_MB = 64;
  const hasCS = typeof CompressionStream !== "undefined";
  const hasDS = typeof DecompressionStream !== "undefined";

  const FORMATS = ["gzip", "zlib", "deflate"];
  const FORMAT_NAMES = { gzip: "GZIP", zlib: "ZLIB", deflate: "DEFLATE（裸流）", zip: "ZIP", brotli: "Brotli", zstd: "Zstandard", lz4: "LZ4" };
  const UNSUPPORTED = { zip: "ZIP", brotli: "Brotli", zstd: "Zstandard", lz4: "LZ4" };

  async function streamThrough(bytes, stream, cap = Infinity) {
    const out = new Blob([bytes]).stream().pipeThrough(stream);
    const reader = out.getReader();
    const chunks = [];
    let total = 0;
    try {
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        const chunk = part.value instanceof Uint8Array ? part.value : new Uint8Array(part.value);
        total += chunk.byteLength;
        if (total > cap) {
          await reader.cancel();
          const error = new Error("解压结果超过输出上限");
          error.code = "cap_exceeded";
          throw error;
        }
        chunks.push(chunk);
      }
      return concat(...chunks);
    } finally {
      reader.releaseLock();
    }
  }

  function zlibHeader(bytes) {
    // zlib = 2 字节头 + deflate 裸流 + 4 字节 Adler-32
    // 取 deflate 裸流时去掉 zlib 头尾即可
    if (bytes.length < 6) throw new Error("ZLIB 数据过短");
    const cmf = bytes[0], flg = bytes[1];
    if ((cmf & 0x0f) !== 8) throw new Error("不是有效的 ZLIB 数据（压缩方法非 deflate）");
    if (((cmf << 8) + flg) % 31 !== 0) throw new Error("ZLIB 头校验失败");
    if ((flg & 0x20) !== 0) throw new Error("ZLIB 预设字典数据不受支持");
    return { body: bytes.slice(2, bytes.length - 4), adler: bytes.slice(bytes.length - 4) };
  }
  function deflateToZlib(body, raw) {
    // 用 Adler-32 手工封装：CMF=0x78, FLG 使 (CMF<<8|FLG)%31==0
    const cmf = 0x78;
    const flg = 0x9c; // 默认压缩级别，校验通过
    return concat(new Uint8Array([cmf, flg]), body, adler32(raw));
  }
  function adler32(bytes) {
    let a = 1, b = 0;
    for (let i = 0; i < bytes.length; i++) {
      a = (a + bytes[i]) % 65521;
      b = (b + a) % 65521;
    }
    const out = new Uint8Array(4);
    out[0] = (b >>> 8) & 0xff; out[1] = b & 0xff;
    out[2] = (a >>> 8) & 0xff; out[3] = a & 0xff;
    return out;
  }
  function sameBytes(a, b) {
    return a.length === b.length && a.every((v, i) => v === b[i]);
  }

  async function compressBytes(data, fmt) {
    if (UNSUPPORTED[fmt]) {
      return fail(`浏览器不支持 ${UNSUPPORTED[fmt]} 压缩（无原生实现）。可用格式：GZIP / ZLIB / DEFLATE`);
    }
    if (!FORMATS.includes(fmt)) return fail(`未知压缩格式：${fmt}`);
    if (!hasCS) return fail("当前浏览器不支持 CompressionStream，请使用较新版本浏览器");
    if (data == null) return fail("输入为空");
    try {
      if (fmt === "gzip") {
        const out = await streamThrough(data, new CompressionStream("gzip"));
        return ok(out, { fmt, in_bytes: data.length, out_bytes: out.length, label: "GZIP" });
      }
      if (fmt === "deflate") {
        // CompressionStream 的 "deflate" 产生 zlib 包装；"deflate-raw" 为裸流
        const out = await streamThrough(data, new CompressionStream("deflate-raw"));
        return ok(out, { fmt, in_bytes: data.length, out_bytes: out.length, label: "DEFLATE（裸流）" });
      }
      // zlib：用 deflate-raw + 手工 zlib 头/尾
      const raw = await streamThrough(data, new CompressionStream("deflate-raw"));
      const out = deflateToZlib(raw, data);
      return ok(out, { fmt: "zlib", in_bytes: data.length, out_bytes: out.length, label: "ZLIB" });
    } catch (e) {
      return fail(`压缩失败：${e.message}`);
    }
  }

  async function decompressBytes(data, fmt, capMb = DEFAULT_CAP_MB) {
    if (UNSUPPORTED[fmt]) {
      return fail(`浏览器不支持 ${UNSUPPORTED[fmt]} 解压（无原生实现）。可用格式：GZIP / ZLIB / DEFLATE`);
    }
    if (!FORMATS.includes(fmt)) return fail(`未知压缩格式：${fmt}`);
    if (!hasDS) return fail("当前浏览器不支持 DecompressionStream，请使用较新版本浏览器");
    if (!data || !data.length) return fail("输入为空：请提供待解压数据");
    const cap = capMb * 1024 * 1024;
    try {
      let body = data;
      let expectedAdler = null;
      if (fmt === "zlib") {
        const parsed = zlibHeader(data);
        body = parsed.body;
        expectedAdler = parsed.adler;
      }
      let out;
      try {
        out = await streamThrough(body, new DecompressionStream(fmt === "deflate" ? "deflate-raw" : fmt), cap);
      } catch (e) {
        if (e.code === "cap_exceeded") {
          return fail(`解压结果超过 ${capMb} MB 上限，已终止（压缩炸弹防护）`, "cap_exceeded");
        }
        throw e;
      }
      if (expectedAdler && !sameBytes(adler32(out), expectedAdler)) {
        return fail("解压失败：ZLIB 数据校验和不匹配，输入可能已损坏");
      }
      return ok(out, { fmt, in_bytes: data.length, out_bytes: out.length, label: FORMAT_NAMES[fmt] });
    } catch (e) {
      if (e.code === "cap_exceeded") {
        return fail(`解压结果超过 ${capMb} MB 上限，已终止（压缩炸弹防护）`, "cap_exceeded");
      }
      return fail(`解压失败：数据不是有效的 ${FORMAT_NAMES[fmt]} 流或已损坏`, e.message);
    }
  }

  function sniff(data) {
    if (!data || data.length < 2) return null;
    if (data[0] === 0x1f && data[1] === 0x8b) return "gzip";
    if (data[0] === 0x78 && ((data[0] << 8) + data[1]) % 31 === 0 && (data[0] & 0x0f) === 8) return "zlib";
    if (data.length >= 4 && data[0] === 0x50 && data[1] === 0x4b && data[2] === 0x03 && data[3] === 0x04) return "zip";
    if (data.length >= 4 && data[0] === 0x28 && data[1] === 0xb5 && data[2] === 0x2f && data[3] === 0xfd) return "zstd";
    if (data.length >= 4 && data[0] === 0x04 && data[1] === 0x22 && data[2] === 0x4d && data[3] === 0x18) return "lz4";
    return null;
  }

  return {
    FORMATS, FORMAT_NAMES, UNSUPPORTED, DEFAULT_CAP_MB,
    compressBytes, decompressBytes, sniff,
    supportsCompression: hasCS, supportsDecompression: hasDS,
  };
})(globalThis.DT.core);
