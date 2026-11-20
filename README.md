# DevToolkit

<p align="center">
  <img src="assets/icon.png" width="128" alt="DevToolkit 图标">
</p>

**纯离线运行的 Windows 编码解码工具箱** —— 编码 / 加密 / 压缩 / 哈希 / 智能解码，一个 EXE 全搞定。
深色默认、浅色可切换 · 当前版本 [v1.1.0](https://github.com/Alex-758/DevToolkit/releases/latest) · MIT License

## 下载

前往 [Releases](https://github.com/Alex-758/DevToolkit/releases) 下载 `DevToolkit.exe`（单文件免安装，约 54 MB，Windows 10 / 11 x64）。

- 双击运行；首次运行如被 SmartScreen 提示，选「仍要运行」（未签名的开源软件，可自行从源码构建验证）
- 卸载：删除 EXE 与数据目录 `%APPDATA%\DevToolkit\` 即可，无任何残留

## 功能（8 页）

| 页面 | 能力 |
|---|---|
| 编码解码 | Base64 / Base32 / Hex / Base58 / Base62 / URL / HTML 实体 / Unicode / ASCII / ROT13 / QP 共 **12 种**双向编解码；UTF-8 / GBK 等字符集；多行批量逐行处理；自动识别（候选 + 置信度 + 预览） |
| 加密解密 | AES-128/192/256（GCM / CBC / ECB）、ChaCha20-Poly1305、RSA-OAEP 加解密、RSA-PSS 签名验签；口令 PBKDF2 派生（默认 210,000 次迭代）；密钥生成 / PEM 导入导出；哈希与加密严格分页 |
| 压缩解压 | GZIP / ZLIB / DEFLATE / ZIP / Brotli / Zstandard / LZ4；文本与二进制；Base64 展示与自动解码；**防压缩炸弹**（输出上限默认 512 MB，可调，超限立即终止） |
| 哈希计算 | MD5 / SHA 全系 / SHA3 / BLAKE2 共 **10 种**同屏展示；大文件哈希（后台线程 + 进度 + 取消）；双哈希比较；逐行批量 |
| 智能解码 | 自动尝试「编码 + 压缩」多层链路（如 Base64 → GZIP → UTF-8）；层数 1–10 可调；防循环、防炸弹；失败保留原始输入 |
| 文件处理 | Base64 / Hex 编码、多算法校验值、GZIP 压缩解压；二进制安全读取；后台线程；支持拖放；结果可保存 |
| 历史记录 | 最近操作（容量可调）；搜索 / 筛选 / 删除 / 清空；**密钥、口令与内容绝不写入** |
| 关于软件 | 版本信息、检查更新（手动查询 GitHub Releases）、快捷键、隐私声明 |

## 安全与隐私

- **完全离线**：所有计算本地完成，不上传、不收集任何数据；唯一联网是「检查更新」——仅在你点击时查询一次 GitHub Releases，不上传本地数据
- AEAD（GCM / ChaCha20-Poly1305）为推荐模式并明确标注；ECB 红色警告、CBC 黄色提示
- 口令从不直接当密钥：PBKDF2-HMAC-SHA256 + 随机盐派生；Nonce / IV 每次随机生成
- 密文自带信封魔数与格式校验，篡改密文会被认证层拒绝
- 解压逐块执行并强制输出上限，压缩炸弹无法打爆内存
- 历史只存操作摘要（算法 + 数据规模），不含密钥与内容
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
pip install -r requirements-dev.txt   # 国内网络可加 -i https://pypi.tuna.tsinghua.edu.cn/simple

python -m pytest tests/ -q        # 306 项单元测试
python tests/ui_scenarios.py      # 54 项全场景 UI 模拟测试
python main.py                    # 启动 GUI
python main.py --selftest         # 核心自检（打包验证用）
```

环境：Python 3.11+，Windows。

### 打包为独立 EXE

```bash
python -m PyInstaller DevToolkit.spec --noconfirm --clean
# 产物：dist/DevToolkit.exe；验证：dist/DevToolkit.exe --selftest
```

## 架构

```
app/core/   算法层：encoders / crypto_tools / compress_tools / hashing /
            detect / smart_decode / batch / history / updater（唯一联网模块，
            仅用户点击检查更新时使用）/ config —— 纯 Python，可独立单测
app/ui/     界面层：main_window / theme / widgets / settings_dialog + 8 个页面
            （PySide6，只调用 core）
tests/      pytest 单元测试 + 全场景 UI 模拟测试
```

**质量保障**：306 项 pytest 单元测试（含安全约束：密钥不进历史、信封不含密钥、压缩炸弹防护、截断流完整性、跨进程写锁等）+ 54 项全场景 UI 模拟测试 + 打包后自检 + UI 冒烟测试。

## 许可

MIT License
