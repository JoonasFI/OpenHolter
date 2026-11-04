"""Decoding recorded sessions into time-aligned arrays, plus the queries the UI needs.

Time base: every sample gets a session time in seconds since `started_wall_ns`.
Within one BLE connection the H10's own sample clock is used (exact sample spacing);
the mapping from sensor clock to wall clock is a drift-corrected linear fit anchored
to the earliest-arriving frames (BLE latency is only ever positive).
"""
from __future__ import annotations

import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from . import pmd
from .quality import SCORE, window_quality
from .storage import TAG_HR, TAG_PMD, iter_records, list_session_dirs, read_meta, write_json_atomic

CACHE_VERSION = 3  # 3: skin-contact flag decoded from HR notifications


# --------------------------------------------------------------------------- chunk decoding

def _decode_chunk(path: Path) -> Dict[str, np.ndarray]:
    ecg_frames: List[Tuple[int, int, int, int]] = []  # conn, wall, sensor_ts, n
    ecg_parts: List[np.ndarray] = []
    acc_frames: List[Tuple[int, int, int, int]] = []
    acc_parts: List[np.ndarray] = []
    hr_rows: List[Tuple[int, int, int, int]] = []  # conn, wall, bpm, contact (1 yes, 0 no, -1 not reported)
    rr_rows: List[Tuple[int, float, int]] = []  # wall, rr_ms (beat end time ≈ wall - later rrs), contact
    for tag, conn, wall, _mono, payload in iter_records(path):
        if tag == TAG_PMD:
            try:
                fr = pmd.parse_frame(payload)
            except ValueError:
                continue
            if fr.measurement == pmd.ECG:
                ecg_frames.append((conn, wall, fr.sensor_ts_ns, len(fr.samples)))
                ecg_parts.append(fr.samples)
            elif fr.measurement == pmd.ACC:
                acc_frames.append((conn, wall, fr.sensor_ts_ns, len(fr.samples)))
                acc_parts.append(fr.samples)
        elif tag == TAG_HR:
            try:
                hr = pmd.parse_heart_rate(payload)
            except (IndexError, ValueError):
                continue
            contact = -1 if hr.contact is None else int(hr.contact)
            hr_rows.append((conn, wall, hr.bpm, contact))
            back = 0.0
            for r in reversed(hr.rr_ms):
                rr_rows.append((wall - int(back * 1e6), r, contact))
                back += r
    def frames(rows):
        a = np.array(rows, dtype=np.int64).reshape(-1, 4)
        return a
    return {
        "ecg_frames": frames(ecg_frames),
        "ecg": np.concatenate(ecg_parts) if ecg_parts else np.zeros(0, np.int32),
        "acc_frames": frames(acc_frames),
        "acc": np.concatenate(acc_parts) if acc_parts else np.zeros((0, 3), np.int32),
        "hr": np.array(hr_rows, dtype=np.int64).reshape(-1, 4),
        "rr": np.array(sorted(rr_rows), dtype=np.float64).reshape(-1, 3),
    }


def _chunk_arrays(session_dir: Path, name: str, closed: bool) -> Dict[str, np.ndarray]:
    path = session_dir / name
    cache = session_dir / "cache" / (name + f".v{CACHE_VERSION}.npz")
    st = path.stat()
    if cache.exists():
        with np.load(cache) as z:
            if int(z["src_size"]) == st.st_size:
                return {k: z[k] for k in z.files if k != "src_size"}
    data = _decode_chunk(path)
    if closed:
        cache.parent.mkdir(exist_ok=True)
        tmp = cache.with_name(cache.name + ".tmp.npz")
        np.savez(tmp, src_size=np.int64(st.st_size), **data)
        tmp.replace(cache)
    return data


# --------------------------------------------------------------------------- session assembly

@dataclass
class SessionData:
    meta: Dict[str, Any]
    ecg_t: np.ndarray  # float64 s since session start
    ecg_uv: np.ndarray  # int32
    acc_t: np.ndarray
    acc_mg: np.ndarray  # (n, 3) int32
    hr_t: np.ndarray
    hr_bpm: np.ndarray
    rr_t: np.ndarray
    rr_ms: np.ndarray
    ecg_fs: float
    # [start, end] seconds where the strap reported no skin contact; HR and RR from these
    # periods are dropped above (an unworn H10 invents a rate from noise)
    no_contact: List[List[float]] = None  # type: ignore[assignment]

    @property
    def duration(self) -> float:
        end = self.meta.get("ended_wall_ns")
        if end:
            return (end - self.meta["started_wall_ns"]) / 1e9
        last = [a[-1] for a in (self.ecg_t, self.hr_t) if len(a)]
        return float(max(last)) if last else 0.0


def _sample_times(frames: np.ndarray, nominal_fs: float, conn_map: Dict[int, Tuple[float, float]]) -> Tuple[np.ndarray, float]:
    """Per-sample wall times (ns, float64) from frame end timestamps."""
    if len(frames) == 0:
        return np.zeros(0), nominal_fs
    conn, _wall, ts, n = frames.T
    dt = np.full(len(frames), 1e9 / nominal_fs)
    fs_seen = []
    for c in np.unique(conn):
        m = conn == c
        tsc, nc = ts[m].astype(np.float64), n[m].astype(np.float64)
        if len(tsc) > 2:
            est = np.diff(tsc) / nc[1:]
            ok = np.abs(est * nominal_fs / 1e9 - 1) < 0.2
            if ok.sum() > 2:
                dt[m] = np.median(est[ok])
                fs_seen.append(1e9 / dt[m][0])
    total = int(n.sum())
    rep = np.repeat(np.arange(len(frames)), n)
    starts = np.cumsum(n) - n
    pos = np.arange(total) - starts[rep]
    sensor = ts[rep].astype(np.float64) - (n[rep] - 1 - pos) * dt[rep]
    a = np.array([conn_map.get(int(c), (0.0, 0.0))[0] for c in conn])
    b = np.array([conn_map.get(int(c), (0.0, 0.0))[1] for c in conn])
    wall = sensor + a[rep] * sensor + b[rep]
    return wall, (float(np.median(fs_seen)) if fs_seen else nominal_fs)


def _clock_map(frames: np.ndarray) -> Dict[int, Tuple[float, float]]:
    """Per connection: wall ≈ sensor + a*sensor + b."""
    out: Dict[int, Tuple[float, float]] = {}
    if len(frames) == 0:
        return out
    conn, wall, ts, _n = frames.T
    for c in np.unique(conn):
        m = conn == c
        x = ts[m].astype(np.float64)
        y = wall[m].astype(np.float64) - x
        a = 0.0
        if x[-1] - x[0] > 120e9 and len(x) > 50:
            a = float(np.polyfit(x - x[0], y, 1)[0])
        resid = y - a * x
        b = float(np.percentile(resid, 0.5))
        out[int(c)] = (a, b)
    return out


def assemble(session_dir: Path) -> SessionData:
    meta = read_meta(session_dir) or {}
    closed = meta.get("state") == "closed"
    chunks = meta.get("chunks", [])
    parts = [
        _chunk_arrays(session_dir, name, closed or i < len(chunks) - 1)
        for i, name in enumerate(chunks)
        if (session_dir / name).exists()
    ]
    cat = lambda key, shape: np.concatenate([p[key] for p in parts]) if parts else np.zeros(shape, np.int64)
    ecg_frames, acc_frames = cat("ecg_frames", (0, 4)), cat("acc_frames", (0, 4))
    settings = meta.get("settings", {})
    t0 = float(meta.get("started_wall_ns", 0))
    cmap = _clock_map(np.concatenate([ecg_frames, acc_frames]) if len(acc_frames) else ecg_frames)
    ecg_wall, fs = _sample_times(ecg_frames, settings.get("ecg_sample_rate", 130), cmap)
    acc_wall, _ = _sample_times(acc_frames, settings.get("acc_sample_rate", 50), cmap)
    ecg_uv = cat("ecg", (0,)).astype(np.int32)
    acc_mg = cat("acc", (0, 3)).astype(np.int32)
    hr = cat("hr", (0, 4))
    rr = np.concatenate([p["rr"] for p in parts]) if parts else np.zeros((0, 3))
    off_t = (hr[hr[:, 3] == 0, 1].astype(np.float64) - t0) / 1e9
    no_contact: List[List[float]] = []
    for x in off_t:  # HR arrives ~1/s: merge seconds into intervals
        if no_contact and x - no_contact[-1][1] <= 2.5:
            no_contact[-1][1] = float(x)
        else:
            no_contact.append([float(x) - 1.0, float(x)])
    hr = hr[hr[:, 3] != 0]
    rr = rr[rr[:, 2] != 0]

    def ordered(t, *vals):
        if len(t) > 1 and np.any(np.diff(t) < 0):
            o = np.argsort(t, kind="stable")
            return (t[o],) + tuple(v[o] for v in vals)
        return (t,) + vals

    ecg_t, ecg_uv = ordered((ecg_wall - t0) / 1e9, ecg_uv)
    acc_t, acc_mg = ordered((acc_wall - t0) / 1e9, acc_mg)
    return SessionData(
        meta=meta,
        ecg_t=ecg_t, ecg_uv=ecg_uv,
        acc_t=acc_t, acc_mg=acc_mg,
        hr_t=(hr[:, 1].astype(np.float64) - t0) / 1e9, hr_bpm=hr[:, 2].astype(np.float64),
        rr_t=(rr[:, 0] - t0) / 1e9, rr_ms=rr[:, 1], no_contact=no_contact,
        ecg_fs=fs,
    )


class SessionStore:
    """Thread-safe access with a small in-memory LRU of assembled sessions."""

    def __init__(self, root: Path, keep: int = 2):
        self.root = root
        self.keep = keep
        self._lru: "OrderedDict[str, Tuple[tuple, SessionData]]" = OrderedDict()
        self._lock = threading.Lock()

    def _signature(self, d: Path) -> tuple:
        meta = read_meta(d) or {}
        sig = [meta.get("state")]
        for name in meta.get("chunks", []):
            p = d / name
            if p.exists():
                sig.append((name, p.stat().st_size))
        return tuple(sig)

    def dir(self, session_id: str) -> Path:
        d = (self.root / session_id).resolve()
        if d.parent != self.root.resolve() or not (d / "meta.json").exists():
            raise KeyError(session_id)
        return d

    def get(self, session_id: str) -> SessionData:
        d = self.dir(session_id)
        sig = self._signature(d)
        with self._lock:
            hit = self._lru.get(session_id)
            if hit and hit[0] == sig:
                self._lru.move_to_end(session_id)
                return hit[1]
        data = assemble(d)
        with self._lock:
            self._lru[session_id] = (sig, data)
            self._lru.move_to_end(session_id)
            while len(self._lru) > self.keep:
                self._lru.popitem(last=False)
        return data

    def forget(self, session_id: str) -> None:
        with self._lock:
            self._lru.pop(session_id, None)

    def list(self) -> List[Dict[str, Any]]:
        out = []
        for d in list_session_dirs(self.root):
            meta = read_meta(d)
            if not meta:
                continue
            out.append({"meta": public_meta(meta), "summary": self.summary(d.name, meta)})
        return out

    def summary(self, session_id: str, meta: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        d = self.dir(session_id)
        meta = meta or read_meta(d) or {}
        path = d / "cache" / "summary.json"
        if meta.get("state") == "closed" and path.exists():
            try:
                s = json.loads(path.read_text())
                if s.get("v") == CACHE_VERSION:
                    return s
            except ValueError:
                pass
        if meta.get("state") != "closed":
            return None  # live sessions are summarised by the status endpoint
        s = summarize(self.get(session_id))
        path.parent.mkdir(exist_ok=True)
        write_json_atomic(path, s)
        return s


def public_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("id", "state", "started_at", "ended_at", "end_reason", "manual_start", "device", "settings",
            "connections", "events", "started_wall_ns", "ended_wall_ns")
    return {k: meta.get(k) for k in keys}


# --------------------------------------------------------------------------- queries

def gaps(t: np.ndarray, duration: float, min_gap: float = 2.0) -> List[List[float]]:
    if len(t) == 0:
        return [[0.0, duration]] if duration > 0 else []
    out = []
    if t[0] > min_gap:
        out.append([0.0, float(t[0])])
    d = np.diff(t)
    for i in np.nonzero(d > min_gap)[0]:
        out.append([float(t[i]), float(t[i + 1])])
    if duration - t[-1] > min_gap:
        out.append([float(t[-1]), float(duration)])
    return out


def _bucket_edges(start: float, end: float, n: int) -> np.ndarray:
    return np.linspace(start, end, n + 1)


def envelope(t: np.ndarray, v: np.ndarray, start: float, end: float, points: int) -> Dict[str, Any]:
    """Min/max per time bucket; empty buckets are None so gaps stay visible."""
    edges = _bucket_edges(start, end, points)
    idx = np.searchsorted(t, edges)
    counts = np.diff(idx)
    lo = np.full(points, np.nan)
    hi = np.full(points, np.nan)
    nz = counts > 0
    if nz.any():
        starts = idx[:-1][nz]
        lo[nz] = np.minimum.reduceat(v, starts)[: nz.sum()] if len(v) else np.nan
        hi[nz] = np.maximum.reduceat(v, starts)[: nz.sum()] if len(v) else np.nan
        # reduceat over the last start runs to the end of the array; clamp it to its bucket
        last = np.nonzero(nz)[0][-1]
        a, b = idx[last], idx[last + 1]
        lo[last], hi[last] = v[a:b].min(), v[a:b].max()
    return {"mode": "envelope", "start": start, "end": end, "min": _nan_list(lo), "max": _nan_list(hi)}


def _nan_list(a: np.ndarray, digits: int = 0) -> List[Optional[float]]:
    r = np.round(a, digits)
    return [None if np.isnan(x) else (int(x) if digits == 0 else float(x)) for x in r]


def ecg_window(s: SessionData, start: float, end: float, points: int) -> Dict[str, Any]:
    start, end = max(0.0, start), max(start + 0.1, end)
    a, b = np.searchsorted(s.ecg_t, [start, end])
    if b - a <= points * 2:
        return {
            "mode": "raw", "start": start, "end": end, "fs": s.ecg_fs,
            "t": np.round(s.ecg_t[a:b], 4).tolist(), "v": s.ecg_uv[a:b].tolist(),
        }
    return envelope(s.ecg_t, s.ecg_uv, start, end, points)


def bucket_mean(t: np.ndarray, v: np.ndarray, start: float, end: float, points: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    edges = _bucket_edges(start, end, points)
    idx = np.searchsorted(t, edges)
    mean, lo, hi = (np.full(points, np.nan) for _ in range(3))
    for i in range(points):
        a, b = idx[i], idx[i + 1]
        if b > a:
            seg = v[a:b]
            mean[i], lo[i], hi[i] = seg.mean(), seg.min(), seg.max()
    centers = (edges[:-1] + edges[1:]) / 2
    return centers, mean, lo, hi


def hr_series(s: SessionData, points: int = 600) -> Dict[str, Any]:
    dur = s.duration
    _c, mean, lo, hi = bucket_mean(s.hr_t, s.hr_bpm, 0.0, dur, points)
    return {"start": 0.0, "end": dur, "mean": _nan_list(mean, 1), "min": _nan_list(lo), "max": _nan_list(hi)}


def rr_window(s: SessionData, start: float, end: float) -> Dict[str, Any]:
    a, b = np.searchsorted(s.rr_t, [start, end])
    return {"t": np.round(s.rr_t[a:b], 3).tolist(), "rr": np.round(s.rr_ms[a:b], 1).tolist()}


def posture_preview(s: SessionData, points: int = 600) -> Dict[str, Any]:
    """Uncalibrated orientation track: roll angle around the body axis + upright flag.

    The body's long axis is taken as the sensor axis whose gravity component varies least
    while lying down (gravity rotates around it when turning over). Stage 6 replaces this
    with calibrated posture classes.
    """
    dur = s.duration
    if len(s.acc_t) < 100:
        return {"start": 0.0, "end": dur, "roll": [], "upright": [], "axis": None}
    g = s.acc_mg.astype(np.float64)
    norm = np.linalg.norm(g, axis=1, keepdims=True)
    u = g / np.maximum(norm, 1.0)
    axis = int(np.argmin(np.std(u, axis=0)))
    others = [i for i in range(3) if i != axis]
    roll_all = np.degrees(np.arctan2(u[:, others[1]], u[:, others[0]]))
    edges = _bucket_edges(0.0, dur, points)
    idx = np.searchsorted(s.acc_t, edges)
    roll = np.full(points, np.nan)
    upright = np.zeros(points, bool)
    for i in range(points):
        a, b = idx[i], idx[i + 1]
        if b > a:
            # circular mean of the angle
            ang = np.radians(roll_all[a:b])
            roll[i] = np.degrees(np.arctan2(np.sin(ang).mean(), np.cos(ang).mean()))
            upright[i] = abs(u[a:b, axis].mean()) > 0.7
    return {"start": 0.0, "end": dur, "roll": _nan_list(roll), "upright": upright.tolist(), "axis": "xyz"[axis]}


def summarize(s: SessionData) -> Dict[str, Any]:
    dur = s.duration
    fs = s.ecg_fs or 130.0
    recorded = len(s.ecg_uv) / fs
    win = int(10 * fs)
    counts = {"good": 0, "fair": 0, "poor": 0, "none": 0}
    score = 0.0
    nwin = len(s.ecg_uv) // win
    off = s.no_contact or []
    for i in range(nwin):
        a = i * win
        t_mid = float(s.ecg_t[a + win // 2]) if len(s.ecg_t) > a + win // 2 else 0.0
        if any(x0 <= t_mid <= x1 for x0, x1 in off):
            q = "none"  # strap reported no skin contact: the ECG is noise whatever it looks like
        else:
            q = window_quality(s.ecg_uv[a:a + win])
        counts[q] += 1
        score += SCORE[q]
    hr = s.hr_bpm[s.hr_bpm > 0]
    _c, spark, _lo, _hi = bucket_mean(s.hr_t, s.hr_bpm, 0.0, dur, 96) if dur > 0 else (None, np.zeros(0), None, None)
    conns = s.meta.get("connections", [])
    return {
        "v": CACHE_VERSION,
        "duration_s": round(dur, 1),
        "recorded_s": round(recorded, 1),
        "coverage": round(recorded / dur, 4) if dur > 0 else 0.0,
        "quality_score": round(score / nwin, 3) if nwin else 0.0,
        "quality_windows": counts,
        "ecg_samples": int(len(s.ecg_uv)),
        "ecg_fs": round(fs, 3),
        "hr_mean": round(float(hr.mean()), 1) if len(hr) else None,
        "hr_min": int(hr.min()) if len(hr) else None,
        "hr_max": int(hr.max()) if len(hr) else None,
        "rr_count": int(len(s.rr_ms)),
        "disconnects": max(0, len(conns) - 1),
        "no_contact_s": round(sum(b - a for a, b in off), 1),
        "gaps": gaps(s.ecg_t, dur),
        "hr_spark": _nan_list(spark, 1),
    }
