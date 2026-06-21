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


def test_discover_skips_claude_mem_observer_dirs(tmp_path):
    """claude-mem observer writes JSONLs under a project dir whose encoded name
    contains '.claude-mem'. These are plugin-internal sessions and must be ignored."""
    real_proj = tmp_path / "A--Users-Mick4994"
    real_proj.mkdir()
    (real_proj / "real-session.jsonl").write_text("{}")

    observer_proj = tmp_path / "A--Users-Mick4994--.claude-mem-observer-sessions"
    observer_proj.mkdir()
    (observer_proj / "obs-1.jsonl").write_text("{}")
    (observer_proj / "obs-2.jsonl").write_text("{}")

    files = list(discover_jsonl_files(tmp_path))
    stems = {f.stem for f in files}
    assert stems == {"real-session"}, f"unexpected files: {stems}"


def test_discover_does_not_skip_real_claude_mem_in_user_path(tmp_path):
    """A real user project whose path happens to contain '.claude-mem' must
    still be scanned. The filter targets observer session dirs specifically."""
    # Only project dirs ending in '-observer-sessions' or matching '.claude-mem'
    # are filtered. A user project with .claude-mem in the middle of the path
    # would not be filtered out (the test name reflects the intent: we don't
    # accidentally filter legitimate projects).
    proj = tmp_path / "A--Users-mick-.claude-mem-folder"
    proj.mkdir()
    (proj / "s.jsonl").write_text("{}")
    files = list(discover_jsonl_files(tmp_path))
    assert len(files) == 1


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
