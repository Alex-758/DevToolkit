# DevToolkit

纯离线 Windows 编码解码工具箱，覆盖编码、加密、压缩、哈希、智能解码和文件处理。

- 当前桌面版：**v1.2.1**
- [下载 Windows EXE（GitHub Releases）](https://github.com/Alex-758/DevToolkit/releases)
- [直接打开网页版（GitHub Pages）](https://alex-758.github.io/DevToolkit/DevToolkit.html)
- MIT License

## 功能

桌面版提供 8 个功能页：

- **编码解码**：Base64、Base32、Hex、Base58、Base62、URL、HTML 实体、Unicode、ASCII、ROT13、Quoted-Printable 等 12 种双向处理；支持字符集、多行批量和自动识别。
- **加密解密**：AES-GCM/CBC/ECB、ChaCha20-Poly1305、RSA-OAEP、RSA-PSS；支持口令 PBKDF2、密钥生成及 PEM 导入导出。
- **压缩解压**：GZIP、ZLIB、DEFLATE、ZIP、Brotli、Zstandard、LZ4；带输出上限和压缩炸弹防护。
- **哈希计算**：MD5、SHA 系列、SHA3、BLAKE2 共 10 种算法；支持大文件后台计算、取消、批量处理和哈希比较。
- **智能解码**：自动尝试编码与压缩的多层链路，展示每一步结果，并限制最大层数和输出大小。
- **文件处理**：文件的 Base64/Hex、哈希、GZIP 压缩解压，支持二进制安全读取、拖放和保存。
- **历史记录**：本地操作摘要、搜索、筛选、收藏、删除和清空；不保存密钥、口令或原文。
- **关于软件**：版本信息、手动检查 GitHub Release 更新、快捷键和隐私说明。

网页版是一个无需安装的单文件 HTML，支持 7 个工具页：编码解码、加密解密、压缩解压、哈希、智能解码、文件处理和关于软件。它适配手机竖屏/横屏、iOS、Android、鸿蒙浏览器、平板和桌面浏览器；浏览器不支持的能力会明确提示。网页版与桌面版的 `DTK1` 加密信封格式兼容。

## 安全与隐私

- 默认完全离线，所有计算在本机完成；只有手动点击“检查更新”时才访问 GitHub Releases。
- GCM、ChaCha20-Poly1305 等 AEAD 模式会校验篡改；ECB 在网页版明确拒绝，桌面版显示风险提示。
- 口令通过 PBKDF2-HMAC-SHA256 和随机盐派生，密钥、Nonce/IV 不写入历史记录。
- 解压过程限制输出大小，避免压缩炸弹耗尽内存。
- 本地设置和历史保存在 `%APPDATA%\\DevToolkit\\`；删除该目录即可清除本地数据。
- 未签名 EXE 可能触发 SmartScreen；可从源码构建并自行校验。

## 从源码运行

环境：Python 3.11+、Windows。

```bash
git clone https://github.com/Alex-758/DevToolkit.git
cd DevToolkit
pip install -r requirements-dev.txt

python -m pytest -q
python tests/ui_scenarios.py
python main.py
python main.py --selftest
```

构建网页版单文件：

```bash
python web/build.py
# web/dist/DevToolkit.html
```

构建 Windows EXE：

```bash
python -m PyInstaller DevToolkit.spec --noconfirm --clean
# dist/DevToolkit.exe
python dist/DevToolkit.exe --selftest
```

## 质量保障

仓库包含 Python 单元测试、桌面 UI 场景测试、核心自检、Web Node 自检和真实 Edge 端到端/多设备视口测试。测试覆盖编码边界、加密篡改与错误口令、压缩截断与输出上限、历史并发写入、Worker 竞态、更新链接安全校验、文件处理和响应式布局。

## 许可证

MIT License
