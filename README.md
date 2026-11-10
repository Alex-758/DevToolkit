# DevToolkit

纯离线运行的 Windows 编码解码工具箱 —— 面向开发者、程序员与日常技术人员的多功能桌面工具。

![DevToolkit](assets/icon.png)

**当前版本：v1.0.0** · 界面风格：GPT / Codex 风格极简设计（深色默认，浅色可切换）

## 功能总览

| 页面 | 能力 |
|---|---|
| **编码解码** | Base64 / Base64URL / Base32 / Base16(Hex) / Base58 / Base62 / URL / HTML 实体 / Unicode 转义 / ASCII / ROT13 / Quoted-Printable，共 12 种，编码解码双向；支持 UTF-8 中文、GBK 等字符集；多行批量逐行处理；自动识别编码（候选 + 置信度 + 判断依据 + 解码预览） |
| **加密解密** | AES-128/192/256（GCM / CBC / ECB）、ChaCha20-Poly1305、RSA-OAEP 加解密、RSA-PSS 签名验签；口令 PBKDF2（默认 210,000 次迭代）派生；密钥生成 / 导入 / 导出（PEM）；ECB / CBC 风险标记，GCM 与 ChaCha20 为推荐模式；哈希与加密严格分页，绝不混淆 |
| **压缩解压** | GZIP / ZLIB / DEFLATE / ZIP / Brotli / Zstandard / LZ4；文本与二进制；Base64 展示与自动解码；防压缩炸弹（默认输出上限 512 MB，可在设置调整） |
| **哈希计算** | MD5 / SHA-1 / SHA-224 / SHA-256 / SHA-384 / SHA-512 / SHA3-256 / SHA3-512 / BLAKE2b-512 / BLAKE2s-256 共 10 种同屏展示；文本自动计算；文件哈希（后台线程 + 进度 + 取消）；两哈希比较；逐行批量 |
| **智能解码** | 自动尝试「编码 + 压缩」多层组合（如 Base64 → GZIP → UTF-8），完整链路与每步前后对比；层数可调（1–10，默认 5）；已处理内容不重复解码；失败保留原始输入；ROT13 不参与自动链路 |
| **文件处理** | Base64 / Hex 编码、SHA-256 校验、GZIP 压缩 / 解压；二进制安全读取（不强制 UTF-8）；后台线程 + 进度条 + 取消；拖放文件；结果保存 |
| **历史记录** | 最近 200 条操作（可调）；搜索 / 筛选 / 单条删除 / 一键清空；**密钥、口令、明文与密文绝不写入历史** |
| **关于软件** | 版本、技术栈、快捷键、隐私声明 |

## 安全设计

- AEAD（GCM / ChaCha20-Poly1305）为推荐默认模式；ECB 红色警告、CBC 黄色提示
- 口令从不直接当密钥：PBKDF2-HMAC-SHA256 + 随机盐派生
- Nonce / IV 每次加密随机生成
- 解压逐块执行并强制上限，防止压缩炸弹
- 历史记录只存操作摘要，不含密钥与内容
- 程序完全离线：不联网、不上传、不收集任何数据

## 快捷键

| 快捷键 | 功能 |
|---|---|
| `Ctrl+Enter` | 执行当前页操作 |
| `Ctrl+1` ~ `Ctrl+8` | 切换功能页 |
| `Ctrl+T` | 深色 / 浅色主题 |
| `Ctrl+Shift+K` | 复制当前页结果 |
| `Ctrl+R` | 编码解码页：交换输入与输出 |
| `Ctrl+,` | 设置 |

## 开发

```bash
# 安装依赖（国内网络建议加清华镜像）
pip install -r requirements-dev.txt

# 运行测试（248 项单元测试）
python -m pytest tests/ -q

# 启动 GUI
python main.py

# 核心自检
python main.py --selftest

# UI 冒烟测试 + 截图（Windows 上窗口会短暂闪现）
python main.py --smoke-ui artifacts/smoke
```

### 目录结构

```
DevToolkit/
├── main.py                 # 入口：GUI / --selftest / --smoke-ui
├── app/
│   ├── core/               # 算法层（纯 Python，不依赖 GUI，可独立单测）
│   │   ├── encoders.py     # 12 种编解码器 + 字节级解码 API
│   │   ├── crypto_tools.py # AES / ChaCha20 / RSA
│   │   ├── compress_tools.py
│   │   ├── hashing.py
│   │   ├── detect.py       # 自动识别（候选 + 置信度）
│   │   ├── smart_decode.py # 多层链路解码
│   │   ├── batch.py        # 批量逐行处理
│   │   ├── history.py      # 历史 / 收藏（本地 JSON）
│   │   └── config.py       # 设置与数据目录
│   └── ui/                 # 界面层（PySide6，只调用 core）
│       ├── main_window.py  # 主窗口 / 侧边导航 / 快捷键
│       ├── theme.py        # GPT 风格深浅主题（QSS 模板）
│       ├── icons.py        # 内置 SVG 线性图标（随主题着色）
│       ├── widgets.py      # 卡片 / 芯片 / 后台 Worker
│       ├── settings_dialog.py
│       └── pages/          # 8 个功能页
├── tests/                  # pytest 单元测试
└── DevToolkit.spec         # PyInstaller 打包配置
```

### 打包为独立 EXE

```bash
python -m PyInstaller DevToolkit.spec --noconfirm --clean
# 产物：dist/DevToolkit.exe（单文件、无控制台、含版本信息与图标）
# 验证：dist/DevToolkit.exe --selftest --selftest-log selftest.json
```

## 许可

MIT License
