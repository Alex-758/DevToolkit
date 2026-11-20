"""批量处理、历史记录、配置存储测试（历史与配置使用隔离的临时目录）。"""

import pytest

from app.core import batch, config, history


@pytest.fixture(autouse=True)
def isolated_appdata(tmp_path, monkeypatch):
    """把 APPDATA 指向临时目录，避免污染真实用户数据。"""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    yield


# ---------------------------------------------------------------------------
# 批量处理
# ---------------------------------------------------------------------------

def test_batch_base64_encode():
    text = "line one\nline two\n\nline three"
    r = batch.batch_encode("base64", "encode", text)
    assert r.ok and r.meta["total"] == 3 and r.meta["failed"] == 0
    rows = r.data
    assert rows[0].output == batch.batch_encode("base64", "encode", "line one").data[0].output


def test_batch_roundtrip_per_line():
    text = "第一行\nsecond\n123"
    enc = batch.batch_encode("base64", "encode", text)
    joined = "\n".join(r.output for r in enc.data)
    dec = batch.batch_encode("base64", "decode", joined)
    assert dec.ok
    assert [r.output for r in dec.data] == ["第一行", "second", "123"]


def test_batch_error_rows_preserved():
    text = "SGVsbG8=\n!!!not-base64!!!\nYWJj"
    r = batch.batch_encode("base64", "decode", text)
    assert r.ok and r.meta["total"] == 3 and r.meta["failed"] == 1
    rows = r.data
    assert rows[0].ok and rows[1].error and rows[2].ok


def test_batch_hash_lines():
    text = "a\nb\n"
    r = batch.batch_hash(text, "sha256")
    assert r.ok and r.meta["total"] == 2
    from app.core import hashing
    assert r.data[0].output == hashing.text_hash("a", "sha256").data


def test_batch_skip_empty_toggle():
    from app.core.results import Result
    r1 = batch.process_lines("a\n\nb", lambda ln: Result.success(ln.upper()), skip_empty=True)
    assert r1.meta["total"] == 2
    r2 = batch.process_lines("a\n\nb", lambda ln: Result.success(ln.upper()), skip_empty=False)
    assert r2.meta["total"] == 3


def test_batch_too_many_lines():
    text = "\n".join("x" for _ in range(batch.MAX_LINES + 1))
    assert not batch.batch_encode("base64", "encode", text).ok


def test_format_rows():
    from app.core.results import Result
    r = batch.process_lines("ok\n错误行！！！", lambda ln: Result.success(ln) if len(ln) < 5 else Result.failure("行太长"))
    out = batch.format_rows(r.data)
    assert out.startswith("1  ok")
    assert "✕" in out


# ---------------------------------------------------------------------------
# 历史记录
# ---------------------------------------------------------------------------

def test_history_add_and_list():
    assert history.add_entry("编码解码", "Base64 编码", "34 B → 48 字符") is True
    entries = history.list_entries()
    assert len(entries) == 1
    assert entries[0]["op"] == "Base64 编码"
    assert entries[0]["page"] == "编码解码"


def test_history_limit():
    for i in range(50):
        history.add_entry("测试", f"op-{i}", f"detail-{i}", limit=10)
    assert len(history.list_entries()) == 10
    assert history.list_entries()[0]["op"] == "op-49"  # 最新在前


def test_history_long_detail_truncated():
    history.add_entry("测试", "op", "x" * 500)
    assert len(history.list_entries()[0]["detail"]) <= history.MAX_DETAIL_LEN + 1


def test_history_remove_and_clear():
    history.add_entry("测试", "a", "1")
    history.add_entry("测试", "b", "2")
    assert history.remove_entry(0) is True
    assert history.list_entries()[0]["op"] == "a"
    assert history.clear_entries() is True
    assert history.list_entries() == []
    assert history.remove_entry(99) is False


def test_favorites_toggle():
    assert history.toggle_favorite("codec", "base64") is True
    assert history.is_favorite("codec", "base64") is True
    assert history.toggle_favorite("codec", "base64") is False
    assert history.is_favorite("codec", "base64") is False
    # 去重
    history.add_favorite("codec", "hex")
    history.add_favorite("codec", "hex")
    assert len(history.list_favorites()) == 1


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

def test_settings_defaults_and_roundtrip():
    s = config.load_settings()
    assert s["theme"] == "dark" and s["max_layers"] == 5
    s["theme"] = "light"
    s["max_layers"] = 8
    assert config.save_settings(s) is True
    s2 = config.load_settings()
    assert s2["theme"] == "light" and s2["max_layers"] == 8


def test_settings_corrupt_file_returns_defaults():
    path = config.get_settings_path()
    path.write_text("{corrupt json!!", encoding="utf-8")
    s = config.load_settings()
    assert s["theme"] == "dark"


def test_setting_helpers():
    assert config.set_setting("history_limit", 123) is True
    assert config.get_setting("history_limit") == 123


# ---------------------------------------------------------------------------
# 配置清洗（R1 修复回归：手改 JSON 非法值不得导致下游 int() 崩溃）
# ---------------------------------------------------------------------------

def test_config_garbage_types_fall_back_to_defaults():
    config.set_setting("max_layers", "abc")
    config.set_setting("decompress_cap_mb", "not-a-number")
    config.set_setting("history_limit", None)
    s = config.load_settings()
    assert s["max_layers"] == 5
    assert s["decompress_cap_mb"] == 512
    assert s["history_limit"] == 200


def test_config_out_of_range_values_are_clamped():
    config.set_setting("max_layers", 999)
    config.set_setting("decompress_cap_mb", 0)
    config.set_setting("history_limit", 5)
    s = config.load_settings()
    assert s["max_layers"] == 10
    assert s["decompress_cap_mb"] == 16
    assert s["history_limit"] == 10


def test_config_invalid_theme_and_flag():
    config.set_setting("theme", "blue")
    config.set_setting("batch_skip_empty", "yes-anything")
    s = config.load_settings()
    assert s["theme"] == "dark"
    assert s["batch_skip_empty"] is True


def test_config_save_also_sanitizes():
    assert config.save_settings({"theme": "neon", "max_layers": "x"}) is True
    s = config.load_settings()
    assert s["theme"] == "dark"
    assert s["max_layers"] == 5


def test_config_downstream_int_never_raises():
    """设置对话框 / 压缩页 / 智能解码页的 int(config.get_setting(...)) 不得抛异常。"""
    for key in ("max_layers", "decompress_cap_mb", "history_limit"):
        config.set_setting(key, "garbage-{key}")
        int(config.get_setting(key) or (5 if key == "max_layers" else 512 if key == "decompress_cap_mb" else 200))


# ---------------------------------------------------------------------------
# R5 回归修复：跨进程文件锁（B6）/ limit 类型清洗（补充）
# ---------------------------------------------------------------------------

import json  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

_PROJ_ROOT = Path(__file__).resolve().parent.parent


def test_history_limit_weird_values_never_raise():
    for lim in ("abc", None, 0, -5, 10.7):
        assert history.add_entry("p", "op", "d", limit=lim) is True
        assert isinstance(history.list_entries(limit=lim), list)


def test_history_multiprocess_no_lost_updates(tmp_path):
    """B6：两进程各写 60 条历史，跨进程锁保证互不覆盖。"""
    code = (
        "import os, sys\n"
        "os.environ['APPDATA'] = sys.argv[1]\n"
        "sys.path.insert(0, sys.argv[2])\n"
        "from app.core import history\n"
        "for i in range(60):\n"
        "    if not history.add_entry('p', 'op', sys.argv[3] + str(i)):\n"
        "        sys.exit(1)\n"
        "print('ok')\n"
    )
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(tmp_path), str(_PROJ_ROOT), tag],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        for tag in ("A", "B")
    ]
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, err.decode(errors="replace")[:300]
    n = len(history.list_entries(1000))
    assert n == 120, f"两进程各写 60 条，应共存 120 条，实际 {n}"


def test_settings_multiprocess_set_different_keys(tmp_path):
    """B6：两进程各 set_setting 不同键，读-改-写互不覆盖。"""
    code = (
        "import os, sys\n"
        "os.environ['APPDATA'] = sys.argv[1]\n"
        "sys.path.insert(0, sys.argv[2])\n"
        "from app.core import config\n"
        "assert config.set_setting(sys.argv[3], sys.argv[4])\n"
        "print('ok')\n"
    )
    jobs = [("max_layers", "7"), ("theme", "light")]
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(tmp_path), str(_PROJ_ROOT), k, v],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        for k, v in jobs
    ]
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, err.decode(errors="replace")[:300]
    s = config.load_settings()
    assert s["max_layers"] == 7 and s["theme"] == "light", s


def test_corrupt_json_with_non_dict_entries_never_raises():
    """R6 N10/N11：合法 JSON list 但元素非 dict（手改/损坏）不得崩溃。

    曾在 add_favorite / is_favorite / 历史页 _refresh 抛 AttributeError，
    且发生在 UI 线程（点击收藏按钮即触发）。
    """
    hp = config.get_history_path()
    hp.write_text(json.dumps(["a string entry", 42, {"page": "encode", "op": "x", "detail": "d", "ts": "01-01"}]),
                  encoding="utf-8")
    assert isinstance(history.list_entries(), list)
    assert history.add_entry("p", "op", "d") is True

    fp = config.get_favorites_path()
    fp.write_text(json.dumps(["not-a-dict", 7]), encoding="utf-8")
    assert history.add_favorite("codec", "base64") is True
    assert history.is_favorite("codec", "base64") is True
    assert history.toggle_favorite("codec", "base64") is False
    assert history.list_favorites() == [{"kind": "codec", "target": "base64"}] or all(
        isinstance(f, dict) for f in history.list_favorites())
