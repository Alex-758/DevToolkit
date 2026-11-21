/* hash.js — 单文件构建用：IIFE 工厂，依赖显式注入，无全局污染 */
globalThis.DT = globalThis.DT || {};
globalThis.DT.hash = (({ ok, fail, utf8, hex, sha3 }) => {
/* 哈希：与桌面版 10 种算法对齐。
 * SHA-1/224/256/384/512、SHA3-256/512 由 Web Crypto 原生提供；
 * MD5、BLAKE2b-512、BLAKE2s-256 用纯 JS 实现（浏览器不提供）。
 */

const HASH_ALGOS = [
  ["md5", "MD5", "128 位 · 已不安全，仅用于非安全场景校验"],
  ["sha1", "SHA-1", "160 位 · 已不安全，仅用于非安全场景校验"],
  ["sha224", "SHA-224", "224 位"],
  ["sha256", "SHA-256", "256 位 · 推荐"],
  ["sha384", "SHA-384", "384 位"],
  ["sha512", "SHA-512", "512 位 · 推荐"],
  ["sha3_256", "SHA3-256", "256 位"],
  ["sha3_512", "SHA3-512", "512 位"],
  ["blake2b", "BLAKE2b-512", "512 位"],
  ["blake2s", "BLAKE2s-256", "256 位"],
];
const ALGO_IDS = HASH_ALGOS.map((a) => a[0]);
const NATIVE = {
  sha1: "SHA-1", sha224: "SHA-224", sha256: "SHA-256",
  sha384: "SHA-384", sha512: "SHA-512",
};
const MAX_TEXT_CHARS = 8_000_000;

/* ---------------- MD5 ---------------- */
function md5(bytes) {
  const K = new Uint32Array(64);
  for (let i = 0; i < 64; i++) K[i] = Math.floor(Math.abs(Math.sin(i + 1)) * 4294967296) >>> 0;
  const S = [7,12,17,22,7,12,17,22,7,12,17,22,7,12,17,22,
             5,9,14,20,5,9,14,20,5,9,14,20,5,9,14,20,
             4,11,16,23,4,11,16,23,4,11,16,23,4,11,16,23,
             6,10,15,21,6,10,15,21,6,10,15,21,6,10,15,21];
  const len = bytes.length;
  const withPad = new Uint8Array((((len + 8) >>> 6) + 1) * 64);
  withPad.set(bytes);
  withPad[len] = 0x80;
  const bitLenLo = (len * 8) >>> 0;
  const bitLenHi = Math.floor(len / 536870912) >>> 0;
  const dv = new DataView(withPad.buffer);
  dv.setUint32(withPad.length - 8, bitLenLo, true);
  dv.setUint32(withPad.length - 4, bitLenHi, true);
  let a0 = 0x67452301, b0 = 0xefcdab89, c0 = 0x98badcfe, d0 = 0x10325476;
  const M = new Uint32Array(16);
  for (let off = 0; off < withPad.length; off += 64) {
    for (let j = 0; j < 16; j++) M[j] = dv.getUint32(off + j * 4, true);
    let A = a0, B = b0, C = c0, D = d0;
    for (let i = 0; i < 64; i++) {
      let F, g;
      if (i < 16) { F = (B & C) | (~B & D); g = i; }
      else if (i < 32) { F = (D & B) | (~D & C); g = (5 * i + 1) % 16; }
      else if (i < 48) { F = B ^ C ^ D; g = (3 * i + 5) % 16; }
      else { F = C ^ (B | ~D); g = (7 * i) % 16; }
      F = (F + A + K[i] + M[g]) >>> 0;
      A = D; D = C; C = B;
      B = (B + ((F << S[i]) | (F >>> (32 - S[i])))) >>> 0;
    }
    a0 = (a0 + A) >>> 0; b0 = (b0 + B) >>> 0; c0 = (c0 + C) >>> 0; d0 = (d0 + D) >>> 0;
  }
  const out = new Uint8Array(16);
  const ov = new DataView(out.buffer);
  ov.setUint32(0, a0, true); ov.setUint32(4, b0, true);
  ov.setUint32(8, c0, true); ov.setUint32(12, d0, true);
  return out;
}

/* ---------------- BLAKE2b（64 位，BigInt 版） ---------------- */
const M64 = (1n << 64n) - 1n;
const B2B_IV = [
  0x6a09e667f3bcc908n, 0xbb67ae8584caa73bn, 0x3c6ef372fe94f82bn, 0xa54ff53a5f1d36f1n,
  0x510e527fade682d1n, 0x9b05688c2b3e6c1fn, 0x1f83d9abfb41bd6bn, 0x5be0cd19137e2179n,
];
const B2B_SIGMA = [
  [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],
  [14,10,4,8,9,15,13,6,1,12,0,2,11,7,5,3],
  [11,8,12,0,5,2,15,13,10,14,3,6,7,1,9,4],
  [7,9,3,1,13,12,11,14,2,6,5,10,4,0,15,8],
  [9,0,5,7,2,4,10,15,14,1,11,12,6,8,3,13],
  [2,12,6,10,0,11,8,3,4,13,7,5,15,14,1,9],
  [12,5,1,15,14,13,4,10,0,7,6,3,9,2,8,11],
  [13,11,7,14,12,1,3,9,5,0,15,4,8,6,2,10],
  [6,15,14,9,11,3,0,8,12,2,13,7,1,4,10,5],
  [10,2,8,4,7,6,1,5,15,11,9,14,3,12,13,0],
  [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],
  [14,10,4,8,9,15,13,6,1,12,0,2,11,7,5,3],
];
const rotr64 = (x, n) => ((x >> BigInt(n)) | (x << BigInt(64 - n))) & M64;
function blake2b(bytes, outLen = 64) {
  const h = B2B_IV.slice();
  h[0] ^= 0x01010000n ^ BigInt(outLen);
  const BLOCK = 128;
  let t = 0n;
  const compress = (block, last) => {
    const m = [];
    const dv = new DataView(block.buffer, block.byteOffset, block.byteLength);
    for (let i = 0; i < 16; i++) m.push(dv.getBigUint64(i * 8, true));
    const v = h.concat(B2B_IV.slice(0, 8));
    v[12] ^= t & M64;
    v[13] ^= (t >> 64n) & M64;
    if (last) v[14] = ~v[14] & M64;
    const G = (a, b, c, d, x, y) => {
      v[a] = (v[a] + v[b] + x) & M64;
      v[d] = rotr64(v[d] ^ v[a], 32);
      v[c] = (v[c] + v[d]) & M64;
      v[b] = rotr64(v[b] ^ v[c], 24);
      v[a] = (v[a] + v[b] + y) & M64;
      v[d] = rotr64(v[d] ^ v[a], 16);
      v[c] = (v[c] + v[d]) & M64;
      v[b] = rotr64(v[b] ^ v[c], 63);
    };
    for (let r = 0; r < 12; r++) {
      const s = B2B_SIGMA[r];
      G(0, 4, 8, 12, m[s[0]], m[s[1]]);
      G(1, 5, 9, 13, m[s[2]], m[s[3]]);
      G(2, 6, 10, 14, m[s[4]], m[s[5]]);
      G(3, 7, 11, 15, m[s[6]], m[s[7]]);
      G(0, 5, 10, 15, m[s[8]], m[s[9]]);
      G(1, 6, 11, 12, m[s[10]], m[s[11]]);
      G(2, 7, 8, 13, m[s[12]], m[s[13]]);
      G(3, 4, 9, 14, m[s[14]], m[s[15]]);
    }
    for (let i = 0; i < 8; i++) h[i] = h[i] ^ v[i] ^ v[i + 8];
  };
  let pos = 0;
  while (bytes.length - pos > BLOCK) {
    t += BigInt(BLOCK);
    compress(bytes.subarray(pos, pos + BLOCK), false);
    pos += BLOCK;
  }
  const lastBlock = new Uint8Array(BLOCK);
  const rest = bytes.subarray(pos);
  lastBlock.set(rest);
  t += BigInt(rest.length);
  compress(lastBlock, true);
  const out = new Uint8Array(outLen);
  const odv = new DataView(out.buffer);
  for (let i = 0; i < outLen / 8; i++) odv.setBigUint64(i * 8, h[i], true);
  return out;
}

/* ---------------- BLAKE2s（32 位） ---------------- */
const B2S_IV = new Uint32Array([
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
  0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
]);
const rotr32 = (x, n) => ((x >>> n) | (x << (32 - n))) >>> 0;
function blake2s(bytes, outLen = 32) {
  const h = new Uint32Array(B2S_IV);
  h[0] ^= 0x01010000 ^ outLen;
  const BLOCK = 64;
  let t = 0;
  const compress = (block, last) => {
    const m = new Uint32Array(16);
    const dv = new DataView(block.buffer, block.byteOffset, block.byteLength);
    for (let i = 0; i < 16; i++) m[i] = dv.getUint32(i * 4, true);
    const v = new Uint32Array(16);
    v.set(h, 0); v.set(B2S_IV, 8);
    v[12] ^= t >>> 0;
    v[13] ^= Math.floor(t / 4294967296) >>> 0;
    if (last) v[14] = ~v[14] >>> 0;
    const G = (a, b, c, d, x, y) => {
      v[a] = (v[a] + v[b] + x) >>> 0;
      v[d] = rotr32(v[d] ^ v[a], 16);
      v[c] = (v[c] + v[d]) >>> 0;
      v[b] = rotr32(v[b] ^ v[c], 12);
      v[a] = (v[a] + v[b] + y) >>> 0;
      v[d] = rotr32(v[d] ^ v[a], 8);
      v[c] = (v[c] + v[d]) >>> 0;
      v[b] = rotr32(v[b] ^ v[c], 7);
    };
    for (let r = 0; r < 10; r++) {
      const s = B2B_SIGMA[r];
      G(0, 4, 8, 12, m[s[0]], m[s[1]]);
      G(1, 5, 9, 13, m[s[2]], m[s[3]]);
      G(2, 6, 10, 14, m[s[4]], m[s[5]]);
      G(3, 7, 11, 15, m[s[6]], m[s[7]]);
      G(0, 5, 10, 15, m[s[8]], m[s[9]]);
      G(1, 6, 11, 12, m[s[10]], m[s[11]]);
      G(2, 7, 8, 13, m[s[12]], m[s[13]]);
      G(3, 4, 9, 14, m[s[14]], m[s[15]]);
    }
    for (let i = 0; i < 8; i++) h[i] ^= v[i] ^ v[i + 8];
  };
  let pos = 0;
  while (bytes.length - pos > BLOCK) {
    t += BLOCK;
    compress(bytes.subarray(pos, pos + BLOCK), false);
    pos += BLOCK;
  }
  const lastBlock = new Uint8Array(BLOCK);
  const rest = bytes.subarray(pos);
  lastBlock.set(rest);
  t += rest.length;
  compress(lastBlock, true);
  const out = new Uint8Array(outLen);
  const odv = new DataView(out.buffer);
  for (let i = 0; i < outLen / 4; i++) odv.setUint32(i * 4, h[i], true);
  return out;
}

/* ---------------- SHA-224（Web Crypto 对 SHA-224 支持不一致，纯 JS 兜底） ---------------- */
const SHA256_K = new Uint32Array([
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
]);
function sha224(bytes) {
  const H224 = new Uint32Array([
    0xc1059ed8,0x367cd507,0x3070dd17,0xf70e5939,0xffc00b31,0x68581511,0x64f98fa7,0xbefa4fa4,
  ]);
  // 复用 sha256 压缩函数：临时替换初始值
  const h = sha256WithIV(bytes, H224);
  const out = new Uint8Array(28);
  const dv = new DataView(out.buffer);
  for (let i = 0; i < 7; i++) dv.setUint32(i * 4, h[i], false);
  return out;
}
function sha256WithIV(bytes, iv) {
  const len = bytes.length;
  const padLen = (((len + 8) >>> 6) + 1) * 64;
  const buf = new Uint8Array(padLen);
  buf.set(bytes);
  buf[len] = 0x80;
  const dv = new DataView(buf.buffer);
  dv.setUint32(padLen - 8, Math.floor(len / 536870912) >>> 0, false);
  dv.setUint32(padLen - 4, (len * 8) >>> 0, false);
  const h = new Uint32Array(iv);
  const w = new Uint32Array(64);
  const rr = (x, n) => ((x >>> n) | (x << (32 - n))) >>> 0;
  for (let off = 0; off < padLen; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = dv.getUint32(off + i * 4, false);
    for (let i = 16; i < 64; i++) {
      const s0 = (rr(w[i-15],7) ^ rr(w[i-15],18) ^ (w[i-15] >>> 3)) >>> 0;
      const s1 = (rr(w[i-2],17) ^ rr(w[i-2],19) ^ (w[i-2] >>> 10)) >>> 0;
      w[i] = (w[i-16] + s0 + w[i-7] + s1) >>> 0;
    }
    let [a,b,c,d,e,f,g,hh] = h;
    for (let i = 0; i < 64; i++) {
      const S1 = (rr(e,6) ^ rr(e,11) ^ rr(e,25)) >>> 0;
      const ch = ((e & f) ^ (~e & g)) >>> 0;
      const t1 = (hh + S1 + ch + SHA256_K[i] + w[i]) >>> 0;
      const S0 = (rr(a,2) ^ rr(a,13) ^ rr(a,22)) >>> 0;
      const mj = ((a & b) ^ (a & c) ^ (b & c)) >>> 0;
      const t2 = (S0 + mj) >>> 0;
      hh = g; g = f; f = e; e = (d + t1) >>> 0;
      d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    h[0] = (h[0] + a) >>> 0; h[1] = (h[1] + b) >>> 0;
    h[2] = (h[2] + c) >>> 0; h[3] = (h[3] + d) >>> 0;
    h[4] = (h[4] + e) >>> 0; h[5] = (h[5] + f) >>> 0;
    h[6] = (h[6] + g) >>> 0; h[7] = (h[7] + hh) >>> 0;
  }
  return h;
}

/* ---------------- 对外接口 ---------------- */
async function digestOne(algo, bytes) {
  if (algo === "md5") return md5(bytes);
  if (algo === "sha224") return sha224(bytes);
  if (algo === "sha3_256") return sha3.sha3_256(bytes);
  if (algo === "sha3_512") return sha3.sha3_512(bytes);
  if (algo === "blake2b") return blake2b(bytes, 64);
  if (algo === "blake2s") return blake2s(bytes, 32);
  const alg = NATIVE[algo];
  if (!alg) throw new Error(`未知哈希算法：${algo}`);
  return new Uint8Array(await crypto.subtle.digest(alg, bytes));
}

async function textHash(text, algo) {
  if (text == null) return fail("输入为空：请输入待哈希内容");
  if (!ALGO_IDS.includes(algo)) return fail(`未知哈希算法：${algo}`);
  if (text.length > MAX_TEXT_CHARS) return fail("输入过大（超过 8 MB）");
  let bytes;
  try { bytes = utf8(text); } catch { return fail("输入包含无法编码为 UTF-8 的字符"); }
  try {
    const d = await digestOne(algo, bytes);
    return ok(hex(d), { algo, in_bytes: bytes.length });
  } catch (e) {
    return fail(`哈希计算失败：${e.message}`);
  }
}

async function textHashAll(text, algos = ALGO_IDS) {
  if (text == null) return fail("输入为空：请输入待哈希内容");
  if (text.length > MAX_TEXT_CHARS) return fail("输入过大（超过 8 MB）");
  let bytes;
  try { bytes = utf8(text); } catch { return fail("输入包含无法编码为 UTF-8 的字符"); }
  const out = {};
  try {
    for (const algo of algos) {
      if (!ALGO_IDS.includes(algo)) return fail(`未知哈希算法：${algo}`);
      out[algo] = hex(await digestOne(algo, bytes));
    }
  } catch (e) {
    return fail(`哈希计算失败：${e.message}`);
  }
  return ok(out, { in_bytes: bytes.length });
}

async function fileHash(file, algos = ALGO_IDS, onProgress = null) {
  const buf = new Uint8Array(await file.arrayBuffer());
  const out = {};
  try {
    for (let i = 0; i < algos.length; i++) {
      out[algos[i]] = hex(await digestOne(algos[i], buf));
      if (onProgress) onProgress(i + 1, algos.length);
    }
  } catch (e) {
    return fail(`哈希计算失败：${e.message}`);
  }
  return ok(out, { in_bytes: buf.length, path: file.name });
}

function compareHash(a, b) {
  const ca = (a || "").trim().toLowerCase().replace(/\s+/g, "");
  const cb = (b || "").trim().toLowerCase().replace(/\s+/g, "");
  if (!ca || !cb) return fail("请输入两个哈希值进行比较");
  return ok(ca === cb, { a: ca, b: cb });
}

return { HASH_ALGOS, ALGO_IDS, textHash, textHashAll, fileHash, compareHash, MAX_TEXT_CHARS };
})(Object.assign({}, globalThis.DT.core, { sha3: globalThis.DT.sha3 }));
