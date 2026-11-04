"""Deleted recordings go to $OPENHOLTER_HOME/trash first and are purged after RETENTION_DAYS.

ECG is health data the user may regret deleting; a move is instant and reversible,
permanent removal is an explicit second step (or the retention period).
"""
from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .storage import read_meta, write_json_atomic

RETENTION_DAYS = 30
MARKER = ".deleted.json"


class Trash:
    def __init__(self, home: Path, sessions_dir: Path):
        self.dir = home / "trash"
        self.sessions_dir = sessions_dir

    def _entry(self, name: str) -> Path:
        p = (self.dir / name).resolve()
        if p.parent != self.dir.resolve() or not (p / MARKER).exists():
            raise KeyError(name)
        return p

    def move_in(self, session_dir: Path) -> str:
        self.dir.mkdir(parents=True, exist_ok=True)
        name = session_dir.name
        target = self.dir / name
        n = 1
        while target.exists():  # same recording deleted, restored and deleted again
            n += 1
            target = self.dir / f"{name}~{n}"
        write_json_atomic(session_dir / MARKER, {"deleted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                                                 "deleted_ts": time.time(), "session_id": name})
        session_dir.rename(target)
        return target.name

    def list(self) -> List[Dict[str, Any]]:
        if not self.dir.exists():
            return []
        out = []
        for p in sorted(self.dir.iterdir(), reverse=True):
            try:
                mark = json.loads((p / MARKER).read_text())
            except (OSError, ValueError):
                continue
            meta = read_meta(p) or {}
            size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            purge = mark["deleted_ts"] + RETENTION_DAYS * 86400
            out.append({"name": p.name, "session_id": mark.get("session_id", p.name), "deleted_at": mark["deleted_at"],
                        "purge_in_days": max(0, round((purge - time.time()) / 86400, 1)), "bytes": size,
                        "started_wall_ns": meta.get("started_wall_ns"), "ended_wall_ns": meta.get("ended_wall_ns")})
        return out

    def restore(self, name: str) -> str:
        p = self._entry(name)
        sid = json.loads((p / MARKER).read_text()).get("session_id", name)
        target = self.sessions_dir / sid
        if target.exists():
            raise FileExistsError(sid)
        (p / MARKER).unlink()
        p.rename(target)
        return sid

    def purge(self, name: str) -> None:
        shutil.rmtree(self._entry(name))

    def purge_expired(self) -> int:
        n = 0
        for e in self.list():
            if e["purge_in_days"] <= 0:
                self.purge(e["name"])
                n += 1
        return n
