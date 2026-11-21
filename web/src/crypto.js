/* crypto.js — 单文件构建用：IIFE 工厂，依赖显式注入，无全局污染 */
globalThis.DT = globalThis.DT || {};
globalThis.DT.crypto = (({ ENV_MAGIC, DEFAULT_ITERATIONS, MIN_ITERATIONS, MAX_ITERATIONS, MAX_DATA_BYTES, ok, fail, concat, rand, hex, unhex, utf8, chacha }) => {
/* 加密 / 解密：与桌面版信封格式完全兼容（DTK1 + salt(16) + nonce/iv + body）。
 * AES-GCM / AES-CBC / ChaCha20-Poly1305 / RSA-OAEP / RSA-PSS 全部走 Web Crypto 原生。
 * AES-ECB 浏览器不提供 —— 明确报错并给出替代建议，绝不静默降级。
 */

const ALGORITHMS = {
  "aes-gcm": { name: "AES-GCM", aead: true, nonceLen: 12, sizes: [128, 192, 256], risk: "ok" },
  "aes-cbc": { name: "AES-CBC", aead: false, ivLen: 16, sizes: [128, 192, 256], risk: "warn" },
  "aes-ecb": { name: "AES-ECB", aead: false, ivLen: 0, sizes: [128, 192, 256], risk: "err", unsupported: true },
  "chacha20-poly1305": { name: "ChaCha20-Poly1305", aead: true, nonceLen: 12, sizes: [256], risk: "ok" },
};
const ALGO_ORDER = ["aes-gcm", "aes-cbc", "aes-ecb", "chacha20-poly1305", "rsa-oaep", "rsa-pss"];

/* ---------------- 密钥 ---------------- */
const clampIter = (n) => {
  const v = Number.isFinite(+n) ? Math.trunc(+n) : DEFAULT_ITERATIONS;
  return Math.max(MIN_ITERATIONS, Math.min(v, MAX_ITERATIONS));
};

async function deriveKey(passphrase, salt, keyBits, iterations = DEFAULT_ITERATIONS) {
  const base = await crypto.subtle.importKey(
    "raw", utf8(passphrase), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt, iterations: clampIter(iterations), hash: "SHA-256" },
    base, keyBits);
  return new Uint8Array(bits);
}

function parseRawKey(raw, keyBytes) {
  const s = (raw || "").trim();
  if (!s) return fail("密钥为空：请输入密钥、粘贴 Hex/Base64 或点击生成随机密钥");
  let key = null;
  const hexNorm = s.replace(/[ :]/g, "").toLowerCase();
  if (/^hex:/i.test(s)) {
    const c = s.slice(4).replace(/[ :]/g, "").toLowerCase();
    if (c.length % 2 || !/^[0-9a-f]*$/.test(c)) return fail("Hex 密钥格式无效：长度必须为偶数且仅含 0–9 A–F");
    key = unhex(c);
  } else if (/^b64:/i.test(s)) {
    try { key = b64ToBytes(s.slice(4)); } catch { return fail("Base64 密钥格式无效"); }
  } else if (hexNorm.length && hexNorm.length % 2 === 0 && /^[0-9a-f]+$/.test(hexNorm)) {
    key = unhex(hexNorm);
  } else {
    try { key = b64ToBytes(s); } catch {
      return fail("无法识别密钥格式：请使用 Hex 或 Base64，或加前缀 hex:/b64: 强制指定");
    }
  }
  if (key.length !== keyBytes) {
    return fail(`密钥长度不正确：当前 ${key.length} 字节，算法需要 ${keyBytes} 字节（${keyBytes * 8} 位）`);
  }
  return ok(key, { key_bytes: key.length });
}
function b64ToBytes(s) {
  const bin = atob(s.replace(/\s+/g, ""));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
function generateRandomKey(keyBytes) {
  if (![16, 24, 32].includes(keyBytes)) return fail("密钥长度必须是 16 / 24 / 32 字节（128 / 192 / 256 位）");
  return ok(hex(rand(keyBytes)), { key_bytes: keyBytes });
}

/* ---------------- 信封 ---------------- */
const packEnvelope = (passMode, salt, nonce, body) =>
  passMode ? concat(ENV_MAGIC, salt, nonce, body) : (nonce.length ? concat(nonce, body) : body);

function unpackEnvelope(data, passMode, nonceLen) {
  if (passMode) {
    if (data.length < 4 + 16 + nonceLen) throw new Error("密文长度不完整（信封格式损坏）");
    for (let i = 0; i < 4; i++) {
      if (data[i] !== ENV_MAGIC[i]) throw new Error("密文缺少 DevToolkit 信封头（DTK1）");
    }
    return { salt: data.slice(4, 20), nonce: data.slice(20, 20 + nonceLen), body: data.slice(20 + nonceLen) };
  }
  if (nonceLen) {
    if (data.length < nonceLen) throw new Error("密文长度不完整（缺少 Nonce / IV）");
    return { salt: new Uint8Array(), nonce: data.slice(0, nonceLen), body: data.slice(nonceLen) };
  }
  return { salt: new Uint8Array(), nonce: new Uint8Array(), body: data };
}

/* ---------------- 对称加解密 ---------------- */
async function aesKey(rawKey, usage) {
  if (![16, 24, 32].includes(rawKey.length)) throw new Error("AES 密钥长度必须是 16 / 24 / 32 字节");
  return crypto.subtle.importKey("raw", rawKey, { name: "AES-GCM" }, false, [usage]);
}

async function encrypt(rawData, cfg) {
  if (rawData == null) return fail("输入为空");
  if (rawData.length > MAX_DATA_BYTES) return fail("输入过大（超过 64 MB 上限），请使用文件处理");
  const algoId = cfg.algorithm || "aes-gcm";
  const info = ALGORITHMS[algoId];
  if (!info) return fail(`对称加密不支持算法：${String(algoId).slice(0, 60)}`);
  if (info.unsupported) {
    return fail("浏览器不支持 AES-ECB（Web Crypto 明确排除该不安全模式）。请改用 AES-GCM（推荐）或 AES-CBC");
  }
  const keyBits = clampInt(cfg.key_size, 256);
  if (info.sizes && !info.sizes.includes(keyBits)) {
    return fail(`${info.name} 密钥长度必须是 ${info.sizes.join(" / ")} 位之一`);
  }
  const keyBytes = keyBits / 8;
  const passMode = (cfg.key_source || "passphrase") !== "raw";
  const iterations = clampIter(cfg.pbkdf2_iterations);

  let key;
  let salt = new Uint8Array();
  if (passMode) {
    if (!cfg.passphrase) return fail("口令为空：请输入口令");
    salt = rand(16);
    try { key = await deriveKey(cfg.passphrase, salt, keyBits, iterations); }
    catch (e) { return fail(`密钥派生失败：${e.message}`); }
  } else {
    const parsed = parseRawKey(cfg.raw_key, keyBytes);
    if (!parsed.ok) return parsed;
    key = parsed.data;
  }

  try {
    let envelope;
    if (algoId === "aes-gcm") {
      const nonce = rand(12);
      const k = await crypto.subtle.importKey("raw", key, { name: "AES-GCM" }, false, ["encrypt"]);
      const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce, tagLength: 128 }, k, rawData));
      envelope = packEnvelope(passMode, salt, nonce, ct);
    } else if (algoId === "chacha20-poly1305") {
      const nonce = rand(12);
      // Edge/Firefox 的 Web Crypto 不支持 ChaCha20-Poly1305：走 RFC 8439 纯 JS 实现
      const ct = chacha.encrypt(key, nonce, rawData);
      envelope = packEnvelope(passMode, salt, nonce, ct);
    } else if (algoId === "aes-cbc") {
      const iv = rand(16);
      const k = await crypto.subtle.importKey("raw", key, { name: "AES-CBC" }, false, ["encrypt"]);
      const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-CBC", iv }, k, pkcs7Pad(rawData, 16)));
      envelope = packEnvelope(passMode, salt, iv, ct);
    } else {
      return fail(`未知算法：${algoId}`);
    }
    return ok(envelope, {
      algorithm: algoId, label: info.name, key_size: keyBits, risk: info.risk,
      iterations: passMode ? iterations : 0,
      in_bytes: rawData.length, out_bytes: envelope.length,
    });
  } catch (e) {
    return fail(`加密失败：${e.message}`);
  }
}

async function decrypt(data, cfg) {
  if (data == null || data.length === 0) return fail("输入为空：请提供待解密的密文");
  if (data.length > MAX_DATA_BYTES) return fail("输入过大（超过 64 MB 上限）");
  const algoId = cfg.algorithm || "aes-gcm";
  const info = ALGORITHMS[algoId];
  if (!info) return fail(`对称解密不支持算法：${String(algoId).slice(0, 60)}`);
  if (info.unsupported) {
    return fail("浏览器不支持 AES-ECB（Web Crypto 明确排除该不安全模式）。请改用 AES-GCM（推荐）或 AES-CBC");
  }
  const keyBits = clampInt(cfg.key_size, 256);
  const keyBytes = keyBits / 8;
  const passMode = (cfg.key_source || "passphrase") !== "raw";
  const nonceLen = info.nonceLen ?? info.ivLen ?? 0;
  const iterations = clampIter(cfg.pbkdf2_iterations);

  let salt, nonce, body, key;
  try {
    ({ salt, nonce, body } = unpackEnvelope(data, passMode, nonceLen));
    if (passMode) {
      if (!cfg.passphrase) return fail("口令为空：请输入加密时使用的口令");
      key = await deriveKey(cfg.passphrase, salt, keyBits, iterations);
    } else {
      const parsed = parseRawKey(cfg.raw_key, keyBytes);
      if (!parsed.ok) return parsed;
      key = parsed.data;
    }
  } catch (e) {
    return fail(e.message);
  }

  try {
    let plain;
    if (algoId === "aes-gcm") {
      if (body.length < 16) return fail("密文不完整：GCM 密文至少包含 16 字节认证 Tag");
      const k = await crypto.subtle.importKey("raw", key, { name: "AES-GCM" }, false, ["decrypt"]);
      try {
        plain = new Uint8Array(await crypto.subtle.decrypt(
          { name: "AES-GCM", iv: nonce, tagLength: 128 }, k, body));
      } catch {
        return fail("解密失败：认证校验未通过（密钥错误或密文已被篡改）");
      }
    } else if (algoId === "chacha20-poly1305") {
      if (body.length < 16) return fail("密文不完整：Poly1305 密文至少包含 16 字节认证 Tag");
      try {
        plain = chacha.decrypt(key, nonce, body);
      } catch {
        return fail("解密失败：认证校验未通过（密钥错误或密文已被篡改）");
      }
    } else if (algoId === "aes-cbc") {
      if (body.length === 0 || body.length % 16) {
        return fail("密文长度不合法：CBC 密文长度必须是 16 字节的整数倍");
      }
      const k = await crypto.subtle.importKey("raw", key, { name: "AES-CBC" }, false, ["decrypt"]);
      try {
        plain = pkcs7Unpad(new Uint8Array(await crypto.subtle.decrypt({ name: "AES-CBC", iv: nonce }, k, body)), 16);
      } catch {
        return fail("解密失败：PKCS#7 填充无效（密钥错误或密文已损坏）");
      }
      if (plain == null) return fail("解密失败：PKCS#7 填充无效（密钥错误或密文已损坏）");
    } else {
      return fail(`未知算法：${algoId}`);
    }
    return ok(plain, {
      algorithm: algoId, label: info.name, key_size: keyBits,
      in_bytes: data.length, out_bytes: plain.length,
    });
  } catch (e) {
    return fail(`解密失败：${e.message}`);
  }
}

function clampInt(v, def) {
  const n = Number.isFinite(+v) ? Math.trunc(+v) : def;
  return n;
}
function pkcs7Pad(bytes, block) {
  const padLen = block - (bytes.length % block);
  const out = new Uint8Array(bytes.length + padLen);
  out.set(bytes);
  out.fill(padLen, bytes.length);
  return out;
}
function pkcs7Unpad(bytes, block) {
  if (!bytes.length) return null;
  const padLen = bytes[bytes.length - 1];
  if (padLen < 1 || padLen > block || padLen > bytes.length) return null;
  for (let i = bytes.length - padLen; i < bytes.length; i++) {
    if (bytes[i] !== padLen) return null;
  }
  return bytes.slice(0, bytes.length - padLen);
}

/* ---------------- RSA ---------------- */
const PEM_LINE = 64;
function pemToDer(pem) {
  const body = (pem || "").replace(/-----[^-]+-----/g, "").replace(/\s+/g, "");
  if (!body) throw new Error("密钥内容为空");
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(body)) throw new Error("密钥不是有效的 Base64 内容");
  return b64ToBytes(body);
}
async function importRsaKey(pem, kind) {
  // kind: 'spki'（公钥）/ 'pkcs8'（私钥）
  const der = pemToDer(pem);
  const isPub = /BEGIN (RSA )?PUBLIC KEY/.test(pem);
  const isPriv = /BEGIN (RSA )?PRIVATE KEY/.test(pem);
  if (kind === "spki" && isPriv) throw new Error("这是私钥：该操作需要公钥（应包含 BEGIN PUBLIC KEY）");
  if (kind === "pkcs8" && isPub) throw new Error("这不是私钥：该操作需要私钥");
  try {
    if (kind === "spki") {
      return await crypto.subtle.importKey("spki", der, { name: "RSA-OAEP", hash: "SHA-256" }, true, ["encrypt"]);
    }
    return await crypto.subtle.importKey("pkcs8", der, { name: "RSA-OAEP", hash: "SHA-256" }, true, ["decrypt"]);
  } catch {
    throw new Error("无法解析 RSA 密钥：请确认是 PEM 格式（PUBLIC KEY / PRIVATE KEY）");
  }
}
async function importRsaPrivateForSign(pem) {
  const der = pemToDer(pem);
  if (/BEGIN (RSA )?PUBLIC KEY/.test(pem)) throw new Error("这不是私钥：签名需要私钥");
  try {
    return await crypto.subtle.importKey("pkcs8", der, { name: "RSA-PSS", hash: "SHA-256" }, true, ["sign"]);
  } catch {
    throw new Error("无法解析 RSA 私钥：请确认是 PEM 格式");
  }
}
async function importRsaPublicForVerify(pem) {
  const der = pemToDer(pem);
  if (/BEGIN (RSA )?PRIVATE KEY/.test(pem)) throw new Error("这是私钥：验签需要公钥");
  try {
    return await crypto.subtle.importKey("spki", der, { name: "RSA-PSS", hash: "SHA-256" }, true, ["verify"]);
  } catch {
    throw new Error("无法解析 RSA 公钥：请确认是 PEM 格式");
  }
}

async function rsaGenerate(bits = 2048) {
  if (![2048, 3072, 4096].includes(bits)) {
    return fail("浏览器端 RSA 密钥长度支持 2048 / 3072 / 4096 位（1024 位已不安全，不提供）");
  }
  try {
    const kp = await crypto.subtle.generateKey(
      { name: "RSA-OAEP", modulusLength: bits, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
      true, ["encrypt", "decrypt"]);
    const spki = new Uint8Array(await crypto.subtle.exportKey("spki", kp.publicKey));
    const pkcs8 = new Uint8Array(await crypto.subtle.exportKey("pkcs8", kp.privateKey));
    return ok({
      public_pem: derToPem(spki, "PUBLIC KEY"),
      private_pem: derToPem(pkcs8, "PRIVATE KEY"),
      bits,
    }, { bits });
  } catch (e) {
    return fail(`密钥生成失败：${e.message}`);
  }
}
function derToPem(der, label) {
  const b64 = btoa(String.fromCharCode.apply(null, der));
  const lines = b64.match(new RegExp(`.{1,${PEM_LINE}}`, "g")) || [];
  return `-----BEGIN ${label}-----\n${lines.join("\n")}\n-----END ${label}-----`;
}

const RSA_MAX = { 2048: 190, 3072: 318, 4096: 446 };
async function rsaEncrypt(pubPem, data) {
  if (!data || !data.length) return fail("输入为空");
  let key;
  try { key = await importRsaKey(pubPem, "spki"); }
  catch (e) { return fail(e.message); }
  const bits = key.algorithm.modulusLength;
  const limit = RSA_MAX[bits] ?? Math.floor(bits / 8) - 66;
  if (data.length > limit) {
    return fail(`明文过长：RSA-OAEP 一次最多加密 ${limit} 字节（${bits} 位密钥）。更大数据请使用 AES 加密后再用 RSA 加密密钥（混合加密）`);
  }
  try {
    const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "RSA-OAEP" }, key, data));
    const envelope = concat(ENV_MAGIC, rand(16), ct);
    return ok(envelope, { label: "RSA-OAEP", bits, in_bytes: data.length, out_bytes: envelope.length });
  } catch (e) {
    return fail(`RSA 加密失败：${e.message}`);
  }
}
async function rsaDecrypt(privPem, data) {
  if (!data || !data.length) return fail("输入为空：请提供待解密的密文");
  let key;
  try { key = await importRsaKey(privPem, "pkcs8"); }
  catch (e) { return fail(e.message); }
  const bits = key.algorithm.modulusLength;
  let ct = data;
  if (data.length >= 4 && data[0] === ENV_MAGIC[0] && data[1] === ENV_MAGIC[1] &&
      data[2] === ENV_MAGIC[2] && data[3] === ENV_MAGIC[3]) {
    ct = data.slice(20);
  }
  if (ct.length !== bits / 8) {
    return fail(`密文长度不正确：当前 ${ct.length} 字节，${bits} 位密钥的密文应为 ${bits / 8} 字节`);
  }
  try {
    const plain = new Uint8Array(await crypto.subtle.decrypt({ name: "RSA-OAEP" }, key, ct));
    return ok(plain, { label: "RSA-OAEP", bits, out_bytes: plain.length });
  } catch {
    return fail("RSA 解密失败：密钥与密文不匹配或密文已损坏");
  }
}

async function rsaSign(privPem, data) {
  if (!data) return fail("输入为空");
  let key;
  try { key = await importRsaPrivateForSign(privPem); }
  catch (e) { return fail(e.message); }
  try {
    const sig = new Uint8Array(await crypto.subtle.sign(
      { name: "RSA-PSS", saltLength: 32 }, key, data));
    return ok(sig, { label: "RSA-PSS-SHA256", bits: key.algorithm.modulusLength, out_bytes: sig.length });
  } catch (e) {
    return fail(`签名失败：${e.message}`);
  }
}
async function rsaVerify(pubPem, data, sig) {
  if (!data || !sig || !sig.length) return fail("请提供原文与签名");
  let key;
  try { key = await importRsaPublicForVerify(pubPem); }
  catch (e) { return fail(e.message); }
  try {
    const good = await crypto.subtle.verify({ name: "RSA-PSS", saltLength: 32 }, key, sig, data);
    return ok(Boolean(good), { label: "RSA-PSS-SHA256" });
  } catch (e) {
    return fail(`验签失败：${e.message}`);
  }
}

const looksLikePrivateKey = (pem) =>
  /BEGIN (RSA |ENCRYPTED )?PRIVATE KEY/.test(pem || "");
const riskOf = (id) => ALGORITHMS[id]?.risk ?? "warn";

return { ALGORITHMS, ALGO_ORDER, encrypt, decrypt, deriveKey, parseRawKey, generateRandomKey, rsaGenerate, rsaEncrypt, rsaDecrypt, rsaSign, rsaVerify, looksLikePrivateKey, riskOf, MIN_ITERATIONS, MAX_ITERATIONS, DEFAULT_ITERATIONS };
})(Object.assign({}, globalThis.DT.core, { chacha: globalThis.DT.chacha }));
