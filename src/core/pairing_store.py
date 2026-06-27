"""卡片右键手动配对的持久化存储（session_id → 终端 hwnd）。

hwnd 在 WT 重启后会变，所以同时保存 class + title，hwnd 失效时按 title 重新匹配。
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile
from pathlib import Path


class PairingStore:
    """线程不安全，单实例即可（dashboard 单进程）。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._cache: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as _f:
                _data = json.load(_f)
            self._cache = _data.get("pairings", {})
        except (OSError, json.JSONDecodeError):
            self._cache = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        _data = {
            "pairings": self._cache,
            "saved_at": _dt.datetime.now().isoformat(timespec="seconds"),
        }
        # 原子写：先写临时文件，再 rename
        _fd, _tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(_fd, "w", encoding="utf-8") as _f:
                json.dump(_data, _f, indent=2, ensure_ascii=False)
            os.replace(_tmp, self._path)
        except Exception:
            try:
                os.unlink(_tmp)
            except OSError:
                pass
            raise

    def get(self, session_id: str) -> dict | None:
        """返回 {hwnd, title, class, paired_at} 或 None。"""
        return self._cache.get(session_id)

    def set(self, session_id: str, hwnd: int, title: str, class_name: str) -> None:
        self._cache[session_id] = {
            "hwnd": hwnd,
            "title": title,
            "class": class_name,
            "paired_at": _dt.datetime.now().isoformat(timespec="seconds"),
        }
        self._save()

    def delete(self, session_id: str) -> bool:
        if session_id in self._cache:
            del self._cache[session_id]
            self._save()
            return True
        return False

    def all(self) -> dict[str, dict]:
        return dict(self._cache)