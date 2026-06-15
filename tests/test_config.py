from src.utils.config import Config


def test_defaults():
    cfg = Config.default()
    assert cfg.poll_interval_ms == 2000
    assert cfg.stale_after_minutes == 30
    assert cfg.recent_seconds == 60
    assert cfg.context_max_tokens == 1_000_000
    assert cfg.collapsed_opacity == 0.8
    assert cfg.expanded_opacity == 1.0
    assert cfg.auto_start is True


def test_from_dict_partial():
    cfg = Config.from_dict({"general": {"poll_interval_ms": 500}})
    assert cfg.poll_interval_ms == 500
    assert cfg.stale_after_minutes == 30  # default


def test_round_trip():
    cfg = Config.default()
    d = cfg.to_dict()
    cfg2 = Config.from_dict(d)
    assert cfg == cfg2


def test_from_file_missing(tmp_path):
    p = tmp_path / "config.ini"
    cfg = Config.from_file(p)
    assert cfg.poll_interval_ms == 2000  # all defaults
