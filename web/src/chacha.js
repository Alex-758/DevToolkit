/* ChaCha20-Poly1305（RFC 8439）纯 JS 实现：Edge 的 Web Crypto 不支持该算法。
 * 输出格式与 Web Crypto 一致：ciphertext || tag(16)，可直接与桌面版互操作。
 */
globalThis.DT = globalThis.DT || {};
globalThis.DT.chacha = (() => {
  const rotl = (v, c) => ((v << c) | (v >>> (32 - c))) >>> 0;

  function chachaBlock(key, counter, nonce) {
    // 初始状态：常量 "expand 32-byte k" + key(8) + counter(1) + nonce(3)
    const st = new Uint32Array(16);
    st[0] = 0x61707865; st[1] = 0x3320646e; st[2] = 0x79622d32; st[3] = 0x6b206574;
    for (let i = 0; i < 8; i++) {
      st[4 + i] = (key[i*4] | (key[i*4+1] << 8) | (key[i*4+2] << 16) | (key[i*4+3] << 24)) >>> 0;
    }
    st[12] = counter >>> 0;
    for (let i = 0; i < 3; i++) {
      st[13 + i] = (nonce[i*4] | (nonce[i*4+1] << 8) | (nonce[i*4+2] << 16) | (nonce[i*4+3] << 24)) >>> 0;
    }
    const w = new Uint32Array(st);
    const qr = (a, b, c, d) => {
      w[a] = (w[a] + w[b]) >>> 0; w[d] = rotl(w[d] ^ w[a], 16);
      w[c] = (w[c] + w[d]) >>> 0; w[b] = rotl(w[b] ^ w[c], 12);
      w[a] = (w[a] + w[b]) >>> 0; w[d] = rotl(w[d] ^ w[a], 8);
      w[c] = (w[c] + w[d]) >>> 0; w[b] = rotl(w[b] ^ w[c], 7);
    };
    for (let i = 0; i < 10; i++) {
      qr(0, 4, 8, 12); qr(1, 5, 9, 13); qr(2, 6, 10, 14); qr(3, 7, 11, 15);
      qr(0, 5, 10, 15); qr(1, 6, 11, 12); qr(2, 7, 8, 13); qr(3, 4, 9, 14);
    }
    const out = new Uint8Array(64);
    for (let i = 0; i < 16; i++) {
      const v = (w[i] + st[i]) >>> 0;
      out[i*4] = v & 0xff; out[i*4+1] = (v >>> 8) & 0xff;
      out[i*4+2] = (v >>> 16) & 0xff; out[i*4+3] = (v >>> 24) & 0xff;
    }
    return out;
  }

  function poly1305(msg, key) {
    // key: 32 字节；r = 前 16 字节（clamp），s = 后 16 字节
    const r = new Uint8Array(16), s = new Uint8Array(16);
    r.set(key.slice(0, 16)); s.set(key.slice(16, 32));
    r[3] &= 15; r[7] &= 15; r[11] &= 15; r[15] &= 15;
    r[4] &= 252; r[8] &= 252; r[12] &= 252;
    const toBig = (bytes) => {
      let n = 0n;
      for (let i = bytes.length - 1; i >= 0; i--) n = (n << 8n) | BigInt(bytes[i]);
      return n;
    };
    const R = toBig(r);
    const S = toBig(s);
    const P = (1n << 130n) - 5n;
    let acc = 0n;
    for (let i = 0; i < msg.length; i += 16) {
      const len = Math.min(16, msg.length - i);
      // 每块后追加 0x01（RFC 8439 §2.5，高位附加而非固定位置）
      const chunk = new Uint8Array(len + 1);
      chunk.set(msg.subarray(i, i + len));
      chunk[len] = 1;
      acc = ((acc + toBig(chunk)) * R) % P;
    }
    acc = (acc + S) & ((1n << 128n) - 1n);
    const out = new Uint8Array(16);
    let v = acc;
    for (let i = 0; i < 16; i++) { out[i] = Number(v & 0xffn); v >>= 8n; }
    return out;
  }

  function aeadMacData(aad, ct) {
    const pad = (n) => (16 - (n % 16)) % 16;
    const total = aad.length + pad(aad.length) + ct.length + pad(ct.length) + 16;
    const out = new Uint8Array(total);
    let p = 0;
    out.set(aad, p); p += aad.length; p += pad(aad.length);
    out.set(ct, p); p += ct.length; p += pad(ct.length);
    const dv = new DataView(out.buffer, p, 16);
    dv.setBigUint64(0, BigInt(aad.length), true);
    dv.setBigUint64(8, BigInt(ct.length), true);
    return out;
  }

  function encrypt(key, nonce, plaintext, aad = new Uint8Array()) {
    const otk = chachaBlock(key, 0, nonce).slice(0, 32);
    const ct = new Uint8Array(plaintext.length);
    for (let off = 0, counter = 1; off < plaintext.length; off += 64, counter++) {
      const ks = chachaBlock(key, counter, nonce);
      for (let i = 0; i < 64 && off + i < plaintext.length; i++) ct[off + i] = plaintext[off + i] ^ ks[i];
    }
    const tag = poly1305(aeadMacData(aad, ct), otk);
    const out = new Uint8Array(ct.length + 16);
    out.set(ct); out.set(tag, ct.length);
    return out;
  }

  function decrypt(key, nonce, ciphertextWithTag, aad = new Uint8Array()) {
    if (ciphertextWithTag.length < 16) throw new Error("密文过短");
    const ct = ciphertextWithTag.slice(0, ciphertextWithTag.length - 16);
    const tag = ciphertextWithTag.slice(ciphertextWithTag.length - 16);
    const otk = chachaBlock(key, 0, nonce).slice(0, 32);
    const expect = poly1305(aeadMacData(aad, ct), otk);
    let diff = 0;
    for (let i = 0; i < 16; i++) diff |= expect[i] ^ tag[i];
    if (diff !== 0) throw new Error("认证失败");
    const pt = new Uint8Array(ct.length);
    for (let off = 0, counter = 1; off < ct.length; off += 64, counter++) {
      const ks = chachaBlock(key, counter, nonce);
      for (let i = 0; i < 64 && off + i < ct.length; i++) pt[off + i] = ct[off + i] ^ ks[i];
    }
    return pt;
  }

  return { encrypt, decrypt, chachaBlock, poly1305 };
})();
