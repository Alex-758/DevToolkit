/* codecs.js — 单文件构建用：IIFE 工厂，依赖显式注入，无全局污染 */
globalThis.DT = globalThis.DT || {};
globalThis.DT.codecs = (({ ok, fail, utf8, fromUtf8, unhex }) => {
/* 编码 / 解码：与桌面版 12 种编解码器对齐。
 * Web Crypto 只有 base64 辅助，其余用纯 JS 实现（浏览器语义与 Python 保持一致）。
 */

const B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
const B62_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
const B58_B62_MAX_CHARS = 32000;
const MAX_INPUT_CHARS = 8_000_000;

const guard = (text) => {
  if (text == null) return fail("输入为空：请输入待处理内容");
  if (text.length > MAX_INPUT_CHARS) {
    return fail(`输入过大（${text.length.toLocaleString()} 字符，超过 8 MB 上限）`);
  }
  return null;
};
const stripWs = (s) => s.replace(/\s+/g, "");

/* ---------------- Base64 ---------------- */
function b64Encode(text, { urlsafe = false, charset = "utf-8", wrap = 0 } = {}) {
  const g = guard(text); if (g) return g;
  let bytes;
  try { bytes = encodeText(text, charset); } catch (e) { return fail(e.message); }
  let out = bytesToB64(bytes);
  if (urlsafe) out = out.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  if (wrap > 0) out = out.replace(new RegExp(`(.{${wrap}})`, "g"), "$1\n").replace(/\n$/, "");
  return ok(out, { in_bytes: bytes.length, out_chars: out.length });
}
function b64Decode(text, { urlsafe = false, charset = "utf-8" } = {}) {
  const g = guard(text); if (g) return g;
  const compact = stripWs(text);
  if (!compact) return ok("");
  const allowed = urlsafe ? /^[A-Za-z0-9\-_]+={0,2}$/ : /^[A-Za-z0-9+/]+={0,2}$/;
  if (!allowed.test(compact)) {
    return fail(`输入包含非 ${urlsafe ? "Base64 URL Safe" : "Base64"} 字符`);
  }
  if (compact.replace(/=/g, "").length % 4 === 1) return fail("长度不合法：不能是 4n+1");
  let s = compact.replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  let bytes;
  try { bytes = unB64(s); } catch { return fail("Base64 解码失败"); }
  try { return ok(decodeText(bytes, charset), { in_bytes: compact.length, out_bytes: bytes.length }); }
  catch { return fail(`解码结果不是有效的 ${charset} 文本（输入可能不是文本数据或字符集选错）`); }
}

/* ---------------- Base32 ---------------- */
const B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
function b32Encode(text, { charset = "utf-8" } = {}) {
  const g = guard(text); if (g) return g;
  let bytes;
  try { bytes = encodeText(text, charset); } catch (e) { return fail(e.message); }
  let bits = 0, value = 0, out = "";
  for (const b of bytes) {
    value = (value << 8) | b; bits += 8;
    while (bits >= 5) { out += B32[(value >>> (bits - 5)) & 31]; bits -= 5; }
  }
  if (bits > 0) out += B32[(value << (5 - bits)) & 31];
  while (out.length % 8) out += "=";
  return ok(out, { in_bytes: bytes.length, out_chars: out.length });
}
function b32Decode(text, { charset = "utf-8" } = {}) {
  const g = guard(text); if (g) return g;
  const c = stripWs(text).toUpperCase();
  if (!c) return ok("");
  if (!/^[A-Z2-7]+={0,6}$/.test(c)) return fail("输入包含非 Base32 字符。字母表为 A–Z 2–7，= 作为填充");
  const body = c.replace(/=+$/, "");
  const padLength = c.length - body.length;
  const remainder = body.length % 8;
  const validRemainders = new Set([0, 2, 4, 5, 7]);
  const expectedPadding = ({ 0: 0, 2: 6, 4: 4, 5: 3, 7: 1 })[remainder];
  if (!validRemainders.has(remainder) || (padLength && (c.length % 8 !== 0 || padLength !== expectedPadding))) {
    return fail("Base32 长度或填充不合法");
  }
  let bits = 0, value = 0;
  const out = [];
  for (const ch of body) {
    const idx = B32.indexOf(ch);
    if (idx < 0) return fail("Base32 解码失败");
    value = (value << 5) | idx; bits += 5;
    if (bits >= 8) { out.push((value >>> (bits - 8)) & 0xff); bits -= 8; }
  }
  if (bits > 0 && (value & ((1 << bits) - 1)) !== 0) return fail("Base32 尾部填充位必须为零");
  const bytes = new Uint8Array(out);
  try { return ok(decodeText(bytes, charset), { in_bytes: c.length, out_bytes: bytes.length }); }
  catch { return fail(`解码结果不是有效的 ${charset} 文本`); }
}

/* ---------------- Hex ---------------- */
function hexEncode(text, { charset = "utf-8", upper = false, sep = false } = {}) {
  const g = guard(text); if (g) return g;
  let bytes;
  try { bytes = encodeText(text, charset); } catch (e) { return fail(e.message); }
  let body = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  if (upper) body = body.toUpperCase();
  const out = sep ? body.replace(/(..)(?=.)/g, "$1 ") : body;
  return ok(out, { in_bytes: bytes.length, out_chars: out.length });
}
function hexDecode(text, { charset = "utf-8" } = {}) {
  const g = guard(text); if (g) return g;
  let c = stripWs(text).replace(/0x/gi, "");
  if (!c) return ok("");
  if (!/^[0-9a-fA-F]+$/.test(c)) {
    const bad = [...c].find((ch) => !/[0-9a-fA-F]/.test(ch)) ?? "?";
    return fail(`输入包含非十六进制字符（「${bad}」）。仅允许 0–9 A–F`);
  }
  if (c.length % 2) return fail("十六进制长度必须为偶数（每字节两位）");
  const bytes = unhex(c);
  try { return ok(decodeText(bytes, charset), { in_bytes: bytes.length, out_bytes: bytes.length }); }
  catch { return fail(`解码结果不是有效的 ${charset} 文本`); }
}

/* ---------------- Base58 / Base62（BigInt，平方级复杂度，有上限保护） ---------------- */
function baseNEncode(bytes, alphabet) {
  const base = BigInt(alphabet.length);
  let num = 0n;
  for (const b of bytes) num = num * 256n + BigInt(b);
  let out = "";
  while (num > 0n) { out = alphabet[Number(num % base)] + out; num /= base; }
  for (const b of bytes) { if (b === 0) out = alphabet[0] + out; else break; }
  return out;
}
function baseNDecode(str, alphabet) {
  const base = BigInt(alphabet.length);
  const idx = new Map([...alphabet].map((ch, i) => [ch, BigInt(i)]));
  let num = 0n;
  for (const ch of str) {
    const v = idx.get(ch);
    if (v === undefined) throw new Error(`输入包含非该字母表字符（「${ch}」）`);
    num = num * base + v;
  }
  const hexStr = num === 0n ? "" : num.toString(16);
  const padded = hexStr.length % 2 ? "0" + hexStr : hexStr;
  const body = padded ? unhex(padded) : new Uint8Array();
  let zeros = 0;
  for (const ch of str) { if (ch === alphabet[0]) zeros++; else break; }
  const out = new Uint8Array(zeros + body.length);
  out.set(body, zeros);
  return out;
}
function b58Encode(text, { charset = "utf-8" } = {}) {
  const g = guard(text); if (g) return g;
  if (text.length > B58_B62_MAX_CHARS) return fail(`输入过大：Base58 上限 ${B58_B62_MAX_CHARS.toLocaleString()} 字符`);
  let bytes; try { bytes = encodeText(text, charset); } catch (e) { return fail(e.message); }
  const out = baseNEncode(bytes, B58_ALPHABET);
  return ok(out, { in_bytes: bytes.length, out_chars: out.length });
}
function b58Decode(text, { charset = "utf-8" } = {}) {
  const g = guard(text); if (g) return g;
  const s = text.trim();
  if (!s) return ok("");
  if (s.length > B58_B62_MAX_CHARS) return fail(`输入过大：Base58 上限 ${B58_B62_MAX_CHARS.toLocaleString()} 字符`);
  let bytes; try { bytes = baseNDecode(s, B58_ALPHABET); } catch (e) { return fail(e.message); }
  try { return ok(decodeText(bytes, charset), { in_bytes: s.length, out_bytes: bytes.length }); }
  catch { return fail(`解码结果不是有效的 ${charset} 文本`); }
}
function b62Encode(text, { charset = "utf-8" } = {}) {
  const g = guard(text); if (g) return g;
  if (text.length > B58_B62_MAX_CHARS) return fail(`输入过大：Base62 上限 ${B58_B62_MAX_CHARS.toLocaleString()} 字符`);
  let bytes; try { bytes = encodeText(text, charset); } catch (e) { return fail(e.message); }
  const out = baseNEncode(bytes, B62_ALPHABET);
  return ok(out, { in_bytes: bytes.length, out_chars: out.length });
}
function b62Decode(text, { charset = "utf-8" } = {}) {
  const g = guard(text); if (g) return g;
  const s = text.trim();
  if (!s) return ok("");
  if (s.length > B58_B62_MAX_CHARS) return fail(`输入过大：Base62 上限 ${B58_B62_MAX_CHARS.toLocaleString()} 字符`);
  let bytes; try { bytes = baseNDecode(s, B62_ALPHABET); } catch (e) { return fail(e.message); }
  try { return ok(decodeText(bytes, charset), { in_bytes: s.length, out_bytes: bytes.length }); }
  catch { return fail(`解码结果不是有效的 ${charset} 文本`); }
}

/* ---------------- URL / HTML / Unicode / ASCII / ROT13 / QP ---------------- */
function urlEncode(text, { keepSlash = true, plusSpace = false } = {}) {
  const g = guard(text); if (g) return g;
  let out = encodeURIComponent(text);
  if (keepSlash) out = out.replace(/%2F/g, "/");
  // encodeURIComponent 已把空格编码为 %20
  if (plusSpace) out = out.replace(/%20/g, "+");
  return ok(out, { in_bytes: utf8(text).length, out_chars: out.length });
}
function urlDecode(text) {
  const g = guard(text); if (g) return g;
  const s = text.trim();
  if (!s) return ok("");
  try {
    const out = decodeURIComponent(s.replace(/\+/g, " "));
    return ok(out, { in_bytes: s.length, out_chars: out.length });
  } catch {
    return fail("URL 解码失败：存在无效的百分号序列或不完整的 UTF-8 编码");
  }
}
const HTML_ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#x27;" };
function htmlEncode(text, { entity = "hex", namedOnly = false } = {}) {
  const g = guard(text); if (g) return g;
  let out = "";
  for (const ch of text) {
    if (HTML_ESC[ch]) { out += HTML_ESC[ch]; continue; }
    const cp = ch.codePointAt(0);
    if (cp > 127 && !namedOnly) {
      out += entity === "dec" ? `&#${cp};` : `&#x${cp.toString(16)};`;
    } else out += ch;
  }
  return ok(out, { in_bytes: utf8(text).length, out_chars: out.length });
}
function htmlDecode(text) {
  const g = guard(text); if (g) return g;
  const s = text;
  if (!s) return ok("");
  let out;
  if (typeof document !== "undefined") {
    const tmp = document.createElement("textarea");
    tmp.innerHTML = s;
    out = tmp.value;
    tmp.remove();
  } else {
    // 无 DOM 环境（Node / Worker）：常用命名实体 + 数字实体
    const NAMED = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
    out = s.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (m, body) => {
      if (body[0] === "#") {
        const cp = body[1] === "x" || body[1] === "X"
          ? parseInt(body.slice(2), 16) : parseInt(body.slice(1), 10);
        return Number.isFinite(cp) && cp >= 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : m;
      }
      return NAMED[body.toLowerCase()] ?? m;
    });
  }
  return ok(out, { in_bytes: s.length, out_chars: out.length });
}
function unicodeEncode(text, { upper = false } = {}) {
  const g = guard(text); if (g) return g;
  let out = "";
  for (const ch of text) {
    const cp = ch.codePointAt(0);
    if (cp > 0xFFFF) {
      // 超出 BMP：按 UTF-16 代理对输出两个 \uXXXX（与桌面版 / JSON 语义一致）
      const v = cp - 0x10000;
      const hi = 0xD800 + (v >> 10), lo = 0xDC00 + (v & 0x3FF);
      let hs = hi.toString(16).padStart(4, "0");
      let ls = lo.toString(16).padStart(4, "0");
      if (upper) { hs = hs.toUpperCase(); ls = ls.toUpperCase(); }
      out += "\\u" + hs + "\\u" + ls;
    } else if (cp > 127) {
      let h = cp.toString(16).padStart(4, "0");
      if (upper) h = h.toUpperCase();
      out += "\\u" + h;
    } else out += ch;
  }
  return ok(out, { in_bytes: utf8(text).length, out_chars: out.length });
}
function unicodeDecode(text) {
  const g = guard(text); if (g) return g;
  if (!text.trim()) return ok("");
  const bad = /\\u(?![0-9a-fA-F]{4})/.exec(text);
  if (bad) return fail("Unicode 解码失败：存在无效的 \\u 序列（\\u 后必须跟 4 位十六进制）");
  try {
    const out = text.replace(/\\u([0-9a-fA-F]{4})/g, (_, h) => String.fromCharCode(parseInt(h, 16)));
    if (/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(out)) {
      return fail("Unicode 解码失败：存在未配对的 UTF-16 代理项");
    }
    return ok(out, { in_bytes: text.length, out_chars: out.length });
  } catch { return fail("Unicode 解码失败"); }
}
function asciiEncode(text, { hexMode = false } = {}) {
  const g = guard(text); if (g) return g;
  const parts = [];
  let i = 0;
  for (const ch of text) {
    const cp = ch.codePointAt(0);
    if (cp > 127) {
      return fail(`第 ${i + 1} 个字符「${ch}」超出 ASCII 范围（0–127）。中文字符请改用 Hex 或 Base64`);
    }
    parts.push(hexMode ? "0x" + cp.toString(16).toUpperCase().padStart(2, "0") : String(cp));
    i++;
  }
  const out = parts.join(" ");
  return ok(out, { in_bytes: text.length, out_chars: out.length });
}
function asciiDecode(text) {
  const g = guard(text); if (g) return g;
  const s = text.trim();
  if (!s) return ok("");
  const tokens = s.split(/[\s,]+/).filter(Boolean);
  const out = [];
  for (const t of tokens) {
    let v;
    if (/^0x[0-9a-fA-F]+$/.test(t)) v = parseInt(t.slice(2), 16);
    else if (/^[0-9]+$/.test(t)) v = parseInt(t, 10);
    else return fail(`「${t}」不是有效的十进制 / 十六进制码点数值`);
    if (v < 0 || v > 127) return fail(`「${t}」超出 ASCII 范围（0–127）`);
    out.push(String.fromCharCode(v));
  }
  const decoded = out.join("");
  return ok(decoded, { in_bytes: s.length, out_chars: decoded.length });
}
function rot13(text) {
  const g = guard(text); if (g) return g;
  let out = "";
  for (const ch of text) {
    const c = ch.charCodeAt(0);
    if (c >= 65 && c <= 90) out += String.fromCharCode(((c - 65 + 13) % 26) + 65);
    else if (c >= 97 && c <= 122) out += String.fromCharCode(((c - 97 + 13) % 26) + 97);
    else out += ch;
  }
  return ok(out, { in_bytes: utf8(text).length, out_chars: out.length });
}
function qpEncode(text, { charset = "utf-8" } = {}) {
  const g = guard(text); if (g) return g;
  let bytes; try { bytes = encodeText(text, charset); } catch (e) { return fail(e.message); }
  let out = "";
  let lineLen = 0;
  const push = (tok) => {
    if (lineLen + tok.length > 75) { out += "=\r\n"; lineLen = 0; }
    out += tok; lineLen += tok.length;
  };
  for (let i = 0; i < bytes.length; i++) {
    const b = bytes[i];
    if (b === 0x0d && bytes[i + 1] === 0x0a) { out += "\r\n"; lineLen = 0; i++; continue; }
    const printable = (b >= 33 && b <= 126 && b !== 61) || b === 32 || b === 9;
    if (printable) {
      if (b === 32 || b === 9) {
        const atEol = i + 1 >= bytes.length || bytes[i + 1] === 0x0d || bytes[i + 1] === 0x0a;
        push(atEol ? "=" + b.toString(16).toUpperCase().padStart(2, "0") : String.fromCharCode(b));
      } else push(String.fromCharCode(b));
    } else {
      push("=" + b.toString(16).toUpperCase().padStart(2, "0"));
    }
  }
  return ok(out, { in_bytes: bytes.length, out_chars: out.length });
}
function qpDecode(text, { charset = "utf-8" } = {}) {
  const g = guard(text); if (g) return g;
  if (!text.trim()) return ok("");
  if (/[^\x00-\x7F]/.test(text)) return fail("QP 解码失败：输入包含非 ASCII 字符");
  const cleaned = text.replace(/=\r?\n/g, "");
  const out = [];
  for (let i = 0; i < cleaned.length; i++) {
    const ch = cleaned[i];
    if (ch === "=") {
      const h = cleaned.substr(i + 1, 2);
      if (!/^[0-9a-fA-F]{2}$/.test(h)) return fail("QP 解码失败：无效的 =XX 序列");
      out.push(parseInt(h, 16)); i += 2;
    } else out.push(ch.charCodeAt(0) & 0xff);
  }
  const bytes = new Uint8Array(out);
  try { return ok(decodeText(bytes, charset), { in_bytes: text.length, out_bytes: bytes.length }); }
  catch { return fail(`解码结果不是有效的 ${charset} 文本`); }
}

/* ---------------- 字符集与 base64 内部工具 ---------------- */
function bytesToB64(bytes) {
  let s = "";
  const CH = 0x8000;
  for (let i = 0; i < bytes.length; i += CH) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  }
  return btoa(s);
}
function unB64(s) {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
function decodeBytes(codecId, text) {
  const compact = stripWs(text);
  try {
    if (codecId === "base64" || codecId === "base64url") {
      if (!compact) return ok(new Uint8Array());
      const urlsafe = codecId === "base64url";
      const allowed = urlsafe ? /^[A-Za-z0-9\-_]+={0,2}$/ : /^[A-Za-z0-9+/]+={0,2}$/;
      if (!allowed.test(compact) || compact.replace(/=/g, "").length % 4 === 1) return fail("Base64 长度或字符不合法");
      let s = compact.replace(/-/g, "+").replace(/_/g, "/");
      while (s.length % 4) s += "=";
      return ok(unB64(s));
    }
    if (codecId === "hex") return ok(unhex(compact.replace(/0x/gi, "")));
    if (codecId === "base32") {
      const r = b32Decode(compact, { charset: "latin-1" });
      if (!r.ok) return r;
      const out = new Uint8Array(r.data.length);
      for (let i = 0; i < r.data.length; i++) out[i] = r.data.charCodeAt(i);
      return ok(out);
    }
    return fail(`不支持字节级解码：${codecId}`);
  } catch (e) { return fail(e.message || "字节解码失败"); }
}
function encodeText(text, charset) {
  const cs = (charset || "utf-8").toLowerCase();
  if (cs === "utf-8" || cs === "utf8") return utf8(text);
  if (cs === "utf-16le" || cs === "utf16le") {
    // 浏览器无 UTF-16LE 编码器：手工逐码元输出（代理对天然正确）
    const out = new Uint8Array(text.length * 2);
    for (let i = 0; i < text.length; i++) {
      const c = text.charCodeAt(i);
      out[i * 2] = c & 0xff; out[i * 2 + 1] = (c >> 8) & 0xff;
    }
    return out;
  }
  if (cs === "latin-1" || cs === "latin1" || cs === "iso-8859-1") {
    const out = new Uint8Array(text.length);
    for (let i = 0; i < text.length; i++) {
      const c = text.charCodeAt(i);
      if (c > 0xff) throw new Error(`文本包含 Latin-1（单字节）范围外的字符（「${text[i]}」），浏览器端无法编码 GBK / Latin-1 之外的扩展字符集`);
      out[i] = c;
    }
    return out;
  }
  // GBK / Big5 等多字节编码：浏览器只有解码器没有编码器（无码表），明确报错
  throw new Error(`浏览器无法「编码」为 ${charset.toUpperCase()}（无编码码表，仅支持解码）。编码请改用 UTF-8 / UTF-16LE / Latin-1`);
}
function decodeText(bytes, charset) {
  const cs = (charset || "utf-8").toLowerCase();
  if (cs === "utf-8" || cs === "utf8") return fromUtf8(bytes);
  if (cs === "utf-16le" || cs === "utf16le") {
    // 原生 TextDecoder("utf-16le") 各内核支持不一，手工解码最稳
    if (bytes.length % 2) throw new Error("UTF-16LE 字节长度必须为偶数");
    let s = "";
    for (let i = 0; i < bytes.length; i += 2) {
      s += String.fromCharCode(bytes[i] | (bytes[i + 1] << 8));
    }
    if (/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(s)) {
      throw new Error("UTF-16LE 包含未配对的代理项");
    }
    return s;
  }
  if (cs === "latin-1" || cs === "latin1" || cs === "iso-8859-1") {
    let s = "";
    for (const b of bytes) s += String.fromCharCode(b);
    return s;
  }
  // GBK / Big5 等：浏览器（Chromium / WebKit / Gecko）原生解码器支持
  try {
    return new TextDecoder(charset, { fatal: true }).decode(bytes);
  } catch (e) {
    if (e.name === "RangeError" || e.name === "TypeError") {
      throw new Error(`不支持的字符集：${charset}`);
    }
    throw new Error(`解码结果不是有效的 ${charset} 文本`);
  }
}

const CODECS = {
  base64: { name: "Base64（标准）", encode: (t) => b64Encode(t), decode: (t) => b64Decode(t) },
  base64url: { name: "Base64 URL Safe", encode: (t) => b64Encode(t, { urlsafe: true }), decode: (t) => b64Decode(t, { urlsafe: true }) },
  base32: { name: "Base32", encode: b32Encode, decode: b32Decode },
  hex: { name: "Base16 / Hex", encode: hexEncode, decode: hexDecode },
  base58: { name: "Base58", encode: b58Encode, decode: b58Decode },
  base62: { name: "Base62", encode: b62Encode, decode: b62Decode },
  url: { name: "URL 编码", encode: urlEncode, decode: urlDecode },
  html: { name: "HTML 实体", encode: htmlEncode, decode: htmlDecode },
  unicode: { name: "Unicode 转义", encode: unicodeEncode, decode: unicodeDecode },
  ascii: { name: "ASCII", encode: asciiEncode, decode: asciiDecode },
  rot13: { name: "ROT13", encode: rot13, decode: rot13 },
  qp: { name: "Quoted-Printable", encode: qpEncode, decode: qpDecode },
};
const CODEC_ORDER = Object.keys(CODECS);
function runCodec(id, direction, text, params = {}) {
  const c = CODECS[id];
  if (!c) return fail(`未知算法：${id}`);
  try { return c[direction](text, params); }
  catch (e) { return fail(`处理失败：${e.message}`); }
}

return { CODECS, CODEC_ORDER, runCodec, decodeBytes, b64Encode, b64Decode, b32Encode, b32Decode, hexEncode, hexDecode, b58Encode, b58Decode, b62Encode, b62Decode, urlEncode, urlDecode, htmlEncode, htmlDecode, unicodeEncode, unicodeDecode, asciiEncode, asciiDecode, rot13, qpEncode, qpDecode, MAX_INPUT_CHARS, B58_B62_MAX_CHARS };
})(globalThis.DT.core);
