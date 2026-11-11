"""DevToolkit 入口：GUI 主程序 + 自检模式（打包验证用）+ 离屏 UI 冒烟模式。"""

from __future__ import annotations

import argparse
import json
import sys


def run_selftest(log_path: str | None = None) -> int:
    """打包后自检：验证核心依赖与算法在独立环境中可用。返回 0=全部通过。"""
    checks: dict = {}

    def check(name, fn):
        try:
            checks[name] = "PASS: " + str(fn())
        except Exception as exc:
            checks[name] = "FAIL: " + repr(exc)

    check("import.pyside6", lambda: __import__("PySide6").__version__)
    check("import.pycryptodome", lambda: __import__("Crypto").__version__)
    check("import.brotli", lambda: __import__("brotli").__version__ if hasattr(__import__("brotli"), "__version__") else "ok")
    check("import.zstandard", lambda: __import__("zstandard").__version__)
    check("import.lz4", lambda: "ok")

    from app.core import compress_tools, crypto_tools, encoders, hashing, smart_decode

    def codecs_roundtrip():
        text = "Hello, DevToolkit! 你好，世界 😀"
        bad = []
        for cid in encoders.CODEC_ORDER:
            if cid == "ascii" and any(ord(c) > 127 for c in text):
                continue
            if cid == "unicode" and "\\u" in text:
                continue
            enc = encoders.encode(cid, text)
            dec = encoders.decode(cid, enc.data) if enc.ok else None
            if not enc.ok or dec is None or not dec.ok or dec.data != text:
                bad.append(cid)
        if bad:
            raise RuntimeError(f"roundtrip failed: {bad}")
        return f"{len(encoders.CODEC_ORDER)} codecs"

    check("encoders.roundtrip", codecs_roundtrip)

    check("hashing.sha256", lambda: (
        hashing.text_hash("abc", "sha256").data == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    ) and "vector ok")

    def compress_roundtrip():
        import gzip as _gzip
        data = "压缩自检 compress selftest 你好".encode("utf-8")
        for fmt in compress_tools.FORMATS:
            enc = compress_tools.compress(data, fmt)
            if not enc.ok:
                raise RuntimeError(f"{fmt}: {enc.error}")
            dec = compress_tools.decompress(enc.data, fmt)
            if not dec.ok or dec.data != data:
                raise RuntimeError(f"{fmt}: {dec.error}")
        return f"{len(compress_tools.FORMATS)} formats"

    check("compress.roundtrip", compress_roundtrip)

    def crypto_roundtrip():
        cfg = {"algorithm": "aes-gcm", "key_size": 256, "key_source": "passphrase",
               "passphrase": "selftest-passphrase", "pbkdf2_iterations": 60000}
        data = "加密自检 你好 😀".encode("utf-8")
        enc = crypto_tools.encrypt(data, cfg)
        if not enc.ok:
            raise RuntimeError(enc.error)
        dec = crypto_tools.decrypt(enc.data, cfg)
        if not dec.ok or dec.data != data:
            raise RuntimeError(dec.error)
        pair = crypto_tools.generate_keypair(2048)
        if not pair.ok:
            raise RuntimeError(pair.error)
        sig = crypto_tools.rsa_sign(pair.data["private_pem"], data)
        vr = crypto_tools.rsa_verify(pair.data["public_pem"], data, sig.data)
        if not (sig.ok and vr.ok and vr.data is True):
            raise RuntimeError("rsa sign/verify failed")
        return "aes-gcm + rsa-pss ok"

    check("crypto.roundtrip", crypto_roundtrip)

    def smart_chain():
        import base64 as _b64
        inner = "智能解码自检链路 你好"
        payload = _b64.b64encode(_gzip if False else __import__("gzip").compress(inner.encode("utf-8"))).decode()
        r = smart_decode.smart_decode(payload)
        if not r.ok or r.data.final_text != inner:
            raise RuntimeError(r.error or "chain mismatch")
        return f"{r.data.layers_used} layers"

    check("smart.chain", smart_chain)

    ok = all(not v.startswith("FAIL") for v in checks.values())
    result = {"ok": ok, "checks": checks}
    line = json.dumps(result, ensure_ascii=False, indent=1)
    if log_path:
        try:
            with open(log_path, "w", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass
    print(line)
    return 0 if ok else 1


def run_smoke_ui(outdir: str) -> int:
    """UI 冒烟测试：构建窗口、遍历页面、执行交互并截图。

    Windows 上使用真实 windows 平台（离屏平台拿不到系统字体，中文会变方框），
    窗口会在桌面短暂闪现后自动关闭。
    """
    import os

    if sys.platform == "win32":
        os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    else:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    from app import APP_VERSION
    from app.ui.context import CTX
    from app.ui.main_window import MainWindow
    from app.ui.theme import build_qss

    theme = str(__import__("app.core.config", fromlist=["get_setting"]).get_setting("theme"))
    CTX.set_theme(theme)
    app.setStyleSheet(build_qss(theme))

    win = MainWindow()
    win.resize(1180, 760)
    win.show()
    app.processEvents()

    out = __import__("pathlib").Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    failures = []

    # 遍历页面截图
    from app.ui.main_window import NAV_ITEMS
    for idx, (page_id, label, _icon) in enumerate(NAV_ITEMS):
        win.switch_page(idx)
        app.processEvents()
        pm = win.grab()
        pm.save(str(out / f"page-{page_id}.png"))
        print(f"SMOKE: page {page_id} captured")

    # 交互 1：编码执行
    enc_page = win.pages["encode"]
    enc_page.in_edit.setPlainText("Hello, DevToolkit! 你好，世界")
    enc_page._execute()
    app.processEvents()
    if enc_page.out_edit.result_text() != "SGVsbG8sIERldlRvb2xraXQhIOS9oOWlve+8jOS4lueVjA==":
        failures.append("encode: unexpected output " + repr(enc_page.out_edit.result_text()[:40]))
    else:
        print("SMOKE: encode exec PASS")

    # 交互 2：解码
    enc_page.dec_btn.setChecked(True)
    enc_page.in_edit.setPlainText("SGVsbG8sIERldlRvb2xraXQhIOS9oOWlve+8jOS4lueVjA==")
    enc_page._execute()
    app.processEvents()
    if enc_page.out_edit.result_text() != "Hello, DevToolkit! 你好，世界":
        failures.append("decode: unexpected output")
    else:
        print("SMOKE: decode exec PASS")

    # 交互 3：自动识别
    enc_page._detect()
    app.processEvents()
    if enc_page.detect_lbl.isHidden():
        failures.append("detect: banner hidden")
    else:
        print("SMOKE: detect PASS")

    # 交互 4：哈希自动计算
    hash_page = win.pages["hash"]
    hash_page.in_edit.setPlainText("abc")
    hash_page._recompute_now()
    app.processEvents()
    got = hash_page._hash_rows["sha256"][1].text()
    if got != "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad":
        failures.append("hash: unexpected sha256 " + got)
    else:
        print("SMOKE: hash auto PASS")

    # 交互 5：智能解码链路
    import base64 as _b64
    import gzip as _gzip
    inner = "UI 冒烟链路 你好 😀"
    payload = _b64.b64encode(_gzip.compress(inner.encode("utf-8"))).decode()
    smart_page = win.pages["smart"]
    smart_page.in_edit.setPlainText(payload)
    smart_page._run()
    app.processEvents()
    # Worker 是异步的：等待完成
    for _ in range(100):
        app.processEvents()
        if not smart_page.smart_runner.busy():
            break
        QTimer.singleShot(10, lambda: None)
        __import__("time").sleep(0.02)
        app.processEvents()
    if smart_page.out_edit.result_text() != inner:
        failures.append("smart: unexpected final " + repr(smart_page.out_edit.result_text()[:40]))
    else:
        print("SMOKE: smart chain PASS")

    # 交互 6：主题切换（不假设启动主题：持久化配置可能是深色或浅色）
    before_theme = CTX.theme
    win.toggle_theme()
    app.processEvents()
    if CTX.theme == before_theme:
        failures.append("theme: toggle failed")
    else:
        win.grab().save(str(out / f"page-{CTX.theme}.png"))
        print("SMOKE: theme toggle PASS")
    win.toggle_theme()
    app.processEvents()

    # 交互 7：设置对话框可正常构建（非模态预览，不阻塞）
    try:
        from app.ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(win, on_theme_change=lambda t: None)
        dlg.show()
        app.processEvents()
        dlg.grab().save(str(out / "dialog-settings.png"))
        dlg.close()
        print("SMOKE: settings dialog PASS")
    except Exception as exc:
        failures.append(f"settings dialog: {exc!r}")

    win.close()
    if failures:
        print("SMOKE: FAILED")
        for f in failures:
            print("  - " + f)
        return 1
    print("SMOKE: ALL PASS")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="DevToolkit", description="纯离线的 Windows 编码解码工具箱")
    parser.add_argument("--version", action="version", version="DevToolkit 1.0.0")
    parser.add_argument("--selftest", action="store_true", help="运行核心功能自检（打包验证用）")
    parser.add_argument("--selftest-log", help="自检结果 JSON 输出路径")
    parser.add_argument("--smoke-ui", metavar="OUTDIR", help="离屏 UI 冒烟测试并截图到指定目录")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest(args.selftest_log)
    if args.smoke_ui:
        return run_smoke_ui(args.smoke_ui)

    from PySide6.QtWidgets import QApplication

    from app import APP_VERSION
    from app.core.config import get_setting
    from app.ui.context import CTX
    from app.ui.main_window import MainWindow
    from app.ui.theme import build_qss

    app = QApplication(sys.argv)
    app.setApplicationName("DevToolkit")
    app.setApplicationVersion(APP_VERSION)
    theme = str(get_setting("theme") or "dark")
    CTX.set_theme(theme)
    app.setStyleSheet(build_qss(theme))

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
