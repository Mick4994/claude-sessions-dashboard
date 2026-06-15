import shutil
from pathlib import Path

from src.collector.session_scanner import discover_jsonl_files, last_entry_timestamp

FIXTURE = Path(__file__).parent / "fixtures" / "projects"


def test_discover_finds_all_jsonl(tmp_path):
    target = tmp_path / "projects"
    shutil.copytree(FIXTURE, target)
    files = list(discover_jsonl_files(target))
    assert len(files) == 3
    assert {f.stem for f in files} == {"sess-A", "sess-B", "sess-C"}


def test_discover_empty_dir(tmp_path):
    files = list(discover_jsonl_files(tmp_path))
    assert files == []


def test_discover_skips_tool_results_subdir(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "sess-A.jsonl").write_text("{}")
    (proj / "tool-results").mkdir()
    (proj / "tool-results" / "x.jsonl").write_text("{}")
    files = list(discover_jsonl_files(tmp_path))
    assert len(files) == 1
    assert files[0].stem == "sess-A"


def test_last_entry_timestamp_known(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text(
        '{"type":"last-prompt","sessionId":"s"}\n'
        '{"type":"user","timestamp":"2026-06-15T10:30:00Z","sessionId":"s"}\n'
    )
    ts = last_entry_timestamp(p)
    assert ts is not None
    import datetime

    expected = datetime.datetime(2026, 6, 15, 10, 30, 0, tzinfo=datetime.UTC).timestamp()
    assert abs(ts - expected) < 60


def test_last_entry_timestamp_no_timestamp_field(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text('{"type":"user","message":{"role":"user","content":"hi"}}\n')
    ts = last_entry_timestamp(p)
    assert ts is None


def test_last_entry_timestamp_empty_file(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text("")
    ts = last_entry_timestamp(p)
    assert ts is None
