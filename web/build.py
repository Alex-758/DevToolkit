#!/usr/bin/env python
"""把 web/src/*.js + 页面模板内联成单个 HTML（file:// 可直接打开，无需服务器）。

用法：python web/build.py
产物：web/dist/DevToolkit.html
"""
from __future__ import annotations

import html
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"
DIST = ROOT / "dist"

# 加载顺序即依赖顺序（后者消费前者的 DT.* 命名空间）
SCRIPTS = ["core.js", "sha3.js", "chacha.js", "codecs.js", "hash.js",
           "crypto.js", "compress.js", "smart.js", "selftest.js", "app.js"]


def read(name: str) -> str:
    p = SRC / name
    if not p.is_file():
        raise SystemExit(f"缺少源文件：{p}")
    return p.read_text(encoding="utf-8")


def main() -> int:
    scripts = []
    for name in SCRIPTS:
        code = read(name)
        # </script> 出现在字符串里会提前关闭标签
        code = code.replace("</script>", "<\\/script>")
        scripts.append(f"<script>\n{code}\n</script>")
    css = read("style.css")
    tpl = read("index.html")

    out_html = tpl.replace("/*__CSS__*/", css).replace("<!--__SCRIPTS__-->", "\n".join(scripts))

    DIST.mkdir(parents=True, exist_ok=True)
    target = DIST / "DevToolkit.html"
    target.write_text(out_html, encoding="utf-8")

    size_kb = target.stat().st_size / 1024
    # 基本完整性校验：不允许残留占位符或外部引用
    problems = []
    if "/*__CSS__*/" in out_html or "<!--__SCRIPTS__-->" in out_html:
        problems.append("占位符未替换")
    for needle in ('src="http', "href=\"http", "src='http", "@import url("):
        if needle in out_html:
            problems.append(f"检测到外部引用：{needle}")

    print(f"built: {target}  ({size_kb:.1f} KB)")
    print(f"scripts: {len(scripts)}  css: {len(css)/1024:.1f} KB")
    if problems:
        for p in problems:
            print("PROBLEM:", p)
        return 1
    print("external references: NONE  (完全离线单文件)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
