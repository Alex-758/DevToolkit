/* 自检：验证 4 层算法与桌面版一致。浏览器与 Node 均可运行。
 * 返回 { passed, failed, items }，供 HTML 页内「自检」按钮与构建校验使用。
 */
globalThis.DT = globalThis.DT || {};
globalThis.DT.selftest = async function () {
  const C = globalThis.DT.core, CD = globalThis.DT.codecs, H = globalThis.DT.hash, CR = globalThis.DT.crypto;
  const items = [];
  const t = (name, cond, extra = "") => items.push({ name, pass: !!cond, extra });

  // ---- 编码 ----
  t("b64 编码", CD.b64Encode("abc").data === "YWJj");
  t("b64 解码", CD.b64Decode("YWJj").data === "abc");
  t("b64url 无填充", CD.b64Encode("a\u00ff", { urlsafe: true }).data.indexOf("=") === -1);
  t("b32 编码", CD.b32Encode("abc").data === "MFRGG===");
  t("hex 编码", CD.hexEncode("abc").data === "616263");
  t("hex 解码 0x", CD.hexDecode("0x61 0x62").data === "ab");
  t("b58 往返", CD.b58Decode(CD.b58Encode("hello").data).data === "hello");
  t("b62 往返", CD.b62Decode(CD.b62Encode("hello").data).data === "hello");
  t("url 往返", CD.urlDecode(CD.urlEncode("a b/中").data).data === "a b/中");
  t("html 往返", CD.htmlDecode(CD.htmlEncode("<a>&中").data).data === "<a>&中");
  t("unicode 往返", CD.unicodeDecode(CD.unicodeEncode("中😀").data).data === "中😀");
  t("ascii 往返", CD.asciiDecode(CD.asciiEncode("AB").data).data === "AB");
  t("rot13 对称", CD.rot13(CD.rot13("Hello").data).data === "Hello");
  t("qp 往返", CD.qpDecode(CD.qpEncode("中文 =x").data).data === "中文 =x");
  t("ascii 拒绝宽松数", !CD.asciiDecode("1_0").ok);
  t("b64 拒绝 4n+1", !CD.b64Decode("A").ok);

  // ---- 哈希（Python hashlib 权威值）----
  const V = {
    md5: "900150983cd24fb0d6963f7d28e17f72",
    sha1: "a9993e364706816aba3e25717850c26c9cd0d89d",
    sha224: "23097d223405d8228642a477bda255b32aadbce4bda0b3f7e36c9da7",
    sha256: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    sha512: "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
    sha3_256: "3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532",
    sha3_512: "b751850b1a57168a5693cd924b6b096e08f621827444f70d884f5d0240d2712e10e116e9192af3c91a7ec57647e3934057340b4cf408d5a56592f8274eec53f0",
    blake2b: "ba80a53f981c4d0d6a2797b69f12f6e94c212f14685ac4b74b12bb6fdbffa2d17d87c5392aab792dc252d5de4533cc9518d38aa8dbf1925ab92386edd4009923",
    blake2s: "508c5e8c327c14e2e1a72ba34eeb452f37458b209ed63a294d999b4c86675982",
  };
  for (const [algo, want] of Object.entries(V)) {
    const r = await H.textHash("abc", algo);
    t(`hash ${algo}`, r.ok && r.data === want, r.ok ? (r.data === want ? "" : r.data) : r.error);
  }
  t("hash 全部 10 种", (await H.textHashAll("abc")).ok);

  // ---- 加密 ----
  const DATA = new TextEncoder().encode("roundtrip 你好 😀");
  for (const [algo, bits] of [["aes-gcm", 256], ["aes-cbc", 256], ["aes-gcm", 128]]) {
    const cfg = { algorithm: algo, key_source: "passphrase", passphrase: "pw", key_size: bits };
    const e = await CR.encrypt(DATA, cfg);
    const d = await CR.decrypt(e.data, cfg);
    t(`${algo}-${bits} 往返`, e.ok && d.ok && d.data.length === DATA.length, d.error || e.error || "");
  }
  {
    const cfg = { algorithm: "aes-gcm", key_source: "passphrase", passphrase: "pw", key_size: 256 };
    const e = await CR.encrypt(DATA, cfg);
    const d = await CR.decrypt(e.data, { ...cfg, passphrase: "bad" });
    t("错误口令被拒", !d.ok);
    const bad = new Uint8Array(e.data); bad[bad.length - 1] ^= 1;
    t("篡改密文被拒", !(await CR.decrypt(bad, cfg)).ok);
    const empty = await CR.encrypt(new Uint8Array(0), cfg);
    t("空明文往返", (await CR.decrypt(empty.data, cfg)).ok);
  }
  t("ECB 明确拒绝", !(await CR.encrypt(DATA, { algorithm: "aes-ecb", key_source: "passphrase", passphrase: "pw", key_size: 256 })).ok);
  {
    const cfg = { algorithm: "chacha20-poly1305", key_source: "passphrase", passphrase: "pw", key_size: 256 };
    const e = await CR.encrypt(DATA, cfg);
    const d = await CR.decrypt(e.data, cfg);
    t("chacha20-poly1305 往返", e.ok && d.ok && d.data.length === DATA.length, d.error || e.error || "");
    const bad = new Uint8Array(e.data); bad[bad.length - 1] ^= 1;
    t("chacha 篡改被拒", !(await CR.decrypt(bad, cfg)).ok);
  }

  const failed = items.filter((i) => !i.pass);
  return { passed: items.length - failed.length, failed: failed.length, items };
};
