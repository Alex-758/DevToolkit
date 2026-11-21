/* core.js — 单文件构建用：IIFE 工厂，依赖显式注入，无全局污染 */
globalThis.DT = globalThis.DT || {};
globalThis.DT.core = (() => {
/* DevToolkit Web — 核心算法层（纯浏览器，零依赖，零网络）
 * 与桌面版 app/core 对齐：相同算法、相同结果、相同错误语义（返回 {ok,data,error}）。
 */

const ENV_MAGIC = new TextEncoder().encode("DTK1");
const DEFAULT_ITERATIONS = 210000;
const MIN_ITERATIONS = 50000;
const MAX_ITERATIONS = 2000000;
const MAX_DATA_BYTES = 64 * 1024 * 1024;
const ALGO_INFO = {
  "aes-gcm": { name: "AES-GCM", aead: true, nonceLen: 12, sizes: [128, 192, 256], risk: "ok" },
  "aes-cbc": { name: "AES-CBC", aead: false, ivLen: 16, sizes: [128, 192, 256], risk: "warn" },
  "aes-ecb": { name: "AES-ECB", aead: false, ivLen: 0, sizes: [128, 192, 256], risk: "err" },
  "chacha20-poly1305": { name: "ChaCha20-Poly1305", aead: true, nonceLen: 12, sizes: [256], risk: "ok" },
};

const ok = (data, meta = {}) => ({ ok: true, data, meta });
const fail = (error, detail = "") => ({ ok: false, data: null, error, detail });

const subtle = () => {
  if (!globalThis.crypto || !crypto.subtle) {
    throw new Error("当前浏览器不支持 Web Crypto（需 HTTPS 或 localhost 环境）");
  }
  return crypto.subtle;
};

const utf8 = (s) => new TextEncoder().encode(s);
const fromUtf8 = (b) => new TextDecoder("utf-8", { fatal: true }).decode(b);
function hex(bytes) {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
function unhex(s) {
  const c = s.replace(/\s+/g, "");
  if (!/^[0-9a-fA-F]*$/.test(c)) throw new Error("输入包含非十六进制字符");
  if (c.length % 2) throw new Error("十六进制长度必须为偶数");
  const out = new Uint8Array(c.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(c.substr(i * 2, 2), 16);
  return out;
}
function b64encode(bytes) {
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}
function b64decode(s) {
  const bin = atob(s.replace(/\s+/g, ""));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
const rand = (n) => crypto.getRandomValues(new Uint8Array(n));
function concat(...arrs) {
  const total = arrs.reduce((n, a) => n + a.length, 0);
  const out = new Uint8Array(total);
  let p = 0;
  for (const a of arrs) { out.set(a, p); p += a.length; }
  return out;
}
const eqBytes = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);

return { ALGO_INFO, DEFAULT_ITERATIONS, ENV_MAGIC, MAX_DATA_BYTES, MAX_ITERATIONS, MIN_ITERATIONS, b64decode, b64encode, concat, eqBytes, fail, fromUtf8, hex, ok, rand, subtle, unhex, utf8 };
})();
