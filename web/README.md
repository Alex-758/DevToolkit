# DevToolkit Web（浏览器单文件版）

**双击 `dist/DevToolkit.html` 即用** —— 单个 HTML 文件，零依赖、零网络、无需安装。
可在 Windows / macOS / Linux / 平板 / 手机上用任意现代浏览器打开，文件拷到哪里都能跑。

## 为什么是单文件

实测发现：`file://` 协议下浏览器**禁止 ES 模块 `import`**（CORS 策略，origin 为 `null`）。
任何「HTML + 多个 .js」的结构在双击打开时都会加载失败。因此本版把所有 JS / CSS 内联进
一个 HTML —— 这是「不受设备限制、拷了就能用」的唯一可行形态。

## 构建

```bash
python web/build.py
# 产物：web/dist/DevToolkit.html（约 130 KB）
```

构建脚本会校验：占位符已替换、**无任何外部引用**（`http(s)://`、`@import`）——确保完全离线。

## 能力与桌面版的差异（均为浏览器平台限制，会明确提示而非静默失败）

| 功能 | 浏览器版 | 说明 |
|---|---|---|
| 12 种编码解码 | ✅ 全部 | 纯 JS 实现，结果与桌面版一致 |
| 哈希 10 种 | ✅ 全部 | SHA-1/256/384/512 用原生；MD5、SHA-224、SHA3-256/512、BLAKE2b/s 为纯 JS 实现 |
| AES-GCM / AES-CBC | ✅ | 原生 Web Crypto |
| ChaCha20-Poly1305 | ✅ | 纯 JS（RFC 8439，已用官方测试向量验证）——Edge/Firefox 原生不支持 |
| RSA-OAEP / RSA-PSS | ✅ | 原生；密钥 2048 / 3072 / 4096 位 |
| AES-ECB | ❌ | Web Crypto 明确排除该不安全模式；界面给出说明与替代建议 |
| GZIP / ZLIB / DEFLATE | ✅ | 原生 CompressionStream / DecompressionStream |
| ZIP / Brotli / Zstandard / LZ4 | ❌ | 浏览器无原生实现；界面明确提示 |
| 智能解码 | ✅ | 编码 + 压缩多层链路，含压缩炸弹防护 |

**加密信封与桌面版完全兼容**：同为 `DTK1` + salt + nonce + body，双向互解已实测通过。

## 验证

页面内置「自检」按钮（左下角 ⚙ 或「关于软件」页），运行 35 项算法校验：

- 编码 16 项（含拒绝非法输入）
- 哈希 9 项（对照 Python hashlib 权威值）
- 加密 10 项（往返、错误口令、篡改检测、空明文、ECB 拒绝、ChaCha）

开发期另用 Node 与真实 Edge（CDP 驱动）做端到端验证：UI 初始化、自检全过、编码/哈希/
加密/压缩的 UI 往返、主题切换、控制台零报错。

## 隐私

完全离线：不联网、不上传、不收集任何数据。所有计算在本地浏览器完成，关闭标签页即彻底清除
（仅主题偏好写入 localStorage）。
