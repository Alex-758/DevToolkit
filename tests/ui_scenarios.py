"""全场景 UI 模拟测试：用真实控件端到端模拟各类使用情况。

运行：python tests/ui_scenarios.py
（使用真实 windows 平台；不做文件对话框交互，直接调用页面内部方法）
"""

import base64
import gzip
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from app.core import config, crypto_tools, hashing, history  # noqa: E402
from app.ui.context import CTX  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.theme import build_qss  # noqa: E402

# 隔离用户数据目录
import tempfile  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="dt-scenarios-")
os.environ["APPDATA"] = _tmp

CTX.set_theme("dark")
app.setStyleSheet(build_qss("dark"))
win = MainWindow()
win.show()
for _ in range(8):
    app.processEvents()
    time.sleep(0.03)

failures = []


def check(name, cond, extra=""):
    if cond:
        print(f"SCENARIO PASS: {name}")
    else:
        failures.append(f"{name} {extra}")
        print(f"SCENARIO FAIL: {name} {extra}")


SAMPLE = "Hello, DevToolkit! 你好，世界 😀"


def wait_done(btn, timeout_s=15):
    """等待后台任务完成：执行按钮被禁用后重新启用即完成。"""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        app.processEvents()
        if btn.isEnabled():
            for _ in range(3):
                app.processEvents()
                time.sleep(0.01)
            if btn.isEnabled():
                return True
        time.sleep(0.02)
    return False

# ---------------------------------------------------------------------------
# 1. 加密页：AES-GCM 口令模式 加密 → 解密 往返
# ---------------------------------------------------------------------------
enc_page = win.pages["encode"]
crypto = win.pages["crypto"]
crypto.algo_combo.setCurrentIndex(0)  # AES-256-GCM
crypto._on_algo_change()
crypto.in_edit.setPlainText(SAMPLE)
crypto.pass_edit.setText("scenario-passphrase-123")
crypto.src_combo.setCurrentIndex(0)
crypto.dir_a.setChecked(True)  # 加密
crypto._execute()
app.processEvents()
cipher_b64 = crypto.out_edit.result_text()
check("crypto: encrypt output non-empty", len(cipher_b64) > 40, repr(cipher_b64[:30]))
check("crypto: encrypt chip ok", "加密成功" in crypto.out_header.chip_lbl.text())

# 解密
crypto.dir_b.setChecked(True)
crypto.in_edit.setPlainText(cipher_b64)
crypto._execute()
app.processEvents()
check("crypto: decrypt roundtrip", crypto.out_edit.result_text() == SAMPLE,
      repr(crypto.out_edit.result_text()[:40]))

# 错误口令
crypto.pass_edit.setText("wrong-passphrase")
crypto._execute()
app.processEvents()
check("crypto: wrong passphrase rejected", "解密失败" in crypto.out_header.chip_lbl.text())

# ---------------------------------------------------------------------------
# 2. 加密页：ECB 风险标记
# ---------------------------------------------------------------------------
crypto.algo_combo.setCurrentIndex(2)  # AES-ECB
crypto._on_algo_change()
crypto.pass_edit.setText("p" * 8)
crypto.dir_a.setChecked(True)
crypto.in_edit.setPlainText("ecb test")
crypto._execute()
app.processEvents()
check("crypto: ECB warning shown", "ECB" in crypto.out_header.chip_lbl.text() and "不安全" in crypto.out_header.chip_lbl.text(),
      crypto.out_header.chip_lbl.text())

# ---------------------------------------------------------------------------
# 3. 加密页：RSA 签名 → 验签
# ---------------------------------------------------------------------------
pair = crypto_tools.generate_keypair(2048)
priv, pub = pair.data["private_pem"], pair.data["public_pem"]
crypto.algo_combo.setCurrentIndex(5)  # RSA-PSS
crypto._on_algo_change()
crypto.rsa_key_edit.setPlainText(priv)
crypto.dir_a.setChecked(True)  # 签名
crypto.in_edit.setPlainText("待签名文档 signature doc")
crypto._execute()
app.processEvents()
sig_b64 = crypto.out_edit.result_text()
check("crypto: rsa sign output", len(sig_b64) > 100,
      crypto.out_header.chip_lbl.text() + " | " + repr(sig_b64[:20]))
# 验签
crypto.rsa_key_edit.setPlainText(pub)
crypto.dir_b.setChecked(True)  # 验签
crypto.in_edit.setPlainText("待签名文档 signature doc")
crypto.sig_edit.setText(sig_b64)
crypto._execute()
app.processEvents()
check("crypto: rsa verify pass", "验签通过" in crypto.out_header.chip_lbl.text())
# 篡改原文 → 验签失败
crypto.in_edit.setPlainText("被篡改的文档")
crypto._execute()
app.processEvents()
check("crypto: rsa verify fail on tampered", "验签失败" in crypto.out_header.chip_lbl.text())

# ---------------------------------------------------------------------------
# 4. 压缩页：GZIP 往返 + Base64
# ---------------------------------------------------------------------------
comp = win.pages["compress"]
comp.in_edit.setPlainText("压缩测试 " * 200)
comp.comp_btn.setChecked(True)
comp.fmt_combo.setCurrentIndex(0)  # GZIP
comp._execute()
app.processEvents()
b64_out = comp.out_edit.result_text()
check("compress: gzip b64 output", b64_out.startswith("H4sI"), repr(b64_out[:20]))
# 解压
comp.decomp_btn.setChecked(True)
comp.in_edit.setPlainText(b64_out)
comp._execute()
app.processEvents()
check("compress: gunzip roundtrip", comp.out_edit.result_text() == "压缩测试 " * 200,
      repr(comp.out_edit.result_text()[:30]))

# 解压损坏数据 → 友好错误
comp.in_edit.setPlainText("H4sI-corrupted-data!!!")
comp._execute()
app.processEvents()
check("compress: corrupt input friendly error", "✕" in comp.out_header.chip_lbl.text())

# ---------------------------------------------------------------------------
# 5. 文件页：真实文件 哈希 / Base64 / GZIP 解压
# ---------------------------------------------------------------------------
files = win.pages["files"]
import pathlib
tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="dt-files-"))
f1 = tmpdir / "sample.txt"
f1.write_text("文件处理场景测试 file scenario 你好", encoding="utf-8")
files._load_file(str(f1))
app.processEvents()
check("files: file loaded", files.run_btn.isEnabled() and "sample.txt" in files.file_header.title_lbl.text())

files.op_combo.setCurrentIndex(2)  # SHA-256
files._run()
check("files: worker finished", wait_done(files.run_btn))
expected_sha = hashing.text_hash("文件处理场景测试 file scenario 你好", "sha256").data
got = files.out_edit.result_text()
check("files: hash matches core", expected_sha in got, repr(got[:60]))

files.op_combo.setCurrentIndex(0)  # Base64
files._run()
check("files: worker finished", wait_done(files.run_btn))
expected_b64 = base64.b64encode(f1.read_bytes()).decode()
check("files: base64 matches", expected_b64 in files.out_edit.result_text())

# GZIP 解压：先把压缩文件写盘再载入
gz = tmpdir / "sample.txt.gz"
gz.write_bytes(gzip.compress(f1.read_bytes()))
files._load_file(str(gz))
files.op_combo.setCurrentIndex(4)  # GZIP 解压
files._run()
check("files: worker finished", wait_done(files.run_btn))
check("files: gunzip to text", "文件处理场景测试 file scenario 你好" in files.out_edit.result_text(),
      repr(files.out_edit.result_text()[:40]))

# ---------------------------------------------------------------------------
# 6. 历史记录：有记录 → 搜索筛选 → 清空
# ---------------------------------------------------------------------------
hist = win.pages["history"]
hist.on_show()
app.processEvents()
check("history: rows recorded", hist.tree.topLevelItemCount() >= 5,
      f"rows={hist.tree.topLevelItemCount()}")
hist.search_input.setText("AES")
app.processEvents()
check("history: search filter", hist.tree.topLevelItemCount() >= 1)
hist.search_input.setText("")
hist.page_combo.setCurrentIndex(2)  # 压缩解压
app.processEvents()
check("history: page filter", hist.tree.topLevelItemCount() >= 2)
hist.page_combo.setCurrentIndex(0)
# 逐条 API 删除
entries = history.list_entries()
before = len(entries)
history.remove_entry(0)
check("history: remove entry", len(history.list_entries()) == before - 1)
history.clear_entries()
check("history: clear", history.list_entries() == [])

# ---------------------------------------------------------------------------
# 7. 编码页：批量模式 + 交换 + 收藏
# ---------------------------------------------------------------------------
enc_page.in_edit.setPlainText("line-a\nline-b\n\nline-c")
enc_page.batch_chk.setChecked(True)
enc_page.algo_combo.setCurrentIndex(0)
enc_page.enc_btn.setChecked(True)
enc_page._execute()
app.processEvents()
out = enc_page.out_edit.result_text().splitlines()
check("batch: 3 rows with index", len(out) == 3 and out[0].startswith("1  bGluZS1h"), repr(out))

# 交换：把批量输出换到输入侧再解码
b64a = base64.b64encode(b"line-a").decode()
b64b = base64.b64encode(b"line-b").decode()
b64c = base64.b64encode(b"line-c").decode()
enc_page.in_edit.setPlainText(f"{b64a}\n{b64b}\n{b64c}")
enc_page.dec_btn.setChecked(True)
enc_page._execute()
app.processEvents()
check("batch decode per line", enc_page.out_edit.result_text() == "1  line-a\n2  line-b\n3  line-c",
      repr(enc_page.out_edit.result_text()))

enc_page._swap()
app.processEvents()
# R5 B8 修复后：批量模式下交换回的是纯逐行结果（不带行号前缀），
# 再次执行可正确 roundtrip（旧行为把「1  line-a」连行号一起换入）
check("swap: output to input (plain rows, no index)",
      enc_page.in_edit.toPlainText() == "line-a\nline-b\nline-c",
      repr(enc_page.in_edit.toPlainText()))

enc_page._toggle_fav()
from app.core import history as hist_mod  # noqa: E402
check("favorite toggled", hist_mod.is_favorite("codec", "base64"))

# ---------------------------------------------------------------------------
# 8. 智能解码：嵌套 Base64 与垃圾输入
# ---------------------------------------------------------------------------
smart = win.pages["smart"]
nested = base64.b64encode(base64.b64encode(SAMPLE.encode())).decode()
smart.in_edit.setPlainText(nested)
smart.layers_spin.setValue(5)
smart._run()
check("smart: worker finished", wait_done(smart.run_btn))
check("smart: nested b64 full decode", smart.out_edit.result_text() == SAMPLE,
      repr(smart.out_edit.result_text()[:40]))

smart.in_edit.setPlainText("无特征内容 ∑∑∑ ???")
smart._run()
check("smart: worker finished", wait_done(smart.run_btn))
check("smart: garbage preserved", smart.out_edit.result_text() == "无特征内容 ∑∑∑ ???")

# ---------------------------------------------------------------------------
# 9. 性能：万行批量编码耗时
# ---------------------------------------------------------------------------
big_text = "\n".join(f"第{i}行 data-{i}" for i in range(10000))
enc_page.in_edit.setPlainText(big_text)
enc_page.batch_chk.setChecked(True)
enc_page.enc_btn.setChecked(True)
enc_page.algo_combo.setCurrentIndex(0)
enc_page._execute()
app.processEvents()
check("perf: 10k-line batch completes", "批量完成" in enc_page.out_header.chip_lbl.text(),
      enc_page.out_header.chip_lbl.text())

# ---------------------------------------------------------------------------
# 10. R1/R2 修复回归：压缩页方向互斥 + Hex 往返
# ---------------------------------------------------------------------------
comp.comp_btn.setChecked(True)
comp._execute()
app.processEvents()
check("dir-group: compress direction after switching back",
      "压缩" in comp.out_header.chip_lbl.text(), comp.out_header.chip_lbl.text())

comp.in_edit.setPlainText("Hex 显示往返回归 " * 200)
comp.b64_chk.setChecked(False)  # 用 Hex 显示
comp._execute()
app.processEvents()
hex_zip = comp.out_edit.result_text().strip()
check("compress-hex: output is pure hex",
      len(hex_zip) > 0 and all(c in "0123456789abcdefABCDEF" for c in hex_zip))
comp.decomp_btn.setChecked(True)
comp.in_edit.setPlainText(hex_zip)
comp._execute()
app.processEvents()
check("compress-hex: roundtrip decompress ok",
      "解压成功" in comp.out_header.chip_lbl.text(), comp.out_header.chip_lbl.text())
check("compress-hex: roundtrip content match",
      comp.out_edit.result_text() == "Hex 显示往返回归 " * 200)

# ---------------------------------------------------------------------------
# 11. R1 修复回归：加密页 Hex 输出模式往返（hex 密文曾被误按 Base64 解析）
# ---------------------------------------------------------------------------
from PySide6.QtWidgets import QMessageBox as _QMB  # noqa: E402

_QMB.information = lambda *a, **k: _QMB.StandardButton.Ok
_QMB.warning = lambda *a, **k: _QMB.StandardButton.Ok

crypto.algo_combo.setCurrentIndex(0)  # AES-256-GCM
crypto._on_algo_change()
crypto.enc_combo.setCurrentIndex(1)  # 密文输出 = Hex
crypto.pass_edit.setText("scenario-hex-pass")
crypto.in_edit.setPlainText("Hex 输出模式往返 scenario 明文")
crypto.dir_a.setChecked(True)
crypto._execute()
app.processEvents()
hex_ct = crypto.out_edit.result_text().strip()
check("crypto-hex: output is pure hex",
      len(hex_ct) > 0 and all(c in "0123456789abcdefABCDEF" for c in hex_ct))
crypto.dir_b.setChecked(True)
crypto.in_edit.setPlainText(hex_ct)
crypto._execute()
app.processEvents()
check("crypto-hex: roundtrip decrypt ok",
      "解密成功" in crypto.out_header.chip_lbl.text(), crypto.out_header.chip_lbl.text())
check("crypto-hex: roundtrip plaintext match",
      crypto.out_edit.result_text() == "Hex 输出模式往返 scenario 明文")

# ---------------------------------------------------------------------------
# 12. R1 修复回归：RSA 密钥后台生成（立即返回 + 完成后填充）
# ---------------------------------------------------------------------------
crypto.algo_combo.setCurrentIndex(5)  # RSA-PSS
crypto._on_algo_change()
t0 = time.time()
crypto._gen_rsa()
check("rsa-bg: _gen_rsa returns immediately", time.time() - t0 < 0.5)
t0 = time.time()
while time.time() - t0 < 30:
    app.processEvents()
    if "-----BEGIN" in crypto.rsa_key_edit.toPlainText():
        break
    time.sleep(0.03)
check("rsa-bg: keypair filled in background", "-----BEGIN" in crypto.rsa_key_edit.toPlainText())
check("rsa-bg: button restored", crypto.gen_btn.isEnabled() and crypto.gen_btn.text() == "生成密钥对")

# ---------------------------------------------------------------------------
# 13. R1 修复回归：哈希页文件哈希不被空文本自动重算覆盖
# ---------------------------------------------------------------------------
import hashlib as _hl  # noqa: E402

f_hash = tmpdir / "scenario-hash.bin"
f_hash.write_bytes(os.urandom(2048))
hash_page = win.pages["hash"]
hash_page.in_edit.setPlainText("这段文本哈希应被文件哈希结果替换")
hash_page._recompute_now()
app.processEvents()
hash_page._start_file_hash(str(f_hash))
t0 = time.time()
while time.time() - t0 < 10:
    app.processEvents()
    if hash_page.prog_card.isHidden():
        break
    time.sleep(0.02)
val_at_done = hash_page._hash_rows["sha256"][1].text()
time.sleep(0.6)  # 越过 300ms 自动重算定时器
app.processEvents()
val_after = hash_page._hash_rows["sha256"][1].text()
expected_file_hash = _hl.sha256(f_hash.read_bytes()).hexdigest()
check("hash-file: value at completion is file hash", val_at_done == expected_file_hash,
      f"got={val_at_done[:16]}")
check("hash-file: not overwritten by empty-text recompute",
      val_after == expected_file_hash and val_after != _hl.sha256(b"").hexdigest(),
      f"after={val_after[:16]}")

# ---------------------------------------------------------------------------
# 14. R2 修复回归：IOEditor 动态换行策略（大文本 NoWrap，回落恢复 Wrap）
# ---------------------------------------------------------------------------
enc_page.in_edit.setPlainText("A" * (200 * 1024))
app.processEvents()
check("wrap: large input switches to NoWrap",
      enc_page.in_edit.lineWrapMode() == enc_page.in_edit.LineWrapMode.NoWrap)
enc_page.in_edit.setPlainText("short")
app.processEvents()
check("wrap: small input restores WidgetWidth",
      enc_page.in_edit.lineWrapMode() == enc_page.in_edit.LineWrapMode.WidgetWidth)

# b58/b62 超限在真实页面给出明确错误
enc_page.in_edit.setPlainText("3" * 40000)
enc_page.batch_chk.setChecked(False)  # 场景 9 开启了批量模式，先恢复单行模式
enc_page.algo_combo.setCurrentIndex(4)  # Base58
enc_page.dec_btn.setChecked(True)
enc_page._execute()
app.processEvents()
check("b58-limit: friendly error in UI", "过大" in enc_page.out_header.chip_lbl.text(),
      enc_page.out_header.chip_lbl.text())
enc_page.in_edit.setPlainText("")

# ---------------------------------------------------------------------------
# 场景 15-17：WorkerRunner 竞态 / 取消回调 / 文件页 busy 保护（R4 回归）
# ---------------------------------------------------------------------------

from app.core.results import Result as _R  # noqa: E402
from app.ui.widgets import WorkerRunner as _WR  # noqa: E402

# 场景 15：旧任务 done 晚到不得破坏新任务（旧实现会 deleteLater 运行中的
# 新 Worker，触发 "QThread: Destroyed while thread is still running" 并崩溃）
_arrived = []
_rr = _WR(lambda r: _arrived.append(r.data), None, None)


def _job_a(_w):  # 忽略取消：跑到完成，制造「过期 done 在新任务运行期间送达」
    time.sleep(0.4)
    return _R.success("A")


def _job_b(_w):
    time.sleep(0.4)
    return _R.success("B")


_rr.start(_job_a)
_t0 = time.time()
_rr.start(_job_b)  # 立即取代 A；A 的 done 将在 B 运行期间送达
while time.time() - _t0 < 2.0 and not _arrived:
    app.processEvents()
    time.sleep(0.01)
check("runner: stale done does not destroy current worker",
      _arrived == ["B"] and not _rr.busy(), repr(_arrived))

# 场景 16：stop() 取消后终止结果仍送达回调（页面恢复 UI 的唯一依赖；
# 旧实现 generation 抑制回调导致进度卡永不隐藏、按钮永久禁用）
_arrived2 = []
_rr2 = _WR(lambda r: _arrived2.append((r.ok, r.error)), None, None)


def _job_c(w):  # 协作取消：每 20ms 检查一次
    for _ in range(40):
        if w.is_cancelled():
            return _R.failure("已取消")
        time.sleep(0.02)
    return _R.success("C")


_rr2.start(_job_c)
_t0 = time.time()
while time.time() - _t0 < 0.3:
    app.processEvents()
    time.sleep(0.01)
_rr2.stop()
while time.time() - _t0 < 3.0 and not _arrived2:
    app.processEvents()
    time.sleep(0.01)
check("runner: cancel still delivers callback",
      _arrived2 == [(False, "已取消")], repr(_arrived2))

# 场景 17：文件页任务运行中禁止再次启动（Ctrl+Return 快捷键绕过禁用按钮）
files_page = win.pages["files"]
files_page._file_path = "scenario-guard-path"  # 守卫不读文件，路径仅需非空
files_page.file_runner.start(
    lambda _w: (time.sleep(0.6), _R.success(
        {"kind": "text", "text": "", "meta": "guard", "binary": None, "ms": 1}))[1]
)
app.processEvents()
_status = []
files_page.statusMsg.connect(_status.append)
files_page._run()  # busy → 必须被拒绝
check("files: busy guard rejects second run",
      bool(_status) and "已有任务" in _status[-1], repr(_status[-1:]))
_t0 = time.time()
while time.time() - _t0 < 3.0 and files_page.file_runner.busy():
    app.processEvents()
    time.sleep(0.01)
files_page.statusMsg.disconnect(_status.append)
files_page._file_path = ""
files_page._run_path = ""

# ---------------------------------------------------------------------------
# 场景 18-19：关于页「检查更新」（mock 网络层，不发真实请求）
# ---------------------------------------------------------------------------

from app.core import updater as _upd  # noqa: E402

about_page = win.pages["about"]
_orig_fetch = _upd.fetch_latest_release

# 场景 18：发现新版本 → chip 显示新版本号 + 下载页链接，按钮恢复
# （mock tag 需严格大于 APP_VERSION；随版本升级同步调高）
_upd.fetch_latest_release = lambda: _R.success({
    "tag": "v1.3.0",
    "url": "https://github.com/Alex-758/DevToolkit/releases/tag/v1.3.0",
    "name": "",
})
about_page._check_update()
_t0 = time.time()
while time.time() - _t0 < 3.0 and about_page.update_runner.busy():
    app.processEvents()
    time.sleep(0.01)
# busy() 变 False 时 done 信号可能仍在事件队列：补泵几轮再断言
for _ in range(5):
    app.processEvents()
    time.sleep(0.01)
check("update: new version chip with download link",
      about_page.check_btn.isEnabled()
      and "发现新版本 v1.3.0" in about_page.update_chip.text()
      and "https://github.com/" in about_page.update_chip.text(),
      repr(about_page.update_chip.text()))

# 场景 19：已是最新 → ok chip；网络失败 → err chip（恢复原 fetch 前先测失败）
_upd.fetch_latest_release = lambda: _R.failure("网络不可用或查询超时，请稍后再试")
about_page._check_update()
_t0 = time.time()
while time.time() - _t0 < 3.0 and about_page.update_runner.busy():
    app.processEvents()
    time.sleep(0.01)
for _ in range(5):
    app.processEvents()
    time.sleep(0.01)
check("update: network failure shows friendly error",
      about_page.check_btn.isEnabled() and "网络不可用" in about_page.update_chip.text(),
      repr(about_page.update_chip.text()))

_upd.fetch_latest_release = lambda: _R.success({
    "tag": "v1.0.0",
    "url": "https://github.com/Alex-758/DevToolkit/releases/latest",
    "name": "",
})
about_page._check_update()
_t0 = time.time()
while time.time() - _t0 < 3.0 and about_page.update_runner.busy():
    app.processEvents()
    time.sleep(0.01)
for _ in range(5):
    app.processEvents()
    time.sleep(0.01)
check("update: up-to-date chip",
      about_page.check_btn.isEnabled() and "已是最新" in about_page.update_chip.text(),
      repr(about_page.update_chip.text()))
_upd.fetch_latest_release = _orig_fetch

# ---------------------------------------------------------------------------
# 20. 编码页：批量模式交换语义（R5 B8 回归：交换回的是纯逐行结果，不带行号）
# ---------------------------------------------------------------------------
enc_page.batch_chk.setChecked(True)
enc_page.algo_combo.setCurrentIndex(enc_page.algo_combo.findData("base64"))
enc_page.dec_btn.setChecked(True)
enc_page.in_edit.setPlainText("aGVsbG8=\naGVsbG8=")
enc_page._execute()
_t0 = time.time()
while time.time() - _t0 < 15 and not enc_page.exec_btn.isEnabled():
    app.processEvents()
    time.sleep(0.02)
for _ in range(3):
    app.processEvents()
    time.sleep(0.01)
enc_page._swap()
check("encode batch: swap fills plain outputs without row indexes",
      enc_page.in_edit.toPlainText() == "hello\nhello"
      and enc_page.out_edit.result_text() == "aGVsbG8=\naGVsbG8=",
      f"in={enc_page.in_edit.toPlainText()!r} out={enc_page.out_edit.result_text()!r}")
enc_page.batch_chk.setChecked(False)
enc_page.enc_btn.setChecked(True)
enc_page.in_edit.setPlainText("")
enc_page.out_edit.set_result_text("")

win.close()

print()
if failures:
    print(f"SCENARIOS FAILED: {len(failures)}")
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("SCENARIOS: ALL PASS")
