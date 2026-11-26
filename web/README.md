# DevToolkit Web（浏览器单文件版）

**双击 `dist/DevToolkit.html` 即用** —— 单个 HTML 文件，零依赖、零网络、无需安装。
可在 Windows / macOS / Linux / 平板 / 手机上用任意现代浏览器打开，文件拷到哪里都能跑。

## 多设备适配（安卓 / 鸿蒙 / iOS / 平板 / 桌面）

- **窄屏（≤700px，手机竖屏）**：侧边栏自动转为顶部栏（品牌 + 主题/自检一行，导航横向滑动一行），主区全宽
- **横屏矮窗（≤520px 高）**：侧边栏导航改双列网格，压低高度
- **触屏设备（pointer: coarse）**：增大点按目标；输入框字号提到 16px——iOS Safari 对 <16px 的输入框聚焦时会强制放大页面
- **动态视口**：`100dvh` 跟随 iOS 地址栏收展；`viewport-fit=cover` + `env(safe-area-inset-*)` 适配刘海/底部横条
- **平台差异统一处理**：tap-highlight 去除、`text-size-adjust`、`touch-action: manipulation`
- 已用 8 种视口（Android 360/412、iPhone 390/375、横屏 844×390、iPad 820/1024、桌面 1280）× 7 页自动化验证横向零溢出

## 字符集支持（Web 版新增）

编码页新增字符集下拉，覆盖能力与桌面版的差异（浏览器平台限制，均明确提示）：

| 字符集 | 编码 | 解码 | 说明 |
|---|---|---|---|
| UTF-8 | ✅ 原生 | ✅ 原生 | 默认 |
| UTF-16LE | ✅ 纯 JS | ✅ 纯 JS | 浏览器无该标签的原生编码器 |
| Latin-1 | ✅ 纯 JS | ✅ 纯 JS | 超出 0xFF 的字符明确报错 |
| GBK | ❌ 明确拒绝 | ✅ 原生 TextDecoder | 浏览器只有解码器没有编码码表 |

## 能力检测

页面加载时自动检测 `crypto.subtle`（Web Crypto）：不可用时显示全局红色横幅说明原因与解决办法，并禁用加密页——老内核浏览器（部分鸿蒙早期版本等）或受限打开方式下不再静默失败。

## 为什么是单文件

实测发现：`file://` 协议下浏览器**禁止 ES 模块 `import`**（CORS 策略，origin 为 `null`）。
任何「HTML + 多个 .js」的结构在双击打开时都会加载失败。因此本版把所有 JS / CSS 内联进
一个 HTML —— 这是「不受设备限制、拷了就能用」的唯一可行形态。

## 构建

```bash
python web/build.py
# 产物：web/dist/DevToolkit.html（约 143 KB）
```

在线访问：[DevToolkit Web](https://alex-758.github.io/DevToolkit/DevToolkit.html)

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

页面内置「自检」按钮（左下角 ⚙ 或「关于软件」页），当前运行 47 项算法校验：

- 编码与字符集 25 项（含拒绝非法输入）
- 哈希 10 项（对照 Python hashlib 权威值）
- 压缩与智能解码 3 项（GZIP 往返、Base64→GZIP、ZLIB 校验和）
- 加密 9 项（往返、错误口令、篡改检测、空明文、ECB 拒绝、ChaCha）

开发期另用 Node 与真实 Edge（CDP 驱动）做端到端验证：UI 初始化、自检全过、编码/哈希/
加密/压缩的 UI 往返、主题切换、控制台零报错。

## 隐私

完全离线：不联网、不上传、不收集任何数据。所有计算在本地浏览器完成，关闭标签页即彻底清除
（仅主题偏好写入 localStorage）。
