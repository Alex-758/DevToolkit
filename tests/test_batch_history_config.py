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
