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
check("swap: output to input", enc_page.in_edit.toPlainText().startswith("1  line-a"))

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

win.close()

print()
if failures:
    print(f"SCENARIOS FAILED: {len(failures)}")
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("SCENARIOS: ALL PASS")
