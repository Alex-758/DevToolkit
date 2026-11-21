/* 智能解码：自动尝试「编码 + 压缩」多层链路，与桌面版 smart_decode 语义一致。 */
globalThis.DT = globalThis.DT || {};
globalThis.DT.smart = (({ ok, fail, utf8, fromUtf8 }) => {
  const MAX_INPUT_CHARS = 4_000_000;
  const MAX_LAYERS = 10;
  const PREVIEW_LIMIT = 96;

  const clip = (s) => {
    s = s.replace(/\r/g, "").replace(/\n/g, "⏎");
    return s.length > PREVIEW_LIMIT ? s.slice(0, PREVIEW_LIMIT) + "…" : s;
  };
  const printableRatio = (s) => {
    if (!s) return 0;
    let n = 0;
    for (const ch of s) { const c = ch.codePointAt(0); if (c >= 32 || ch === "\t" || ch === "\n") n++; }
    return n / s.length;
  };
  const preview = (v) => {
    if (v instanceof Uint8Array) {
      try {
        const t = fromUtf8(v);
        if (printableRatio(t) > 0.8) return clip(t);
      } catch {}
      const head = Array.from(v.slice(0, 16), (b) => b.toString(16).padStart(2, "0").toUpperCase());
      return head.join(" ") + ` …（二进制 ${v.length.toLocaleString()} 字节）`;
    }
    return clip(String(v));
  };

  async function tryStringDecoders(text) {
    const CD = globalThis.DT.codecs;
    const compact = text.replace(/\s+/g, "");
    const trials = [];
    if (/^[A-Za-z0-9+/]{16,}={0,2}$/.test(compact) && compact.length % 4 === 0) trials.push(["Base64 解码", "base64"]);
    if (/^[A-Za-z0-9\-_]{16,}={0,2}$/.test(compact) && compact.length % 4 !== 1) trials.push(["Base64URL 解码", "base64url"]);
    if (/^[0-9a-fA-F]{16,}$/.test(compact) && compact.length % 2 === 0) trials.push(["Hex 解码", "hex"]);
    if (/^[A-Z2-7]+={0,6}$/.test(compact) && compact.length % 8 === 0 && compact.length >= 8) trials.push(["Base32 解码", "base32"]);
    if (/%[0-9A-Fa-f]{2}/.test(text)) trials.push(["URL 解码", "url"]);
    if (/\\u[0-9a-fA-F]{4}/.test(text)) trials.push(["Unicode 转义解码", "unicode"]);
    if (/&(#[0-9]{2,}|#[xX][0-9a-fA-F]{2,}|[a-zA-Z]{2,8});/.test(text)) trials.push(["HTML 实体解码", "html"]);

    for (const [action, codecId] of trials) {
      const r = CD.runCodec(codecId, "decode", compact);
      if (!r.ok) continue;
      const decoded = r.data;
      if (decoded === text) continue;
      // URL / Unicode / HTML 返回字符串；字节型返回的也是字符串（此处按文本处理）
      return { action, codecId, value: decoded };
    }
    return null;
  }

  async function tryDecompress(bytes, capMb) {
    const CP = globalThis.DT.compress;
    const fmt = CP.sniff(bytes);
    if (!fmt) return null;
    const r = await CP.decompressBytes(bytes, fmt, capMb);
    if (!r.ok) {
      if (r.detail === "cap_exceeded") return { bomb: true, error: r.error };
      return null;
    }
    return { action: `${CP.FORMAT_NAMES[fmt]} 解压`, value: r.data };
  }

  return async function smartDecode(text, maxLayers = 5, capMb = 64) {
    if (text == null || !text.trim()) return fail("请先输入待解码内容");
    if (text.length > MAX_INPUT_CHARS) return fail("输入过大（超过 4 MB），请使用文件处理");
    maxLayers = Math.max(1, Math.min(Math.trunc(maxLayers) || 5, MAX_LAYERS));

    const steps = [];
    const seen = new Set();
    const chain = [];
    let current = text;
    let layers = 0;

    while (layers < maxLayers) {
      if (typeof current === "string") {
        const key = current.slice(0, 4096);
        if (seen.has(key)) break;
        seen.add(key);
        const trial = await tryStringDecoders(current);
        if (!trial) break;
        const before = current;
        let decoded = trial.value;
        // 若解码结果是可打印文本，先看是否藏着压缩数据
        let bytes = null;
        try { bytes = utf8(decoded); } catch {}
        if (bytes) {
          const comp = await tryDecompress(bytes, capMb);
          if (comp && comp.bomb) return fail(comp.error, "压缩炸弹防护终止：已保留原始输入");
          if (comp && comp.action) {
            steps.push({
              index: steps.length + 1, action: trial.action,
              detail: "解码为二进制后检测到压缩魔数",
              beforePreview: preview(before), afterPreview: preview(bytes),
              beforeSize: `${before.length.toLocaleString()} 字符`, afterSize: `${bytes.length.toLocaleString()} 字节`,
            });
            chain.push(trial.codecId);
            layers++;
            if (layers >= maxLayers) { current = bytes; break; }
            steps.push({
              index: steps.length + 1, action: comp.action, detail: "压缩魔数命中，解压成功",
              beforePreview: preview(bytes), afterPreview: preview(comp.value),
              beforeSize: `${bytes.length.toLocaleString()} 字节`, afterSize: `${comp.value.length.toLocaleString()} 字节`,
            });
            chain.push(comp.action.split(" ")[0].toLowerCase());
            layers++;
            try { current = fromUtf8(comp.value); } catch { current = comp.value; }
            continue;
          }
        }
        steps.push({
          index: steps.length + 1, action: trial.action, detail: "特征匹配并解码成功",
          beforePreview: preview(before), afterPreview: preview(decoded),
          beforeSize: `${before.length.toLocaleString()} 字符`, afterSize: `${decoded.length.toLocaleString()} 字符`,
        });
        chain.push(trial.codecId);
        layers++;
        current = decoded;
      } else {
        const comp = await tryDecompress(current, capMb);
        if (comp && comp.bomb) return fail(comp.error, "压缩炸弹防护终止：已保留原始输入");
        if (comp) {
          steps.push({
            index: steps.length + 1, action: comp.action, detail: "压缩魔数命中，解压成功",
            beforePreview: preview(current), afterPreview: preview(comp.value),
            beforeSize: `${current.length.toLocaleString()} 字节`, afterSize: `${comp.value.length.toLocaleString()} 字节`,
          });
          chain.push(comp.action.split(" ")[0].toLowerCase());
          layers++;
          try { current = fromUtf8(comp.value); } catch { current = comp.value; }
          continue;
        }
        try { current = fromUtf8(current); }
        catch { break; }
        steps.push({
          index: steps.length + 1, action: "UTF-8 文本确认", detail: "二进制数据为有效 UTF-8 文本",
          beforePreview: preview(current), afterPreview: preview(current),
          beforeSize: `${current.length.toLocaleString()} 字节`, afterSize: `${current.length.toLocaleString()} 字符`,
        });
        chain.push("utf-8");
        layers++;
      }
    }

    if (current instanceof Uint8Array) {
      try { current = fromUtf8(current); }
      catch {
        return fail("解码终止：结果为二进制数据且无法进一步解压或按文本显示。已保留原始输入");
      }
    }

    const names = {
      base64: "Base64", base64url: "Base64URL", hex: "Hex", base32: "Base32",
      url: "URL", unicode: "Unicode", html: "HTML 实体",
      gzip: "GZIP", zlib: "ZLIB", deflate: "DEFLATE", "utf-8": "UTF-8",
    };
    const chainStr = chain.length ? chain.map((c) => names[c] || c).join(" → ") : "（未做任何处理）";
    let note;
    if (layers >= maxLayers && chain.length) note = `已达最大层数（${maxLayers} 层）自动终止`;
    else if (chain.length) note = "链路自然终止（结果已是可读文本且无进一步特征）";
    else note = "未识别到可解码的编码特征，保留原始输入";

    return ok({ finalText: current, steps, chain: chainStr, layersUsed: layers }, { note, layers_used: layers, max_layers: maxLayers });
  };
})(globalThis.DT.core);
