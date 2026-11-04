"""Live fan-out: ring buffers for the last seconds of data and WebSocket subscribers."""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Set

import numpy as np

from .quality import window_quality

ECG_SECONDS = 12
RR_SECONDS = 90


class LiveHub:
    def __init__(self) -> None:
        self.ecg_fs = 130.0
        self._ecg: Deque[int] = deque(maxlen=int(ECG_SECONDS * 140))
        self._rr: Deque[List[float]] = deque()
        self._acc: Optional[List[float]] = None
        self._posture: Optional[str] = None
        self._angles: Optional[List[float]] = None
        self._hr: Optional[Dict[str, Any]] = None
        self.quality = "none"
        self._last_quality = 0.0
        self._subs: Set[asyncio.Queue] = set()
        self.status: Dict[str, Any] = {}

    # ---- producers (called from the collector, on the event loop)

    def ecg(self, samples: np.ndarray, fs: float) -> None:
        self.ecg_fs = fs
        vals = samples.tolist()
        self._ecg.extend(vals)
        now = time.monotonic()
        msg: Dict[str, Any] = {"type": "ecg", "fs": fs, "v": vals, "at": time.time()}
        if now - self._last_quality > 1.0 and len(self._ecg) > fs * 2:
            self._last_quality = now
            tail = np.fromiter(self._ecg, dtype=np.int32)[-int(fs * 4):]
            # the strap's own skin-contact flag wins: unworn, it streams noise that can look "poor"
            q = "none" if self._hr and self._hr.get("contact") is False else window_quality(tail)
            if q != self.quality:
                self.quality = q
            msg["quality"] = q
        self._send(msg)

    def acc(self, samples: np.ndarray, posture: Optional[str] = None, angles: Optional[tuple] = None) -> None:
        g = samples.astype(np.float64).mean(axis=0)
        self._acc = [round(float(x), 1) for x in g]
        self._posture = posture
        self._angles = [round(a, 1) for a in angles] if angles else None
        self._send({"type": "acc", "g": self._acc, "posture": posture, "angles": self._angles})

    def heart_rate(self, bpm: int, rr_ms: List[float], contact: Optional[bool]) -> None:
        now = time.time()
        back = 0.0
        beats = []
        if contact is False:
            rr_ms = []  # unworn strap: intervals derived from noise, keep them out of the tachogram
        for r in reversed(rr_ms):
            beats.append([round(now - back / 1000.0, 3), round(r, 1)])
            back += r
        beats.reverse()
        self._rr.extend(beats)
        while self._rr and self._rr[0][0] < now - RR_SECONDS:
            self._rr.popleft()
        self._hr = {"bpm": bpm, "contact": contact, "at": now}
        self._send({"type": "hr", "bpm": bpm, "rr": beats, "contact": contact, "at": now})

    def set_status(self, status: Dict[str, Any]) -> None:
        self.status = status
        self._send({"type": "status", **status})

    def clear(self) -> None:
        self._ecg.clear()
        self._acc = None
        self._posture = None
        self._angles = None
        self._hr = None
        self.quality = "none"

    # ---- consumers

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=400)
        q.put_nowait({"type": "status", **self.status})
        q.put_nowait({
            "type": "backlog", "fs": self.ecg_fs, "ecg": list(self._ecg)[-int(self.ecg_fs * 10):],
            "rr": list(self._rr), "acc": self._acc, "posture": self._posture, "angles": self._angles, "hr": self._hr, "quality": self.quality, "at": time.time(),
        })
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def _send(self, msg: Dict[str, Any]) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass  # slow client: drop rather than block acquisition
