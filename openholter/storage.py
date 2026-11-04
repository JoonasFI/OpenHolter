"""On-disk session format.

    sessions/<id>/meta.json        session metadata, rewritten atomically on every change
    sessions/<id>/chunk-0000.rec.gz one file per hour of recording
    sessions/<id>/cache/            derived numpy arrays (safe to delete)

A chunk is a gzip stream of records:

    tag u8 | conn u16 | length u16 | wall_ns i64 | mono_ns i64 | payload[length]

tag 1 = raw PMD data notification, tag 2 = raw Heart Rate Measurement notification.
`conn` numbers the BLE connections within a session. Payloads are stored exactly as
received, so decoding can be improved later without re-recording.

The writer does a gzip sync flush every couple of seconds; a crash loses at most that
much and the reader tolerates a truncated final block.
"""
from __future__ import annotations

import gzip
import json
import os
import struct
import time
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

TAG_PMD = 1
TAG_HR = 2

HEADER = struct.Struct("<BHHqq")
CHUNK_SECONDS = 3600
FLUSH_SECONDS = 2.0


def write_json_atomic(path: Path, data: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def chunk_name(index: int) -> str:
    return f"chunk-{index:04d}.rec.gz"


class SessionWriter:
    def __init__(self, root: Path, device: Dict[str, Any], settings: Dict[str, Any], manual: bool):
        now = time.time_ns()
        stamp = datetime.fromtimestamp(now / 1e9).strftime("%Y-%m-%d_%H%M%S")
        self.dir = root / stamp
        self.dir.mkdir(parents=True, exist_ok=False)
        self.started_wall_ns = now
        self.started_mono_ns = time.monotonic_ns()
        self.meta: Dict[str, Any] = {
            "id": stamp,
            "format": 1,
            "state": "recording",
            "started_at": datetime.fromtimestamp(now / 1e9).astimezone().isoformat(timespec="seconds"),
            "started_wall_ns": now,
            "ended_at": None,
            "ended_wall_ns": None,
            "end_reason": None,
            "manual_start": manual,
            "device": device,
            "settings": settings,
            "connections": [],
            "events": [],
            "chunks": [],
        }
        self._init_chunks()

    def _init_chunks(self) -> None:
        self._chunk_index = len(self.meta["chunks"]) - 1
        self._chunk_base = self._chunk_index + 1  # rotation counts from (re)open time
        self._chunk: Optional[gzip.GzipFile] = None
        self._last_flush = time.monotonic()
        self.bytes_written = 0
        self._rotate()
        self.save_meta()

    @classmethod
    def resume(cls, session_dir: Path, meta: Dict[str, Any]) -> "SessionWriter":
        """Continue a session left in state "recording" (app crashed or was restarted)."""
        self = cls.__new__(cls)
        self.dir = session_dir
        self.meta = meta
        self.started_wall_ns = meta["started_wall_ns"]
        self.started_mono_ns = time.monotonic_ns()
        for c in meta["connections"]:
            if c["disconnected_at"] is None:
                c["disconnected_at"] = _iso_now()
                c["disconnected_wall_ns"] = time.time_ns()
                c["reason"] = "app restarted"
        meta["events"].append({"t": _iso_now(), "kind": "resumed"})
        self._init_chunks()
        return self

    @property
    def id(self) -> str:
        return self.meta["id"]

    @property
    def next_conn(self) -> int:
        return max((c["conn"] for c in self.meta["connections"]), default=-1) + 1

    def _rotate(self) -> None:
        if self._chunk is not None:
            self._chunk.close()
        self._chunk_index += 1
        name = chunk_name(self._chunk_index)
        self._chunk = gzip.open(self.dir / name, "wb", compresslevel=6)
        self.meta["chunks"].append(name)

    def write(self, tag: int, conn: int, payload: bytes, wall_ns: int, mono_ns: int) -> None:
        assert self._chunk is not None
        if (mono_ns - self.started_mono_ns) / 1e9 >= (self._chunk_index + 1 - self._chunk_base) * CHUNK_SECONDS:
            self._rotate()
            self.save_meta()
        self._chunk.write(HEADER.pack(tag, conn, len(payload), wall_ns, mono_ns))
        self._chunk.write(payload)
        self.bytes_written += HEADER.size + len(payload)
        if time.monotonic() - self._last_flush >= FLUSH_SECONDS:
            self.flush()

    def flush(self) -> None:
        if self._chunk is not None:
            self._chunk.flush()  # Z_SYNC_FLUSH: everything so far is decodable
            os.fsync(self._chunk.fileno())
        self._last_flush = time.monotonic()

    def event(self, kind: str, **details: Any) -> Dict[str, Any]:
        ev = {"id": os.urandom(4).hex(), "t": _iso_now(), "wall_ns": time.time_ns(), "kind": kind, **details}
        self.meta["events"].append(ev)
        self.save_meta()
        return ev

    def connection_started(self, conn: int, device: Dict[str, Any]) -> None:
        self.meta["connections"].append({"conn": conn, "connected_at": _iso_now(), "connected_wall_ns": time.time_ns(),
                                         "disconnected_at": None, "disconnected_wall_ns": None, "reason": None})
        self.meta["device"].update({k: v for k, v in device.items() if v is not None})
        self.save_meta()

    def connection_ended(self, conn: int, reason: str) -> None:
        for c in self.meta["connections"]:
            if c["conn"] == conn and c["disconnected_at"] is None:
                c["disconnected_at"] = _iso_now()
                c["disconnected_wall_ns"] = time.time_ns()
                c["reason"] = reason
        self.save_meta()

    def close(self, reason: str) -> None:
        self.flush()
        if self._chunk is not None:
            self._chunk.close()
            self._chunk = None
        for c in self.meta["connections"]:
            if c["disconnected_at"] is None:
                c["disconnected_at"] = _iso_now()
                c["disconnected_wall_ns"] = time.time_ns()
                c["reason"] = "session closed"
        self.meta["state"] = "closed"
        self.meta["ended_at"] = _iso_now()
        self.meta["ended_wall_ns"] = time.time_ns()
        self.meta["end_reason"] = reason
        self.save_meta()

    def save_meta(self) -> None:
        write_json_atomic(self.dir / "meta.json", self.meta)


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def iter_records(path: Path) -> Iterator[Tuple[int, int, int, int, bytes]]:
    """Yield (tag, conn, wall_ns, mono_ns, payload). Tolerates a truncated or still-open file."""
    d = zlib.decompressobj(wbits=31)
    buf = bytearray()
    with open(path, "rb") as f:
        while True:
            block = f.read(1 << 16)
            if not block:
                break
            try:
                buf += d.decompress(block)
            except zlib.error:
                break
            while d.eof and d.unused_data:  # concatenated gzip members
                rest = d.unused_data
                d = zlib.decompressobj(wbits=31)
                buf += d.decompress(rest)
            pos = 0
            while len(buf) - pos >= HEADER.size:
                tag, conn, length, wall, mono = HEADER.unpack_from(buf, pos)
                end = pos + HEADER.size + length
                if end > len(buf):
                    break
                yield tag, conn, wall, mono, bytes(buf[pos + HEADER.size:end])
                pos = end
            del buf[:pos]


def read_meta(session_dir: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((session_dir / "meta.json").read_text())
    except (OSError, ValueError):
        return None


def list_session_dirs(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted((p for p in root.iterdir() if (p / "meta.json").exists()), reverse=True)
