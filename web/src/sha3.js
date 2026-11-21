/* SHA-3（Keccak-f[1600]）纯 JS 实现：Edge/Firefox 的 Web Crypto 不提供 SHA3。
 * 支持 SHA3-256 / SHA3-512（与 hashlib.sha3_* 一致，padding 0x06）。
 */
globalThis.DT = globalThis.DT || {};
globalThis.DT.sha3 = (() => {
  const RC = [
    [0x00000001, 0x00000000], [0x00008082, 0x00000000], [0x0000808a, 0x80000000],
    [0x80008000, 0x80000000], [0x0000808b, 0x00000000], [0x80000001, 0x00000000],
    [0x80008081, 0x80000000], [0x00008009, 0x80000000], [0x0000008a, 0x00000000],
    [0x00000088, 0x00000000], [0x80008009, 0x00000000], [0x8000000a, 0x00000000],
    [0x8000808b, 0x00000000], [0x0000008b, 0x80000000], [0x00008089, 0x80000000],
    [0x00008003, 0x80000000], [0x00008002, 0x80000000], [0x00000080, 0x80000000],
    [0x0000800a, 0x00000000], [0x8000000a, 0x80000000], [0x80008081, 0x80000000],
    [0x00008080, 0x80000000], [0x80000001, 0x00000000], [0x80008008, 0x80000000],
  ];
  const ROT = [
    [0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56], [27, 20, 39, 8, 14],
  ];
  // 状态用 25 个小端 64 位整数（[lo, hi] 两个 32 位）
  function rotl(lo, hi, n) {
    if (n === 0) return [lo, hi];
    if (n < 32) return [((lo << n) | (hi >>> (32 - n))) >>> 0, ((hi << n) | (lo >>> (32 - n))) >>> 0];
    if (n === 32) return [hi, lo];
    const m = n - 32;
    return [((hi << m) | (lo >>> (32 - m))) >>> 0, ((lo << m) | (hi >>> (32 - m))) >>> 0];
  }
  function keccakF(st) {
    const C = new Array(5), D = new Array(5), B = new Array(25);
    for (let round = 0; round < 24; round++) {
      // theta
      for (let x = 0; x < 5; x++) {
        C[x] = [st[x][0] ^ st[x + 5][0] ^ st[x + 10][0] ^ st[x + 15][0] ^ st[x + 20][0],
                st[x][1] ^ st[x + 5][1] ^ st[x + 10][1] ^ st[x + 15][1] ^ st[x + 20][1]];
      }
      for (let x = 0; x < 5; x++) {
        const nx = (x + 1) % 5, px = (x + 4) % 5;
        const r = rotl(C[nx][0], C[nx][1], 1);
        D[x] = [C[px][0] ^ r[0], C[px][1] ^ r[1]];
      }
      for (let x = 0; x < 5; x++) {
        for (let y = 0; y < 5; y++) {
          const i = x + 5 * y;
          st[i] = [st[i][0] ^ D[x][0], st[i][1] ^ D[x][1]];
        }
      }
      // rho + pi
      for (let x = 0; x < 5; x++) {
        for (let y = 0; y < 5; y++) {
          const i = x + 5 * y;
          const [lo, hi] = rotl(st[i][0], st[i][1], ROT[x][y]);
          const nx = y, ny = (2 * x + 3 * y) % 5;
          B[nx + 5 * ny] = [lo, hi];
        }
      }
      // chi
      for (let x = 0; x < 5; x++) {
        for (let y = 0; y < 5; y++) {
          const i = x + 5 * y;
          const i1 = ((x + 1) % 5) + 5 * y;
          const i2 = ((x + 2) % 5) + 5 * y;
          st[i] = [B[i][0] ^ ((~B[i1][0]) & B[i2][0]) >>> 0,
                   B[i][1] ^ ((~B[i1][1]) & B[i2][1]) >>> 0];
        }
      }
      // iota
      st[0] = [(st[0][0] ^ RC[round][0]) >>> 0, (st[0][1] ^ RC[round][1]) >>> 0];
    }
  }
  function keccak(rateBytes, domainPad, data, outLen) {
    const st = Array.from({ length: 25 }, () => [0, 0]);
    // 填充：data + domain + 10*1
    const padded = new Uint8Array(Math.floor(data.length / rateBytes) * rateBytes + rateBytes);
    padded.set(data);
    padded[data.length] ^= domainPad;
    padded[padded.length - 1] ^= 0x80;
    for (let off = 0; off < padded.length; off += rateBytes) {
      for (let i = 0; i < rateBytes / 8; i++) {
        const p = off + i * 8;
        const lo = (padded[p] | (padded[p+1] << 8) | (padded[p+2] << 16) | (padded[p+3] << 24)) >>> 0;
        const hi = (padded[p+4] | (padded[p+5] << 8) | (padded[p+6] << 16) | (padded[p+7] << 24)) >>> 0;
        st[i] = [(st[i][0] ^ lo) >>> 0, (st[i][1] ^ hi) >>> 0];
      }
      keccakF(st);
    }
    const out = new Uint8Array(outLen);
    let pos = 0, lane = 0;
    while (pos < outLen) {
      for (let i = 0; i < 4 && pos < outLen; i++) {
        out[pos++] = (st[lane][0] >>> (8 * i)) & 0xff;
      }
      for (let i = 0; i < 4 && pos < outLen; i++) {
        out[pos++] = (st[lane][1] >>> (8 * i)) & 0xff;
      }
      lane++;
      if (lane >= rateBytes / 8 && pos < outLen) {
        keccakF(st);
        lane = 0;
      }
    }
    return out;
  }
  return {
    sha3_256: (bytes) => keccak(136, 0x06, bytes, 32),
    sha3_512: (bytes) => keccak(72, 0x06, bytes, 64),
  };
})();
