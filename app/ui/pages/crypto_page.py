"""加密解密页：AES（GCM/CBC/ECB）、ChaCha20-Poly1305、RSA（OAEP 加解密 / PSS 签名验签）。

- 哈希不可逆，明确引导到「哈希计算」页，与加密严格区分。
- ECB / CBC 显示风险标记；GCM 与 ChaCha20 为推荐模式。
- 密钥只在内存中使用，不写入历史记录，也不持久化。
"""

from __future__ import annotations

import base64
import binascii
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core import crypto_tools as ct
from ..widgets import (
    CardHeader,
    IOEditor,
    PageHeader,
    banner,
    btn,
    elapsed_ms,
    io_card,
    make_card,
    set_btn_icon,
    set_chip,
)
from . import PageBase

PAGE_NAME = "加密解密"

ALGO_CHOICES = [
    ("aes-gcm", "AES-256-GCM（推荐）"),
    ("aes-cbc", "AES-CBC"),
    ("aes-ecb", "AES-ECB（不安全）"),
    ("chacha20-poly1305", "ChaCha20-Poly1305（推荐）"),
    ("rsa-oaep", "RSA-OAEP（公钥加密 / 私钥解密）"),
    ("rsa-pss", "RSA-PSS（签名 / 验签）"),
]


def parse_cipher_text(text: str):
    """把用户输入的密文（Base64 或 Hex）还原为字节。"""
    s = (text or "").strip()
    if not s:
        return None, "输入为空：请提供待解密 / 验签的密文"
    compact = "".join(s.split())
    if compact[:5].lower() == "b64:":
        compact = compact[5:]
    try:
        return base64.b64decode(compact, validate=True), ""
    except (binascii.Error, ValueError):
        pass
    try:
        return bytes.fromhex(compact), ""
    except ValueError:
        return None, "无法识别密文格式：请使用 Base64 或 Hex（与加密时的输出格式一致）"


def encode_cipher_text(data: bytes, encoding: str) -> str:
    if encoding == "hex":
        return data.hex()
    return base64.b64encode(data).decode("ascii")


class CryptoPage(PageBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        header = PageHeader(PAGE_NAME, "可逆加密仅在此页。MD5 / SHA 等哈希不可逆，请前往「哈希计算」页 —— 两类操作严格区分。")
        root.addWidget(header)

        # ---- 输入区 ----
        self.in_card, self.in_header, self.in_edit = io_card("输入内容", "0 字符", min_lines=4)
        self.in_edit.textChanged.connect(self._update_in_meta)
        self.in_edit.setProperty("mono", True)
        self.paste_btn = btn("粘贴", "paste")
        set_btn_icon(self.paste_btn, "paste")
        self.paste_btn.clicked.connect(self._paste)
        self.in_clear_btn = btn("清空", "eraser")
        set_btn_icon(self.in_clear_btn, "eraser")
        self.in_clear_btn.clicked.connect(lambda: self.in_edit.setPlainText(""))
        self.in_header.add_button(self.paste_btn)
        self.in_header.add_button(self.in_clear_btn)
        root.addWidget(self.in_card)

        # ---- 操作行 ----
        op_card = make_card()
        op_v = QVBoxLayout(op_card)
        op_v.setContentsMargins(14, 11, 14, 11)
        op_v.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(10)
        algo_lbl = QLabel("算法")
        algo_lbl.setObjectName("dtMeta")
        self.algo_combo = QComboBox()
        for value, text in ALGO_CHOICES:
            self.algo_combo.addItem(text, value)
        self.algo_combo.setMinimumWidth(240)
        self.algo_combo.currentIndexChanged.connect(self._on_algo_change)

        dir_lbl = QLabel("方向")
        dir_lbl.setObjectName("dtMeta")
        self.seg_frame = QFrame()
        self.seg_frame.setObjectName("dtSegFrame")
        seg_h = QHBoxLayout(self.seg_frame)
        seg_h.setContentsMargins(2, 2, 2, 2)
        seg_h.setSpacing(2)
        self.dir_a = QPushButton("加密")
        self.dir_b = QPushButton("解密")
        for b in (self.dir_a, self.dir_b):
            b.setObjectName("dtSeg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dir_a.setChecked(True)
        seg_h.addWidget(self.dir_a)
        seg_h.addWidget(self.dir_b)
        # 互斥：同一时间只有一个方向处于选中态
        self._dir_group = QButtonGroup(self)
        self._dir_group.setExclusive(True)
        self._dir_group.addButton(self.dir_a)
        self._dir_group.addButton(self.dir_b)

        self.exec_btn = btn("执行", "lock", variant="primary")
        set_btn_icon(self.exec_btn, "lock", "accent_fg")
        self.exec_btn.clicked.connect(self._execute)

        row.addWidget(algo_lbl)
        row.addWidget(self.algo_combo)
        row.addWidget(dir_lbl)
        row.addWidget(self.seg_frame)
        row.addStretch(1)
        row.addWidget(self.exec_btn)
        op_v.addLayout(row)
        root.addWidget(op_card)

        # ---- 动态参数区 ----
        self.params_card = make_card()
        self.params_header = CardHeader("密钥与参数", "按所选算法动态显示")
        self.params_inner = QVBoxLayout()
        self.params_inner.setContentsMargins(14, 0, 14, 12)
        self.params_inner.setSpacing(10)
        p_header_wrap = QVBoxLayout()
        p_header_wrap.setContentsMargins(1, 1, 1, 1)
        p_header_wrap.addWidget(self.params_header)
        self.params_card_layout = QVBoxLayout(self.params_card)
        self.params_card_layout.setContentsMargins(1, 1, 1, 1)
        self.params_card_layout.addLayout(p_header_wrap)
        self.params_card_layout.addLayout(self.params_inner)
        root.addWidget(self.params_card)

        # ---- 输出区 ----
        self.out_card, self.out_header, self.out_edit = io_card("输出结果", "", readonly=True, min_lines=4)
        self.copy_btn = btn("复制结果", "copy")
        set_btn_icon(self.copy_btn, "copy")
        self.copy_btn.clicked.connect(self._copy)
        self.save_btn = btn("保存结果", "save")
        set_btn_icon(self.save_btn, "save")
        self.save_btn.clicked.connect(self._save)
        self.out_header.add_button(self.copy_btn)
        self.out_header.add_button(self.save_btn)
        root.addWidget(self.out_card)
        root.addStretch(1)

        self._binary_out = None  # 非文本解密结果的字节缓存
        self._on_algo_change()
        QShortcut(QKeySequence("Ctrl+Return"), self, self._execute)

    # ------------------------------------------------------------------
    def _algo(self) -> str:
        return self.algo_combo.currentData()

    def _direction(self) -> str:
        if self._algo() == "rsa-pss":
            return "verify" if self.dir_b.isChecked() else "sign"
        return "decrypt" if self.dir_b.isChecked() else "encrypt"

    def _update_in_meta(self):
        text = self.in_edit.toPlainText()
        self.in_header.set_meta(f"{len(text):,} 字符" if text else "0 字符")

    def _paste(self):
        from PySide6.QtWidgets import QApplication
        text = QApplication.clipboard().text()
        if text:
            self.in_edit.setPlainText(text)
            self.statusMsg.emit(f"已粘贴剪贴板内容（{len(text):,} 字符）")
        else:
            self.statusMsg.emit("剪贴板为空")

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
                item.layout().deleteLater()

    # ------------------------------------------------------------------
    def _on_algo_change(self):
        self._clear_layout(self.params_inner)
        algo = self._algo()
        if algo.startswith("rsa"):
            self._build_rsa_params(algo)
        else:
            self._build_symmetric_params(algo)
        # 方向文案随算法变化
        is_sign = algo == "rsa-pss"
        a_text, b_text = ("签名", "验签") if is_sign else ("加密", "解密")
        self.dir_a.setText(a_text)
        self.dir_b.setText(b_text)
        self.exec_btn.setIcon(self._lock_icon())

    def _lock_icon(self):
        from .. import icons
        from ..context import CTX
        name = "signature" if self._algo() == "rsa-pss" else "lock"
        return icons.icon(name, CTX.pal()["accent_fg"])

    def _build_symmetric_params(self, algo: str):
        info = ct.ALGORITHMS[algo]
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        key_src_lbl = QLabel("密钥来源")
        key_src_lbl.setObjectName("dtMeta")
        self.src_combo = QComboBox()
        self.src_combo.addItem("口令 + PBKDF2 派生（推荐）", "passphrase")
        self.src_combo.addItem("原始密钥（Hex / Base64）", "raw")
        self.src_combo.currentIndexChanged.connect(self._refresh_symmetric_rows)
        grid.addWidget(key_src_lbl, 0, 0)
        grid.addWidget(self.src_combo, 0, 1)

        keylen_lbl = QLabel("密钥长度")
        keylen_lbl.setObjectName("dtMeta")
        self.keylen_combo = QComboBox()
        for bits in info["sizes"]:
            self.keylen_combo.addItem(f"{bits} 位（AES-{bits}）", bits)
        self.keylen_combo.setCurrentIndex(len(info["sizes"]) - 1)  # 默认选最长（256 位）
        self.keylen_combo.setEnabled(len(info["sizes"]) > 1)
        grid.addWidget(keylen_lbl, 0, 2)
        grid.addWidget(self.keylen_combo, 0, 3)

        self.pass_lbl = QLabel("口令")
        self.pass_lbl.setObjectName("dtMeta")
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_edit.setPlaceholderText("输入口令（不会被保存或写入历史）")
        grid.addWidget(self.pass_lbl, 1, 0)
        grid.addWidget(self.pass_edit, 1, 1)

        self.gen_btn = btn("生成随机密钥", "refresh")
        set_btn_icon(self.gen_btn, "refresh")
        self.gen_btn.setToolTip("生成随机原始密钥并填入密钥框")
        self.gen_btn.clicked.connect(self._gen_key)
        grid.addWidget(self.gen_btn, 1, 2)

        self.key_lbl = QLabel("原始密钥")
        self.key_lbl.setObjectName("dtMeta")
        self.key_edit = QLineEdit()
        self.key_edit.setProperty("mono", True)
        self.key_edit.setPlaceholderText("Hex 或 Base64 密钥（如 hex:9f86d081…），或点击「生成随机密钥」")
        grid.addWidget(self.key_lbl, 2, 0)
        grid.addWidget(self.key_edit, 2, 1)

        self.iter_lbl = QLabel("PBKDF2 迭代")
        self.iter_lbl.setObjectName("dtMeta")
        self.iter_spin = QSpinBox()
        self.iter_spin.setRange(ct.MIN_ITERATIONS, ct.MAX_ITERATIONS)
        self.iter_spin.setSingleStep(10000)
        self.iter_spin.setValue(ct.DEFAULT_ITERATIONS)
        grid.addWidget(self.iter_lbl, 2, 2)
        grid.addWidget(self.iter_spin, 2, 3)

        enc_lbl = QLabel("密文输出")
        enc_lbl.setObjectName("dtMeta")
        self.enc_combo = QComboBox()
        self.enc_combo.addItem("Base64", "base64")
        self.enc_combo.addItem("Hex", "hex")
        grid.addWidget(enc_lbl, 3, 0)
        grid.addWidget(self.enc_combo, 3, 1)

        note_lbl = QLabel("Nonce / IV 每次加密自动随机生成；AEAD 认证 Tag 附加在密文尾部。")
        note_lbl.setObjectName("dtHint")
        note_lbl.setWordWrap(True)
        grid.addWidget(note_lbl, 4, 0, 1, 4)
        grid.setColumnStretch(9, 1)

        self.params_inner.addLayout(grid)
        if info["risk"] == "err":
            self.params_inner.addWidget(banner("err", "⚠ ECB 模式不安全：相同明文块产生相同密文，泄露数据模式，仅限兼容旧系统使用。"))
        elif info["risk"] == "warn":
            self.params_inner.addWidget(banner("warn", "⚠ CBC 模式无认证能力：密文可被篡改而不被发现，建议配合 HMAC 或改用 GCM。"))
        else:
            self.params_inner.addWidget(banner("ok", "✓ 认证加密（AEAD）：密文被篡改时解密将直接失败，推荐日常使用。"))
        self._refresh_symmetric_rows()

    def _refresh_symmetric_rows(self):
        raw_mode = self.src_combo.currentData() == "raw"
        self.pass_edit.setVisible(not raw_mode)
        self.pass_lbl.setVisible(not raw_mode)
        self.key_edit.setVisible(raw_mode)
        self.key_lbl.setVisible(raw_mode)
        self.iter_lbl.setVisible(not raw_mode)
        self.iter_spin.setVisible(not raw_mode)

    def _gen_key(self):
        bits = self.keylen_combo.currentData() if self.keylen_combo.isEnabled() else 256
        r = ct.generate_random_key(bits // 8)
        if r.ok:
            self.src_combo.setCurrentIndex(1)
            self.key_edit.setText("hex:" + r.data)
            self.statusMsg.emit(f"已生成 {bits} 位随机密钥（仅显示一次，请妥善保存）")
        else:
            QMessageBox.warning(self, "生成失败", r.error)

    def _build_rsa_params(self, algo: str):
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        key_lbl = QLabel("RSA 密钥（PEM）")
        key_lbl.setObjectName("dtMeta")
        self.rsa_key_edit = IOEditor()
        self.rsa_key_edit.set_placeholder(
            "-----BEGIN PUBLIC KEY----- 或 -----BEGIN PRIVATE KEY-----\n"
            "可在下方生成密钥对，或导入密钥文件"
        )
        self.rsa_key_edit.setMinimumHeight(96)
        grid.addWidget(key_lbl, 0, 0)
        grid.addWidget(self.rsa_key_edit, 1, 0, 1, 3)

        btns = QHBoxLayout()
        gen_btn = btn("生成密钥对", "refresh")
        set_btn_icon(gen_btn, "refresh")
        gen_btn.clicked.connect(self._gen_rsa)
        imp_btn = btn("导入密钥文件", "upload")
        set_btn_icon(imp_btn, "upload")
        imp_btn.clicked.connect(self._import_rsa)
        exp_btn = btn("导出当前密钥", "save")
        set_btn_icon(exp_btn, "save")
        exp_btn.clicked.connect(self._export_rsa)
        btns.addWidget(gen_btn)
        btns.addWidget(imp_btn)
        btns.addWidget(exp_btn)
        btns.addStretch(1)
        grid.addLayout(btns, 2, 0, 1, 3)

        bits_lbl = QLabel("密钥长度")
        bits_lbl.setObjectName("dtMeta")
        self.rsa_bits_combo = QComboBox()
        self.rsa_bits_combo.addItem("2048 位（默认）", 2048)
        self.rsa_bits_combo.addItem("4096 位", 4096)
        grid.addWidget(bits_lbl, 3, 0)
        grid.addWidget(self.rsa_bits_combo, 3, 1)
        grid.setColumnStretch(9, 1)

        self.params_inner.addLayout(grid)
        if algo == "rsa-pss":
            sig_lbl = QLabel("待验证签名（Base64，仅「验签」方向需要）")
            sig_lbl.setObjectName("dtMeta")
            self.sig_edit = QLineEdit()
            self.sig_edit.setProperty("mono", True)
            self.sig_edit.setPlaceholderText("粘贴签名者给出的 Base64 签名")
            self.params_inner.addWidget(sig_lbl)
            self.params_inner.addWidget(self.sig_edit)
            self.params_inner.addWidget(banner("info", "签名 / 验签使用 RSA-PSS + SHA-256：签名方需要私钥，验签方只需要公钥。"))
        else:
            self.params_inner.addWidget(banner("info", "RSA-OAEP + SHA-256：加密需要对方公钥，解密需要自己的私钥；单次加密上限随密钥长度而定（2048 位约 190 字节），大数据请用 AES + RSA 混合方案。"))
        self.params_inner.addWidget(banner("ok", "✓ 生成密钥对后请立即导出保存私钥；公钥可分发给别人。私钥绝不写入历史记录。"))

    def _gen_rsa(self):
        bits = self.rsa_bits_combo.currentData()
        r = ct.generate_keypair(bits)
        if not r.ok:
            QMessageBox.warning(self, "生成失败", r.error)
            return
        self.rsa_key_edit.setPlainText(r.data["private_pem"])
        self.statusMsg.emit(f"已生成 {bits} 位 RSA 密钥对")
        QMessageBox.information(
            self, "密钥对已生成",
            "私钥已填入密钥框，请立即导出保存。\n\n公钥（分发给对方使用）：\n\n" + r.data["public_pem"],
        )

    def _import_rsa(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入密钥文件", "", "PEM 密钥 (*.pem *.key *.pub *.txt);;所有文件 (*.*)")
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "导入失败", f"无法读取文件：{exc}")
            return
        self.rsa_key_edit.setPlainText(text)
        kind = "私钥" if ct.looks_like_private_key(text) else "公钥"
        self.statusMsg.emit(f"已导入{kind}：{Path(path).name}")

    def _export_rsa(self):
        text = self.rsa_key_edit.toPlainText().strip()
        if not text:
            self.statusMsg.emit("当前没有可导出的密钥")
            return
        default = "private.pem" if ct.looks_like_private_key(text) else "public.pem"
        path, _ = QFileDialog.getSaveFileName(self, "导出密钥", default, "PEM 密钥 (*.pem);;所有文件 (*.*)")
        if not path:
            return
        try:
            Path(path).write_text(text, encoding="utf-8")
            self.statusMsg.emit(f"密钥已导出：{Path(path).name}")
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", f"无法写入文件：{exc}")

    # ------------------------------------------------------------------
    def _collect_symmetric_cfg(self) -> dict:
        return {
            "algorithm": self._algo(),
            "key_size": self.keylen_combo.currentData(),
            "key_source": self.src_combo.currentData(),
            "passphrase": self.pass_edit.text(),
            "raw_key": self.key_edit.text(),
            "pbkdf2_iterations": self.iter_spin.value(),
        }

    def _show_result_text(self, data: bytes):
        try:
            text = data.decode("utf-8")
            self.out_edit.set_result_text(text)
            self._binary_out = None
            return True
        except UnicodeDecodeError:
            self.out_edit.setPlainText(
                f"[二进制结果，共 {len(data):,} 字节，前 64 字节预览：]\n{data[:64].hex(' ')}\n\n请点击「保存结果」导出完整数据。"
            )
            self.out_edit._full_text = ""
            self._binary_out = data
            return False

    def _execute(self):
        import time as _time

        t0 = _time.perf_counter()
        algo = self._algo()
        direction = self._direction()
        text = self.in_edit.toPlainText()
        self._binary_out = None

        # ---- RSA ----
        if algo.startswith("rsa"):
            key_text = self.rsa_key_edit.toPlainText()
            if algo == "rsa-oaep":
                if direction == "encrypt":
                    if not text:
                        set_chip(self.out_header.chip_lbl, "✕ 输入为空：请输入待加密明文", "err")
                        return
                    r = ct.rsa_encrypt(key_text, text.encode("utf-8"))
                    if not r.ok:
                        set_chip(self.out_header.chip_lbl, f"✕ {r.error}", "err")
                        self.statusMsg.emit(f"加密失败：{r.error}")
                        return
                    self.out_edit.set_result_text(encode_cipher_text(r.data, "base64"))
                    set_chip(self.out_header.chip_lbl, f"✓ 加密成功 · {r.meta['bits']} 位公钥 · {elapsed_ms(t0)} 毫秒", "ok")
                    self.historyAdd.emit(PAGE_NAME, "RSA-OAEP 加密", f"{r.meta['in_bytes']} 字节明文 → {r.meta['out_bytes']} 字节密文")
                else:
                    data, err = parse_cipher_text(text)
                    if err:
                        set_chip(self.out_header.chip_lbl, f"✕ {err}", "err")
                        return
                    r = ct.rsa_decrypt(key_text, data)
                    if not r.ok:
                        set_chip(self.out_header.chip_lbl, f"✕ {r.error}", "err")
                        self.statusMsg.emit(f"解密失败：{r.error}")
                        return
                    is_text = self._show_result_text(r.data)
                    set_chip(self.out_header.chip_lbl, f"✓ 解密成功 · {r.meta['out_bytes']:,} 字节明文 · {elapsed_ms(t0)} 毫秒", "ok")
                    self.historyAdd.emit(PAGE_NAME, "RSA-OAEP 解密", f"{len(data)} 字节密文 → {r.meta['out_bytes']} 字节明文")
            else:  # rsa-pss
                if direction == "sign":
                    if not text:
                        set_chip(self.out_header.chip_lbl, "✕ 输入为空：请输入待签名原文", "err")
                        return
                    r = ct.rsa_sign(key_text, text.encode("utf-8"))
                    if not r.ok:
                        set_chip(self.out_header.chip_lbl, f"✕ {r.error}", "err")
                        return
                    self.out_edit.set_result_text(encode_cipher_text(r.data, "base64"))
                    set_chip(self.out_header.chip_lbl, f"✓ 签名成功 · {r.meta['bits']} 位私钥 · {elapsed_ms(t0)} 毫秒", "ok")
                    self.historyAdd.emit(PAGE_NAME, "RSA-PSS 签名", f"{r.meta['out_bytes']} 字节签名")
                else:
                    if not text:
                        set_chip(self.out_header.chip_lbl, "✕ 输入为空：请输入被签名的原文", "err")
                        return
                    # 验签：原文是任意文本，直接按 UTF-8 字节参与校验；只有签名需要 Base64 解析
                    data = text.encode("utf-8")
                    sig, sig_err = parse_cipher_text(self.sig_edit.text())
                    if sig_err:
                        set_chip(self.out_header.chip_lbl, f"✕ 签名格式无效：{sig_err}", "err")
                        return
                    r = ct.rsa_verify(key_text, data, sig)
                    if not r.ok:
                        set_chip(self.out_header.chip_lbl, f"✕ {r.error}", "err")
                        return
                    ok = r.data
                    set_chip(self.out_header.chip_lbl,
                             "✓ 验签通过：签名有效，原文未被篡改" if ok else "✕ 验签失败：签名与原文不匹配", "ok" if ok else "err")
                    self.historyAdd.emit(PAGE_NAME, "RSA-PSS 验签", "通过" if ok else "未通过")
            self.statusMsg.emit(f"操作完成 · {elapsed_ms(t0)} 毫秒")
            return

        # ---- 对称 ----
        if not text:
            set_chip(self.out_header.chip_lbl, "✕ 输入为空：请输入待处理内容", "err")
            return
        cfg = self._collect_symmetric_cfg()
        if direction == "encrypt":
            data = text.encode("utf-8")
            r = ct.encrypt(data, cfg)
            if not r.ok:
                set_chip(self.out_header.chip_lbl, f"✕ {r.error}", "err")
                self.statusMsg.emit(f"加密失败：{r.error}")
                return
            self.out_edit.set_result_text(encode_cipher_text(r.data, self.enc_combo.currentData()))
            warn = r.meta.get("warning")
            set_chip(self.out_header.chip_lbl,
                     f"✓ 加密成功 · {r.meta['label']} {r.meta['key_size']} 位 · {elapsed_ms(t0)} 毫秒"
                     + (" ⚠ " + warn if warn else ""),
                     r.meta["risk"] if r.meta["risk"] != "ok" else "ok")
            self.historyAdd.emit(PAGE_NAME, f"{r.meta['label']} {r.meta['key_size']} 位加密",
                                 f"{r.meta['in_bytes']} 字节明文 → {r.meta['out_bytes']} 字节密文（密钥未记录）")
            self.statusMsg.emit(f"加密完成 · {elapsed_ms(t0)} 毫秒")
        else:
            data, err = parse_cipher_text(text)
            if err:
                set_chip(self.out_header.chip_lbl, f"✕ {err}", "err")
                return
            r = ct.decrypt(data, cfg)
            if not r.ok:
                set_chip(self.out_header.chip_lbl, f"✕ {r.error}", "err")
                self.statusMsg.emit(f"解密失败：{r.error}")
                return
            is_text = self._show_result_text(r.data)
            set_chip(self.out_header.chip_lbl, f"✓ 解密成功 · {r.meta['out_bytes']:,} 字节明文 · {elapsed_ms(t0)} 毫秒", "ok")
            self.historyAdd.emit(PAGE_NAME, f"{r.meta['label']} 解密", f"{len(data)} 字节密文 → {r.meta['out_bytes']} 字节明文（密钥未记录）")
            self.statusMsg.emit(f"解密完成 · {elapsed_ms(t0)} 毫秒")

    def _copy(self):
        from PySide6.QtWidgets import QApplication
        text = self.out_edit.result_text()
        if not text:
            self.statusMsg.emit("没有可复制的结果")
            return
        QApplication.clipboard().setText(text)
        self.statusMsg.emit(f"已复制完整结果（{len(text):,} 字符）")

    def _save(self):
        if self._binary_out is not None:
            path, _ = QFileDialog.getSaveFileName(self, "保存二进制结果", "devtoolkit-output.bin", "所有文件 (*.*)")
            if path:
                try:
                    Path(path).write_bytes(self._binary_out)
                    self.statusMsg.emit(f"已保存二进制结果（{len(self._binary_out):,} 字节）")
                except OSError as exc:
                    QMessageBox.warning(self, "保存失败", f"无法写入文件：{exc}")
            return
        text = self.out_edit.result_text()
        if not text:
            self.statusMsg.emit("没有可保存的结果")
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存结果", "devtoolkit-cipher.txt", "文本文件 (*.txt);;所有文件 (*.*)")
        if not path:
            return
        try:
            Path(path).write_text(text, encoding="utf-8")
            self.statusMsg.emit(f"结果已保存：{Path(path).name}")
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", f"无法写入文件：{exc}")

    def on_theme_changed(self, theme: str):
        from ..widgets import recolor_icons
        recolor_icons(self)
        self.exec_btn.setIcon(self._lock_icon())
