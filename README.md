# DevToolkit

<p align="center">
  <img src="assets/icon.png" width="128" alt="DevToolkit 图标">
</p>

**纯离线运行的 Windows 编码解码工具箱** —— 面向开发者与日常技术人员的多功能桌面工具。编码 / 加密 / 压缩 / 哈希 / 智能解码，一个 EXE 全搞定。

**当前版本：[v1.1.0](https://github.com/Alex-758/DevToolkit/releases/latest)** · 深色默认、浅色可切换 · MIT License

## 下载

前往 [Releases 页面](https://github.com/Alex-758/DevToolkit/releases) 下载最新的 `DevToolkit.exe`（单文件、绿色免安装、约 54 MB）：

1. 下载 EXE，双击运行（Windows 10 / 11 x64）
2. 如需卸载，直接删除 EXE 与数据目录 `%APPDATA%\DevToolkit\` 即可，无任何残留

首次运行如被 SmartScreen 提示，选择「仍要运行」即可（本程序为未签名的开源软件，可用下方命令自行从源码构建验证）。

## 功能总览

| 页面 | 能力 |
|---|---|
| **编码解码** | Base64 / Base64URL / Base32 / Base16(Hex) / Base58 / Base62 / URL / HTML 实体 / Unicode 转义 / ASCII / ROT13 / Quoted-Printable 共 **12 种**，双向编解码；UTF-8 / GBK 等字符集；多行批量逐行处理；自动识别编码（候选 + 置信度 + 判断依据 + 解码预览） |
| **加密解密** | AES-128/192/256（GCM / CBC / ECB）、ChaCha20-Poly1305、RSA-OAEP 加解密、RSA-PSS 签名验签；口令 PBKDF2（默认 210,000 次迭代）派生；密钥生成 / 导入 / 导出（PEM）；ECB / CBC 风险标记；哈希与加密严格分页 |
| **压缩解压** | GZIP / ZLIB / DEFLATE / ZIP / Brotli / Zstandard / LZ4；文本与二进制；Base64 展示与自动解码；**防压缩炸弹**（默认输出上限 512 MB，可在设置调整，逐块解压超限立即终止） |
| **哈希计算** | MD5 / SHA-1 / SHA-224 / SHA-256 / SHA-384 / SHA-512 / SHA3-256 / SHA3-512 / BLAKE2b-512 / BLAKE2s-256 共 **10 种**同屏展示；文本自动计算；大文件哈希（后台线程 + 进度 + 取消）；双哈希比较；逐行批量 |
| **智能解码** | 自动尝试「编码 + 压缩」多层组合链路（如 Base64 → GZIP → UTF-8），逐步展示前后对比；层数 1–10 可调；防循环、防炸弹；失败保留原始输入 |
| **文件处理** | Base64 / Hex 编码、多算法校验值、GZIP 压缩 / 解压；二进制安全读取；后台线程 + 进度 + 取消；支持拖放；结果可保存 |
| **历史记录** | 最近操作（容量可调）；搜索 / 筛选 / 删除 / 清空；**密钥、口令、明文与密文绝不写入历史** |
| **关于软件** | 版本信息、**检查更新**（手动查询 GitHub Releases）、快捷键、隐私声明 |

## 安全与隐私设计

- **完全离线**：不联网、不上传、不收集任何数据，所有计算均在本地完成
- 唯一例外是「检查更新」：**仅在你点击按钮时**查询一次 GitHub Releases，只带固定 User-Agent，不上传任何本地数据；应用自身绝不自动联网
- AEAD（GCM / ChaCha20-Poly1305）为推荐模式并明确标注；ECB 红色警告、CBC 黄色提示
- 口令从不直接当密钥：PBKDF2-HMAC-SHA256 + 随机盐派生；Nonce / IV 每次随机生成
- 加密信封带魔数与格式校验，篡改密文会被认证层拒绝
- 解压逐块执行并强制输出上限，压缩炸弹无法打爆内存
- 历史记录只存操作摘要（算法 + 数据规模），不含密钥与内容
- 所有数据保存在本地 `%APPDATA%\DevToolkit\`，删除即彻底清除

## 快捷键

| 快捷键 | 功能 |
|---|---|
| `Ctrl+Enter` | 执行当前页操作 |
| `Ctrl+1` ~ `Ctrl+8` | 切换功能页 |
| `Ctrl+T` | 深色 / 浅色主题 |
| `Ctrl+Shift+K` | 复制当前页结果 |
| `Ctrl+R` | 编码解码页：交换输入与输出 |
| `Ctrl+,` | 设置 |

## 从源码运行

```bash
git clone https://github.com/Alex-758/DevToolkit.git
cd DevToolkit
pip install -r requirements-dev.txt   # 国内网络建议加清华镜像 -i https://pypi.tuna.tsinghua.edu.cn/simple

# 运行测试（279 项 pytest 单元测试 + 53 项全场景 UI 模拟测试）
python -m pytest tests/ -q
python tests/ui_scenarios.py

# 启动 GUI
python main.py

# 核心自检（打包验证用）
python main.py --selftest
```

环境要求：Python 3.11+，Windows（UI 在 Windows 上开发测试）。

### 打包为独立 EXE

```bash
python -m PyInstaller DevToolkit.spec --noconfirm --clean
# 产物：dist/DevToolkit.exe（单文件、无控制台、含版本信息与图标）
# 验证：dist/DevToolkit.exe --selftest --selftest-log selftest.json
```

## 架构

```
DevToolkit/
├── main.py                 # 入口：GUI / --selftest / --smoke-ui / --version
├── app/
│   ├── core/               # 算法层（纯 Python，不依赖 GUI，可独立单测）
│   │   ├── encoders.py     # 12 种编解码器 + 字节级解码 API
│   │   ├── crypto_tools.py # AES / ChaCha20 / RSA（信封格式 + 认证）
│   │   ├── compress_tools.py  # 7 种压缩格式 + 逐块炸弹防护
│   │   ├── hashing.py      # 10 种哈希，文件流式计算
│   │   ├── detect.py       # 编码自动识别（候选 + 置信度）
│   │   ├── smart_decode.py # 多层链路解码
│   │   ├── batch.py        # 批量逐行处理
│   │   ├── history.py      # 历史 / 收藏（本地 JSON）
│   │   ├── updater.py      # 检查更新（唯一联网模块，用户触发）
│   │   └── config.py       # 设置与数据目录（含非法值清洗）
│   └── ui/                 # 界面层（PySide6，只调用 core）
│       ├── main_window.py  # 主窗口 / 侧边导航 / 快捷键
│       ├── theme.py        # GPT 风格深浅主题（QSS 模板）
│       ├── icons.py        # 内置 SVG 线性图标（随主题着色）
│       ├── widgets.py      # 卡片 / 芯片 / 后台 Worker（竞态安全）
│       ├── settings_dialog.py
│       └── pages/          # 8 个功能页
├── tests/                  # pytest 单元测试 + 全场景 UI 模拟测试
└── DevToolkit.spec         # PyInstaller 打包配置
```

**质量保障**：279 项 pytest 单元测试（含安全约束测试：密钥不进历史、信封不含密钥、压缩炸弹防护、超限快速失败等）+ 53 项全场景 UI 模拟测试（真实控件端到端）+ 打包后自检 + UI 冒烟测试。

## 许可

MIT License
