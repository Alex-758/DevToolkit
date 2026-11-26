/* UI 逻辑：8 个页面的交互与算法调用。所有算法来自 DT.* 命名空间。 */
(() => {
  const { core: C, codecs: CD, hash: H, crypto: CR, compress: CP, smart: SM } = globalThis.DT;
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const status = (msg) => { $("status").textContent = msg; };
  const setChip = (node, text, kind = "info") => {
    node.textContent = text || "";
    node.className = "chip" + (text ? " " + kind : "");
  };
  const enc = (s) => new TextEncoder().encode(s);
  const dec = (b) => new TextDecoder().decode(b);
  const toB64 = (bytes) => {
    let s = "";
    const CH = 0x8000;
    for (let i = 0; i < bytes.length; i += CH) s += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
    return btoa(s);
  };
  const fromB64 = (str) => {
    const bin = atob(str);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  };
  const download = (bytes, name, type = "application/octet-stream") => {
    const url = URL.createObjectURL(new Blob([bytes], { type }));
    const a = document.createElement("a");
    a.href = url; a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  /* ================= 导航与主题 ================= */
  const PAGES = [
    ["encode", "编码解码"], ["crypto", "加密解密"], ["compress", "压缩解压"],
    ["hash", "哈希计算"], ["smart", "智能解码"], ["files", "文件处理"], ["about", "关于软件"],
  ];
  const ICONS = {
    encode: "⟨⟩", crypto: "⚿", compress: "⊟", hash: "#",
    smart: "✧", files: "▤", about: "ⓘ",
  };
  const nav = $("nav");
  PAGES.forEach(([id, label], i) => {
    const b = el("button", null, (ICONS[id] || "•") + " " + label);
    b.dataset.page = id;
    b.onclick = () => go(id);
    nav.appendChild(b);
    if (i === 0) b.setAttribute("aria-current", "page");
  });
  function go(id) {
    document.querySelectorAll(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + id));
    nav.querySelectorAll("button").forEach((b) => {
      if (b.dataset.page === id) b.setAttribute("aria-current", "page");
      else b.removeAttribute("aria-current");
    });
    $("scrollArea").scrollTop = 0;
  }
  const THEME_KEY = "dtweb-theme";
  function applyTheme(t) {
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem(THEME_KEY, t); } catch {}
    status(`主题切换为${t === "light" ? "浅色" : "深色"}`);
  }
  let theme = "dark";
  try { theme = localStorage.getItem(THEME_KEY) || "dark"; } catch {}
  applyTheme(theme);
  $("themeBtn").onclick = () => applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "t") { e.preventDefault(); $("themeBtn").click(); }
    const m = /^([1-7])$/.exec(e.key);
    if ((e.ctrlKey || e.metaKey) && m) { e.preventDefault(); go(PAGES[Number(m[1]) - 1][0]); }
  });

  /* ================= 通用：双向切换 ================= */
  function bindSeg(node, onChange) {
    const btns = [...node.querySelectorAll("button")];
    btns.forEach((b) => b.onclick = () => {
      btns.forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      onChange(b.dataset.dir);
    });
    return () => btns.find((b) => b.getAttribute("aria-pressed") === "true").dataset.dir;
  }

  /* ================= 编码解码 ================= */
  const encIn = $("encIn"), encOut = $("encOut"), encAlgo = $("encAlgo");
  CD.CODEC_ORDER.forEach((id) => {
    const o = el("option", null, CD.CODECS[id].name);
    o.value = id;
    encAlgo.appendChild(o);
  });
  // 字符集：仅字节型编解码器使用（与桌面版 params_schema 对齐）
  const CHARSET_CODECS = new Set(["base64", "base64url", "base32", "hex", "base58", "base62", "qp"]);
  const encCharset = el("select");
  encCharset.id = "encCharset";
  [["utf-8", "UTF-8（默认）"], ["utf-16le", "UTF-16LE"], ["gbk", "GBK（仅解码）"], ["latin-1", "Latin-1"]].forEach(([v, t]) => {
    const o = el("option", null, t); o.value = v; encCharset.appendChild(o);
  });
  const charsetLabel = el("label", "field", "字符集");
  charsetLabel.id = "encCharsetLabel";
  const charsetWrap = el("span");
  charsetWrap.style.cssText = "display:inline-flex;align-items:center;gap:6px;margin:0";
  charsetWrap.appendChild(charsetLabel);
  charsetWrap.appendChild(encCharset);
  $("encHint").parentNode.insertBefore(charsetWrap, $("encHint"));
  encCharset.style.width = "150px";
  function syncCharsetVisibility() {
    const use = CHARSET_CODECS.has(encAlgo.value);
    charsetWrap.style.display = use ? "inline-flex" : "none";
  }
  syncCharsetVisibility();

  const HINTS = {    base64: "每 3 字节映射为 4 字符；标准字母表 A–Z a–z 0–9 + /，= 作为填充。",
    base64url: "使用 - _ 替代 + / 并省略填充，可直接用于 URL 与 JWT。",
    base32: "RFC 4648：字母表 A–Z 2–7，= 填充，常用于 TOTP 与 DNS 记录。",
    hex: "支持大小写、有无空格分隔及 0x 前缀的输入。",
    base58: "Bitcoin 字母表，去掉易混淆的 0 O I l；常用于加密货币地址与 IPFS CID。",
    base62: "字母表 0–9 a–z A–Z，无填充；常用于短链接 ID 与业务编号。",
    url: "UTF-8 百分号编码；解码时自动识别 %20 与 + 两种空格形式。",
    html: "编码 & < > \" ' 及非 ASCII 字符；解码支持命名 / 十进制 / 十六进制实体。",
    unicode: "\\uXXXX 格式；自动处理代理对（emoji 等超出 BMP 的字符）。",
    ascii: "字符与码点互转（十进制或 0x 十六进制）；仅支持 0–127。",
    rot13: "仅作用于 A–Z a–z 26 个字母，其余字符保持不变；编码即解码。",
    qp: "RFC 2045 =XX 十六进制转义，常用于邮件 MIME 正文。",
  };
  function syncEncHint() {
    let h = HINTS[encAlgo.value] || "";
    if (CHARSET_CODECS.has(encAlgo.value)) {
      h += " 字符集：GBK / Big5 仅支持解码（浏览器无编码码表）；编码可用 UTF-8 / UTF-16LE / Latin-1。";
    }
    $("encHint").textContent = h;
  }
  encAlgo.onchange = () => { syncEncHint(); syncCharsetVisibility(); };
  syncEncHint();
  let encDirection = bindSeg($("encDir"), () => { syncCharsetVisibility(); });
  encIn.oninput = () => { $("encInMeta").textContent = `${encIn.value.length.toLocaleString()} 字符`; };
  $("encClear").onclick = () => { encIn.value = ""; encOut.value = ""; encIn.oninput(); setChip($("encChip"), ""); };
  $("encPaste").onclick = async () => {
    try { encIn.value = await navigator.clipboard.readText(); encIn.oninput(); status("已从剪贴板粘贴"); }
    catch { status("浏览器拒绝了剪贴板访问，请手动粘贴（Ctrl+V）"); }
  };
  $("encSwap").onclick = () => {
    const out = encOut.value;
    const input = encIn.value;
    encOut.value = input;
    encIn.value = out;
    encIn.oninput();
    status("已交换输入与输出内容");
  };
  $("encRun").onclick = () => {
    const dir = encDirection();
    const text = encIn.value;
    if (!text.trim()) { setChip($("encChip"), "✕ 输入为空：请输入待处理内容", "err"); return; }
    const t0 = performance.now();
    if ($("encBatch").checked) {
      const lines = text.split("\n").map((l) => l.replace(/\r$/, ""));
      const rows = [];
      let failed = 0;
      lines.forEach((line, i) => {
        if (!line.trim()) return;
        const r = CD.runCodec(encAlgo.value, dir, line, { charset: encCharset.value });
        if (r.ok) rows.push(`${i + 1}  ${r.data}`);
        else { rows.push(`${i + 1}  ✕ ${r.error}`); failed++; }
      });
      encOut.value = rows.join("\n");
      setChip($("encChip"),
        `✓ 批量完成 · ${rows.length} 行` + (failed ? ` · ${failed} 行失败` : "") +
        ` · ${Math.round(performance.now() - t0)} 毫秒`,
        failed ? "warn" : "ok");
    } else {
      const r = CD.runCodec(encAlgo.value, dir, text, { charset: encCharset.value });
      if (!r.ok) { setChip($("encChip"), "✕ " + r.error, "err"); status("执行失败：" + r.error); return; }
      encOut.value = r.data;
      setChip($("encChip"), `✓ ${dir === "encode" ? "编码" : "解码"}成功 · ${Math.round(performance.now() - t0)} 毫秒`, "ok");
    }
    status("处理完成（" + CD.CODECS[encAlgo.value].name + "）");
  };
  $("encCopy").onclick = async () => {
    if (!encOut.value) return status("没有可复制的结果");
    try { await navigator.clipboard.writeText(encOut.value); status(`已复制 ${encOut.value.length.toLocaleString()} 字符`); }
    catch { encOut.select(); document.execCommand("copy"); status("已复制"); }
  };

  /* ================= 加密解密 ================= */
  const cryIn = $("cryIn"), cryOut = $("cryOut"), cryAlgo = $("cryAlgo"), cryParams = $("cryParams");
  const CRY_ALGOS = [
    ["aes-gcm", "AES-256-GCM（推荐）"],
    ["aes-cbc", "AES-CBC（无认证）"],
    ["aes-ecb", "AES-ECB（不安全，浏览器不支持）"],
    ["chacha20-poly1305", "ChaCha20-Poly1305"],
    ["rsa-oaep", "RSA-OAEP 加解密"],
    ["rsa-pss", "RSA-PSS 签名 / 验签"],
  ];
  CRY_ALGOS.forEach(([v, label]) => { const o = el("option", null, label); o.value = v; cryAlgo.appendChild(o); });
  let cryDirection = bindSeg($("cryDir"), () => {});
  cryIn.oninput = () => { $("cryInMeta").textContent = `${cryIn.value.length.toLocaleString()} 字符`; };
  $("cryClear").onclick = () => { cryIn.value = ""; cryOut.value = ""; cryIn.oninput(); setChip($("cryChip"), ""); };

  function fieldRow(labelText, control) {
    const w = el("div", "field-row");
    const l = el("label", "field", labelText);
    w.appendChild(l); w.appendChild(control);
    return w;
  }
  function buildCryParams() {
    cryParams.innerHTML = "";
    $("cryBanner").innerHTML = "";
    const algo = cryAlgo.value;
    if (algo.startsWith("rsa")) {
      const keyBox = el("textarea");
      keyBox.id = "cryRsaKey";
      keyBox.style.minHeight = "96px";
      keyBox.placeholder = algo === "rsa-oaep"
        ? (cryDirection() === "encrypt" ? "-----BEGIN PUBLIC KEY-----（加密需要公钥）" : "-----BEGIN PRIVATE KEY-----（解密需要私钥）")
        : "-----BEGIN PRIVATE KEY-----（签名）或 PUBLIC KEY（验签）";
      const wrap = fieldRow("RSA 密钥（PEM）", keyBox);
      wrap.classList.add("full-width");
      cryParams.appendChild(wrap);
      const row = el("div", "inline-actions full-width");
      if (algo === "rsa-oaep") {
        const gen = el("button", "btn small", "生成 2048 位密钥对");
        gen.onclick = async () => {
          gen.disabled = true; gen.textContent = "生成中…";
          const r = await CR.rsaGenerate(2048);
          gen.disabled = false; gen.textContent = "生成 2048 位密钥对";
          if (!r.ok) return setChip($("cryChip"), "✕ " + r.error, "err");
          keyBox.value = cryDirection() === "encrypt" ? r.data.public_pem : r.data.private_pem;
          setChip($("cryChip"), "✓ 已生成密钥（请妥善保存私钥）", "ok");
        };
        row.appendChild(gen);
        const imp = el("button", "btn small", "导入密钥文件");
        const fileInput = document.createElement("input");
        fileInput.type = "file"; fileInput.accept = ".pem,.key,.txt"; fileInput.style.display = "none";
        imp.onclick = () => fileInput.click();
        fileInput.onchange = async () => {
          const f = fileInput.files[0];
          if (f) { keyBox.value = await f.text(); status("已导入 " + f.name); }
        };
        row.appendChild(imp); row.appendChild(fileInput);
      }
      cryParams.appendChild(row);
      $("cryHint").textContent = algo === "rsa-oaep"
        ? "RSA-OAEP 一次最多加密 190 字节（2048 位密钥）；更大数据请使用 AES 加密后再用 RSA 加密密钥。"
        : "使用 RSA-PSS + SHA-256 签名，输出 Base64 签名值。";
      $("cryBanner").innerHTML = '<div class="banner info mt8">RSA-PSS 使用 SHA-256 与 32 字节盐长度，与桌面版一致。</div>';
      return;
    }
    // ---- 对称 ----
    const info = CR.ALGORITHMS[algo];
    const srcSel = el("select");
    [["passphrase", "口令 + PBKDF2 派生（推荐）"], ["raw", "原始密钥（Hex / Base64）"]].forEach(([v, t]) => {
      const o = el("option", null, t); o.value = v; srcSel.appendChild(o);
    });
    const sizeSel = el("select");
    (info.sizes || [256]).forEach((b) => {
      const o = el("option", null, `${b} 位（AES-${b}）`); o.value = String(b); sizeSel.appendChild(o);
    });
    sizeSel.value = String((info.sizes || [256]).slice(-1)[0]);
    if ((info.sizes || []).length < 2) sizeSel.disabled = true;

    const passInput = document.createElement("input");
    passInput.type = "password"; passInput.placeholder = "输入口令（不保存）";
    const rawInput = document.createElement("input");
    rawInput.type = "text"; rawInput.placeholder = "Hex 或 Base64 密钥（如 hex:9f86d081…）";

    cryParams.appendChild(fieldRow("密钥来源", srcSel));
    cryParams.appendChild(fieldRow("密钥长度", sizeSel));
    const genBtn = el("button", "btn small", "生成随机密钥");
    // 「生成随机密钥」紧跟原始密钥输入框（同一字段容器内），避免孤立成行
    const rawField = el("div", "field-row");
    rawField.appendChild(el("label", "field", "原始密钥"));
    const rawLine = el("div", "inline-actions");
    rawLine.appendChild(rawInput);
    rawLine.appendChild(genBtn);
    rawField.appendChild(rawLine);
    const passWrap = fieldRow("口令", passInput);
    const rawWrap = rawField;
    cryParams.appendChild(passWrap);
    cryParams.appendChild(rawWrap);
    genBtn.onclick = () => {
      const bits = Number(sizeSel.value) || 256;
      const r = CR.generateRandomKey(bits / 8);
      if (!r.ok) return setChip($("cryChip"), "✕ " + r.error, "err");
      srcSel.value = "raw";
      rawInput.value = "hex:" + r.data;
      toggleSrc();
      status(`已生成 ${bits} 位随机密钥（仅显示一次，请妥善保存）`);
    };

    const iterInput = document.createElement("input");
    iterInput.type = "number"; iterInput.min = String(CR.MIN_ITERATIONS);
    iterInput.max = String(CR.MAX_ITERATIONS); iterInput.step = "10000";
    iterInput.value = String(CR.DEFAULT_ITERATIONS);
    const encSel = el("select");
    [["base64", "Base64"], ["hex", "Hex"]].forEach(([v, t]) => { const o = el("option", null, t); o.value = v; encSel.appendChild(o); });
    const iterWrap = fieldRow("PBKDF2 迭代", iterInput);
    cryParams.appendChild(iterWrap);
    cryParams.appendChild(fieldRow("密文输出", encSel));

    function toggleSrc() {
      const raw = srcSel.value === "raw";
      passWrap.style.display = raw ? "none" : "";
      rawWrap.style.display = raw ? "" : "none";
      iterWrap.style.display = raw ? "none" : "";
    }
    srcSel.onchange = toggleSrc;
    toggleSrc();

    $("cryHint").textContent = "Nonce / IV 每次加密自动随机生成；AEAD 认证 Tag 附加在密文尾部。";
    const risk = CR.riskOf(algo);
    if (risk === "err") {
      $("cryBanner").innerHTML = '<div class="banner err mt8">⚠ ECB 模式不安全：相同明文块产生相同密文，泄露数据模式，且浏览器 Web Crypto 不提供该模式。</div>';
    } else if (risk === "warn") {
      $("cryBanner").innerHTML = '<div class="banner warn mt8">⚠ CBC 模式无认证能力：密文可被篡改而不被发现，建议改用 GCM。</div>';
    } else {
      $("cryBanner").innerHTML = '<div class="banner mt8">✓ 认证加密（AEAD）：密文被篡改时解密将直接失败，推荐日常使用。</div>';
    }
    // 暴露给执行函数
    cryParams._state = { srcSel, sizeSel, passInput, rawInput, iterInput, encSel };
  }
  cryAlgo.onchange = buildCryParams;
  buildCryParams();

  $("cryRun").onclick = async () => {
    const algo = cryAlgo.value;
    const dir = cryDirection();
    const text = cryIn.value;
    if (!text.trim()) { setChip($("cryChip"), "✕ 输入为空：请输入待处理内容", "err"); return; }
    const t0 = performance.now();
    let result;
    if (algo.startsWith("rsa")) {
      const keyText = $("cryRsaKey")?.value || "";
      if (!keyText.trim()) { setChip($("cryChip"), "✕ 请先粘贴或生成 RSA 密钥", "err"); return; }
      if (algo === "rsa-oaep") {
        if (dir === "encrypt") {
          result = await CR.rsaEncrypt(keyText, enc(text));
          if (result.ok) cryOut.value = toB64(result.data);
        } else {
          let raw;
          try { raw = fromB64(text.replace(/\s+/g, "")); }
          catch { result = { ok: false, error: "密文不是有效的 Base64" }; }
          if (!result) {
            result = await CR.rsaDecrypt(keyText, raw);
            if (result.ok) cryOut.value = safeText(result.data);
          }
        }
      } else {
        if (dir === "encrypt") {
          result = await CR.rsaSign(keyText, enc(text));
          if (result.ok) cryOut.value = toB64(result.data);
        } else {
          const [msg, sigB64] = text.split(/\n-{3,}\n/);
          if (!sigB64) { setChip($("cryChip"), "✕ 验签需要「原文」与「签名 Base64」，用一行 --- 分隔", "err"); return; }
          let sig;
          try { sig = fromB64(sigB64.trim()); }
          catch { setChip($("cryChip"), "✕ 签名不是有效的 Base64", "err"); return; }
          result = await CR.rsaVerify(keyText, enc(msg), sig);
          if (result.ok) cryOut.value = result.data ? "✓ 验签通过：签名与原文匹配" : "✕ 验签失败：签名不匹配";
        }
      }
    } else {
      const S = cryParams._state;
      const cfg = {
        algorithm: algo,
        key_size: Number(S.sizeSel.value) || 256,
        key_source: S.srcSel.value,
        passphrase: S.passInput.value,
        raw_key: S.rawInput.value,
        pbkdf2_iterations: Number(S.iterInput.value) || CR.DEFAULT_ITERATIONS,
      };
      if (dir === "encrypt") {
        result = await CR.encrypt(enc(text), cfg);
        if (result.ok) cryOut.value = S.encSel.value === "hex" ? hexOf(result.data) : toB64(result.data);
      } else {
        let data;
        try {
          data = S.encSel.value === "hex" ? unhexOf(text) : fromB64(text.replace(/\s+/g, ""));
        } catch {
          setChip($("cryChip"), "✕ 密文格式与所选「密文输出」不一致（Base64 / Hex）", "err");
          return;
        }
        result = await CR.decrypt(data, cfg);
        if (result.ok) cryOut.value = safeText(result.data);
      }
    }
    if (!result || !result.ok) {
      setChip($("cryChip"), "✕ " + (result?.error || "处理失败"), "err");
      status("失败：" + (result?.error || ""));
      return;
    }
    setChip($("cryChip"), `✓ 处理成功 · ${Math.round(performance.now() - t0)} 毫秒`, "ok");
    status("处理完成");
  };
  function hexOf(bytes) { return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join(""); }
  function unhexOf(s) {
    const c = s.replace(/\s+/g, "").replace(/0x/gi, "");
    if (!/^[0-9a-fA-F]*$/.test(c) || c.length % 2) throw new Error("bad hex");
    const out = new Uint8Array(c.length / 2);
    for (let i = 0; i < out.length; i++) out[i] = parseInt(c.substr(i * 2, 2), 16);
    return out;
  }
  function safeText(bytes) {
    try { return new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
    catch {
      return `[二进制结果 ${bytes.length.toLocaleString()} 字节]\n${hexOf(bytes.slice(0, 96)).replace(/(..)/g, "$1 ").toUpperCase()}\n\n请点击「复制结果」或改用文件处理页导出。`;
    }
  }
  $("cryCopy").onclick = async () => {
    if (!cryOut.value) return status("没有可复制的结果");
    try { await navigator.clipboard.writeText(cryOut.value); status("已复制结果"); }
    catch { cryOut.select(); document.execCommand("copy"); }
  };

  /* ================= 压缩解压 ================= */
  const cpIn = $("cpIn"), cpOut = $("cpOut");
  [["gzip", "GZIP"], ["zlib", "ZLIB"], ["deflate", "DEFLATE（裸流）"]].forEach(([v, t]) => {
    const o = el("option", null, t); o.value = v; $("cpFmt").appendChild(o);
  });
  let cpDirection = bindSeg($("cpDir"), () => {});
  cpIn.oninput = () => { $("cpInMeta").textContent = `${cpIn.value.length.toLocaleString()} 字符`; };
  $("cpClear").onclick = () => { cpIn.value = ""; cpOut.value = ""; cpIn.oninput(); setChip($("cpChip"), ""); };
  $("cpRun").onclick = async () => {
    const text = cpIn.value;
    if (!text.trim()) { setChip($("cpChip"), "✕ 输入为空", "err"); return; }
    const t0 = performance.now();
    let result;
    if (cpDirection() === "compress") {
      result = await CP.compressBytes(enc(text), $("cpFmt").value);
      if (result.ok) {
        cpOut.value = $("cpB64").checked ? toB64(result.data) : hexOf(result.data).replace(/(..)/g, "$1 ").toUpperCase();
        setChip($("cpChip"),
          `✓ 压缩成功 · ${result.meta.in_bytes.toLocaleString()} B → ${result.meta.out_bytes.toLocaleString()} B · ${Math.round(performance.now() - t0)} 毫秒`, "ok");
      }
    } else {
      let data = null;
      const compact = text.replace(/\s+/g, "");
      // 自动识别 Base64 / Hex
      if (/^[0-9a-fA-F]+$/.test(compact) && compact.length % 2 === 0 && compact.length >= 16) {
        try { data = unhexOf(compact); } catch {}
      }
      if (!data) { try { data = fromB64(compact); } catch {} }
      if (!data) data = enc(text);
      result = await CP.decompressBytes(data, $("cpFmt").value, CP.DEFAULT_CAP_MB);
      if (result.ok) {
        cpOut.value = safeText(result.data);
        setChip($("cpChip"),
          `✓ 解压成功 · ${result.meta.in_bytes.toLocaleString()} B → ${result.meta.out_bytes.toLocaleString()} B · ${Math.round(performance.now() - t0)} 毫秒`, "ok");
      }
    }
    if (!result.ok) { setChip($("cpChip"), "✕ " + result.error, "err"); status("失败：" + result.error); }
    else status("处理完成");
  };
  $("cpCopy").onclick = async () => {
    if (!cpOut.value) return status("没有可复制的结果");
    try { await navigator.clipboard.writeText(cpOut.value); status("已复制结果"); }
    catch { cpOut.select(); document.execCommand("copy"); }
  };

  /* ================= 哈希 ================= */
  const hsIn = $("hsIn"), hsList = $("hsList");
  const hsInputs = {};
  H.HASH_ALGOS.forEach(([id, name]) => {
    const row = el("div", "hash-row");
    row.appendChild(el("span", "name", name));
    const inp = document.createElement("input");
    inp.readOnly = true; inp.placeholder = "—";
    row.appendChild(inp);
    const copy = el("button", "btn small", "复制");
    copy.onclick = async () => {
      if (!inp.value) return;
      try { await navigator.clipboard.writeText(inp.value); status(`已复制 ${name}`); }
      catch { inp.select(); document.execCommand("copy"); }
    };
    row.appendChild(copy);
    hsList.appendChild(row);
    hsInputs[id] = inp;
  });
  let hashTimer = null;
  async function recomputeHashes() {
    const text = hsIn.value;
    $("hsInMeta").textContent = `${text.length.toLocaleString()} 字符`;
    const t0 = performance.now();
    const r = await H.textHashAll(text);
    if (!r.ok) {
      Object.values(hsInputs).forEach((i) => { i.value = ""; });
      setChip($("hsChip"), "✕ " + r.error, "err");
      return;
    }
    for (const [id, inp] of Object.entries(hsInputs)) inp.value = r.data[id] || "";
    setChip($("hsChip"), `✓ 已计算 ${Object.keys(r.data).length} 种 · ${text.length.toLocaleString()} 字符 · ${Math.round(performance.now() - t0)} 毫秒`, "ok");
  }
  hsIn.oninput = () => {
    $("hsInMeta").textContent = `${hsIn.value.length.toLocaleString()} 字符`;
    clearTimeout(hashTimer);
    hashTimer = setTimeout(recomputeHashes, 300);
  };
  $("hsClear").onclick = () => { hsIn.value = ""; hsIn.oninput(); };
  $("hsFileBtn").onclick = () => $("hsFile").click();
  $("hsFile").onchange = async () => {
    const f = $("hsFile").files[0];
    if (!f) return;
    setChip($("hsChip"), "… 正在计算文件哈希", "info");
    const r = await H.fileHash(f, ["sha256", "md5", "sha1"]);
    if (!r.ok) { setChip($("hsChip"), "✕ " + r.error, "err"); return; }
    Object.entries(hsInputs).forEach(([id, inp]) => { inp.value = r.data[id] || "—"; });
    setChip($("hsChip"), `✓ ${f.name} · ${r.meta.in_bytes.toLocaleString()} 字节`, "ok");
    status("文件哈希计算完成");
  };
  $("hsCopyAll").onclick = async () => {
    const lines = H.HASH_ALGOS.filter(([id]) => hsInputs[id].value).map(([id, name]) => `${name}: ${hsInputs[id].value}`);
    if (!lines.length) return status("没有可复制的结果");
    try { await navigator.clipboard.writeText(lines.join("\n")); status("已复制全部哈希"); }
    catch { status("复制失败"); }
  };
  function cmpUpdate() {
    const r = H.compareHash($("hsCmpA").value, $("hsCmpB").value);
    if (!r.ok) return setChip($("hsCmpChip"), r.error, "info");
    setChip($("hsCmpChip"), r.data ? "✓ 两个哈希值相同" : "✕ 两个哈希值不同", r.data ? "ok" : "err");
  }
  $("hsCmpA").oninput = cmpUpdate;
  $("hsCmpB").oninput = cmpUpdate;
  hsIn.value = "";
  recomputeHashes();

  /* ================= 智能解码 ================= */
  for (let i = 1; i <= 10; i++) {
    const o = el("option", null, String(i)); o.value = String(i);
    if (i === 5) o.selected = true;
    $("smLayers").appendChild(o);
  }
  $("smIn").oninput = () => { $("smInMeta").textContent = `${$("smIn").value.length.toLocaleString()} 字符`; };
  $("smClear").onclick = () => {
    $("smIn").value = ""; $("smOut").value = ""; $("smSteps").innerHTML = "";
    $("smChain").textContent = ""; setChip($("smChip"), ""); $("smIn").oninput();
  };
  $("smRun").onclick = async () => {
    const text = $("smIn").value;
    if (!text.trim()) { setChip($("smChip"), "✕ 请先输入待解码内容", "err"); return; }
    $("smRun").disabled = true; $("smRun").textContent = "分析中…";
    setChip($("smChip"), "… 正在分析", "info");
    const r = await SM(text, Number($("smLayers").value), CP.DEFAULT_CAP_MB);
    $("smRun").disabled = false; $("smRun").textContent = "开始分析";
    if (!r.ok) { setChip($("smChip"), "✕ " + r.error, "err"); return; }
    const d = r.data;
    $("smOut").value = d.finalText;
    $("smChain").textContent = "链路：" + d.chain + " · " + r.meta.note;
    setChip($("smChip"), `✓ 完成 · ${d.layersUsed} 层`, "ok");
    const box = $("smSteps");
    box.innerHTML = "";
    d.steps.forEach((s) => {
      const w = el("div", "step");
      const head = el("div", "step-head");
      head.appendChild(el("span", "step-idx", "第 " + s.index + " 层"));
      head.appendChild(el("span", "step-action", s.action));
      head.appendChild(el("span", "step-detail", s.detail));
      w.appendChild(head);
      const p1 = el("div", "step-preview", `输入（${s.beforeSize}）：${s.beforePreview}`);
      const p2 = el("div", "step-preview", `输出（${s.afterSize}）：${s.afterPreview}`);
      w.appendChild(p1); w.appendChild(p2);
      box.appendChild(w);
    });
    status(`智能解码完成，共 ${d.layersUsed} 层`);
  };
  $("smCopy").onclick = async () => {
    if (!$("smOut").value) return status("没有可复制的结果");
    try { await navigator.clipboard.writeText($("smOut").value); status("已复制结果"); }
    catch { $("smOut").select(); document.execCommand("copy"); }
  };

  /* ================= 文件处理 ================= */
  let pickedFile = null;
  let saveBytes = null, saveName = "";
  $("flPick").onclick = () => $("flFile").click();
  $("flFile").onchange = () => {
    pickedFile = $("flFile").files[0] || null;
    if (!pickedFile) return;
    $("flMeta").textContent = `${pickedFile.name} · ${pickedFile.size.toLocaleString()} 字节`;
    $("flRun").disabled = false;
  };
  $("flRun").onclick = async () => {
    if (!pickedFile) return;
    $("flRun").disabled = true; $("flRun").textContent = "处理中…";
    setChip($("flChip"), "… 正在处理", "info");
    try {
      const buf = new Uint8Array(await pickedFile.arrayBuffer());
      const op = $("flOp").value;
      saveBytes = null; saveName = "";
      if (op === "base64") {
        $("flOut").value = toB64(buf);
        setChip($("flChip"), `✓ Base64 编码 · ${buf.length.toLocaleString()} B → ${$("flOut").value.length.toLocaleString()} 字符`, "ok");
      } else if (op === "hex") {
        $("flOut").value = hexOf(buf);
        setChip($("flChip"), `✓ Hex 编码 · ${buf.length.toLocaleString()} B → ${$("flOut").value.length.toLocaleString()} 字符`, "ok");
      } else if (op === "hash") {
        const r = await H.fileHash(pickedFile, ["sha256", "md5", "sha1"]);
        if (!r.ok) throw new Error(r.error);
        $("flOut").value = ["sha256", "md5", "sha1"].map((a) => `${a.toUpperCase()}: ${r.data[a]}`).join("\n");
        setChip($("flChip"), `✓ 文件哈希 · ${buf.length.toLocaleString()} 字节`, "ok");
      } else if (op === "gzip") {
        const r = await CP.compressBytes(buf, "gzip");
        if (!r.ok) throw new Error(r.error);
        saveBytes = r.data; saveName = pickedFile.name + ".gz";
        $("flOut").value = `[GZIP 压缩结果 ${r.data.length.toLocaleString()} 字节]\n源文件 ${buf.length.toLocaleString()} 字节\n\n点击「保存结果」导出 ${saveName}`;
        setChip($("flChip"), `✓ GZIP 压缩 · ${buf.length.toLocaleString()} B → ${r.data.length.toLocaleString()} B`, "ok");
      } else {
        const fmt = CP.sniff(buf) || "gzip";
        const r = await CP.decompressBytes(buf, fmt, CP.DEFAULT_CAP_MB);
        if (!r.ok) throw new Error(r.error);
        $("flOut").value = safeText(r.data);
        setChip($("flChip"), `✓ ${CP.FORMAT_NAMES[fmt]} 解压 · ${buf.length.toLocaleString()} B → ${r.data.length.toLocaleString()} B`, "ok");
      }
      $("flSave").disabled = !saveBytes;
      status("文件处理完成");
    } catch (e) {
      setChip($("flChip"), "✕ " + e.message, "err");
      status("失败：" + e.message);
    } finally {
      $("flRun").disabled = false; $("flRun").textContent = "开始处理";
    }
  };
  $("flCopy").onclick = async () => {
    if (!$("flOut").value) return status("没有可复制的结果");
    try { await navigator.clipboard.writeText($("flOut").value); status("已复制结果"); }
    catch { $("flOut").select(); document.execCommand("copy"); }
  };
  $("flSave").onclick = () => {
    if (!saveBytes) return;
    download(saveBytes, saveName || "output.bin");
    status("已导出 " + saveName);
  };

  /* ================= 关于 / 自检 ================= */
  const VERSION = "1.2.1";
  $("aboutVer").textContent = "v" + VERSION + " · 单文件离线版";
  $("verLabel").textContent = "Web v" + VERSION;
  async function runSelfTest(chipNode, detailNode) {
    setChip(chipNode, "… 正在自检", "info");
    if (detailNode) detailNode.textContent = "";
    const t0 = performance.now();
    const r = await globalThis.DT.selftest();
    const ms = Math.round(performance.now() - t0);
    setChip(chipNode, r.failed === 0 ? `✓ 自检通过 ${r.passed}/${r.passed} · ${ms} 毫秒` : `✕ ${r.failed} 项失败`, r.failed === 0 ? "ok" : "err");
    if (detailNode) {
      detailNode.textContent = r.failed === 0
        ? `全部 ${r.passed} 项算法校验通过（编码 25 项 · 哈希 10 项 · 压缩/智能解码 3 项 · 加密 9 项）`
        : r.items.filter((i) => !i.pass).map((i) => `${i.name}: ${i.extra}`).join("；");
    }
    return r;
  }
  $("selfTestBtn").onclick = async () => {
    status("正在运行自检…");
    const r = await runSelfTest($("aboutTestChip"), $("aboutTestDetail"));
    go("about");
    status(r.failed === 0 ? `自检通过：${r.passed} 项全部正常` : `自检发现 ${r.failed} 项异常`);
  };
  $("aboutSelfTest").onclick = () => runSelfTest($("aboutTestChip"), $("aboutTestDetail"));

  /* ================= 初始化 ================= */
  if (!CP.supportsCompression) {
    $("cpRun").disabled = true;
    setChip($("cpChip"), "当前浏览器不支持 CompressionStream", "err");
  }
  // 能力检测：Web Crypto 不可用时全局明示（老内核 / 特殊打开方式常见），
  // 绝不静默失败——用户需要知道为什么加密点不动
  if (!globalThis.crypto || !crypto.subtle) {
    const warn = el("div", "banner err");
    warn.style.margin = "0 0 12px";
    warn.textContent =
      "⚠ 当前浏览器环境不可用 Web Crypto：所有加密/解密与 SHA 系列哈希将失败" +
      "（MD5 / BLAKE2 纯 JS 实现仍可用）。常见原因：浏览器内核过旧，或通过受限方式打开本地文件。" +
      "请改用新版 Chrome / Edge / Firefox / Safari，或将本文件上传到 HTTPS 网页后通过网址访问。";
    $("scrollArea").prepend(warn);
    $("cryRun").disabled = true;
    status("⚠ Web Crypto 不可用：加密功能已禁用");
  }
  status("就绪 · 完全离线运行 · 算法自检可通过左下角 ⚙ 运行");
  $("statusRight").textContent = `UTF-8 · 离线模式 · Web v${VERSION}`;
  window.__dtReady = true;
})();
