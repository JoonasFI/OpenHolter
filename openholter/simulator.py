"""Synthetic Polar H10 for developing without the strap.

Produces byte-identical PMD and Heart Rate notifications, so the whole pipeline
(parsing, storage, decoding, UI) runs exactly as with the real device. The synthetic
body has a slowly varying sinus rhythm with respiratory arrhythmia, posture changes
during the night and premature ventricular beats that are more frequent lying supine
or on the left side. This is test data, nothing more.
"""
from __future__ import annotations

import asyncio
import os
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from . import pmd
from .storage import TAG_HR, TAG_PMD, SessionWriter, write_json_atomic

# Gravity reaction in body frame (x = left→right, y = feet→head, z = back→chest), mG.
POSTURE_G = {
    "supine": (0, 0, 1000),
    "prone": (0, 0, -1000),
    "left": (1000, 0, 0),
    "right": (-1000, 0, 0),
    "upright": (0, 1000, 0),
}
VES_RATE = {"supine": 0.035, "left": 0.05, "right": 0.004, "prone": 0.004, "upright": 0.01}
TRUE_FS = 130.04  # the H10 crystal is never exactly 130 Hz


def _rot(ax: float, ay: float, az: float) -> np.ndarray:
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return rz @ ry @ rx


def _gauss(t: np.ndarray, mu: float, w: float, a: float) -> np.ndarray:
    return a * np.exp(-0.5 * ((t - mu) / w) ** 2)


def beat_wave(t: np.ndarray, kind: str, rr: float) -> np.ndarray:
    """ECG of one beat in µV, t relative to the R peak (s)."""
    qt = 0.28 * math.sqrt(max(rr, 0.4))
    if kind == "V":
        return (_gauss(t, -0.01, 0.032, 1500) + _gauss(t, 0.06, 0.03, -650)
                + _gauss(t, qt + 0.05, 0.075, -420))
    return (_gauss(t, -0.17, 0.024, 110) + _gauss(t, -0.028, 0.009, -110) + _gauss(t, 0.0, 0.011, 1250)
            + _gauss(t, 0.03, 0.011, -320) + _gauss(t, qt, 0.055, 290))


class SyntheticBody:
    def __init__(self, seed: int = 7, night: bool = True, hours: float = 9.0):
        self.rng = np.random.default_rng(seed)
        self.strap = _rot(*self.rng.normal(0, 0.25, 3))
        self.schedule = self._make_schedule(hours) if night else [(0.0, 1e9, "supine")]
        self.beats: List[Tuple[float, str]] = [(0.4, "N")]
        self._hr_phase = self.rng.uniform(0, 6.28)
        self._mode = None  # (pattern, remaining) for bigeminy/trigeminy runs
        self.off_periods: List[Tuple[float, float]] = []
        if night:
            t = self.rng.uniform(2.0, 3.0) * 3600
            self.off_periods.append((t, t + 150))
        self._blocks: Dict[int, np.ndarray] = {}

    def _make_schedule(self, hours: float) -> List[Tuple[float, float, str]]:
        seq = ["supine", "left", "supine", "right", "prone", "right", "upright", "left", "supine", "right", "left", "supine"]
        out, t = [], 0.0
        for i, p in enumerate(seq):
            dur = 4 * 60 if p == "upright" else self.rng.uniform(25, 70) * 60
            out.append((t, t + dur, p))
            t += dur
            if t > hours * 3600:
                break
        out[-1] = (out[-1][0], 1e9, out[-1][2])
        return out

    override: Optional[str] = None  # live simulator: posture set from the UI for testing calibration

    def posture(self, t: float) -> str:
        if self.override:
            return self.override
        for a, b, p in self.schedule:
            if a <= t < b:
                return p
        return self.schedule[-1][2]

    def _transition_noise(self, t: float) -> float:
        """0..1 movement intensity near posture changes."""
        best = 0.0
        for a, _b, _p in self.schedule[1:]:
            d = abs(t - a)
            if d < 8:
                best = max(best, 1 - d / 8)
        return best

    def base_rr(self, t: float) -> float:
        hr = 58 + 9 * math.exp(-t / 2400) + 3 * math.sin(t / 2900 + self._hr_phase)
        if self.posture(t) == "upright":
            hr += 18
        hr += 2.5 * math.sin(2 * math.pi * t / 5400)  # sleep cycles
        rr = 60.0 / hr
        return rr * (1 + 0.045 * math.sin(2 * math.pi * 0.24 * t))  # respiratory sinus arrhythmia

    def _extend(self, until: float) -> None:
        while self.beats[-1][0] < until:
            t, kind = self.beats[-1]
            rr = self.base_rr(t)
            if kind == "V":  # compensatory pause: N-V-N spans two normal cycles
                prev = self.beats[-2][0] if len(self.beats) > 1 else t - rr
                self.beats.append((max(t + rr * 1.15, prev + 2 * rr), "N"))
                continue
            p = VES_RATE[self.posture(t)]
            if self._mode is None and self.rng.random() < p * 0.06:
                self._mode = (self.rng.choice([2, 3]), int(self.rng.integers(4, 12)))
            want_v = self.rng.random() < p
            if self._mode is not None:
                period, left = self._mode
                want_v = (len(self.beats) % period == 0)
                self._mode = None if left <= 1 else (period, left - (1 if want_v else 0))
            if want_v:
                self.beats.append((t + rr * self.rng.uniform(0.58, 0.72), "V"))
                if self.rng.random() < 0.08:  # couplet
                    t2 = self.beats[-1][0]
                    self.beats.append((t2 + rr * 0.7, "V"))
            else:
                self.beats.append((t + rr * (1 + self.rng.normal(0, 0.008)), "N"))

    def _render_block(self, k: int, fs: float) -> np.ndarray:
        """30 s of ECG samples, block k covers sample indices [k*n, (k+1)*n)."""
        n = int(round(30 * fs))
        t = (np.arange(n) + k * n) / fs
        t0, t1 = t[0], t[-1]
        self._extend(t1 + 2)
        x = np.zeros(n)
        times = np.array([b[0] for b in self.beats])
        lo, hi = np.searchsorted(times, [t0 - 1.0, t1 + 1.0])
        for i in range(lo, hi):
            bt, kind = self.beats[i]
            rr = times[i] - times[i - 1] if i > 0 else 0.9
            a, b = np.searchsorted(t, [bt - 0.35, bt + 0.75])
            if b > a:
                x[a:b] += beat_wave(t[a:b] - bt, kind, rr)
        # baseline wander (breathing), mains-free white noise, movement artefacts
        x += 70 * np.sin(2 * np.pi * 0.24 * t + 1.0) + 25 * np.sin(2 * np.pi * 0.05 * t)
        x += self.rng.normal(0, 14, n)
        move = np.array([self._transition_noise(tt) for tt in t[::13]])
        if move.any():
            m = np.repeat(move, 13)[:n]
            x += m * np.cumsum(self.rng.normal(0, 60, n))
        for a, b in self.off_periods:
            mask = (t >= a) & (t < b)
            if mask.any():
                x[mask] = self.rng.normal(0, 4, mask.sum())
        return np.round(x).astype(np.int32)

    def ecg(self, i0: int, n: int, fs: float = TRUE_FS) -> np.ndarray:
        bn = int(round(30 * fs))
        out = []
        i = i0
        while i < i0 + n:
            k = i // bn
            if k not in self._blocks:
                self._blocks[k] = self._render_block(k, fs)
                for old in [b for b in self._blocks if b < k - 1]:
                    del self._blocks[old]
            blk = self._blocks[k]
            a = i - k * bn
            take = min(bn - a, i0 + n - i)
            out.append(blk[a:a + take])
            i += take
        return np.concatenate(out)

    def acc(self, t: np.ndarray) -> np.ndarray:
        g = np.array([POSTURE_G[self.posture(float(tt))] for tt in t], dtype=np.float64)
        # blend across transitions so turning over is a smooth rotation
        move = np.array([self._transition_noise(float(tt)) for tt in t])
        g = g @ self.strap.T
        g[:, 2] += 12 * np.sin(2 * np.pi * 0.24 * t)  # chest rise
        g += self.rng.normal(0, 6, g.shape) + move[:, None] * self.rng.normal(0, 250, g.shape)
        return np.round(g).astype(np.int32)

    def beats_between(self, t0: float, t1: float) -> List[Tuple[float, float]]:
        """(end time, RR ms) of beats ending in (t0, t1]."""
        self._extend(t1 + 2)
        out = []
        for i in range(1, len(self.beats)):
            bt = self.beats[i][0]
            if t0 < bt <= t1:
                out.append((bt, (bt - self.beats[i - 1][0]) * 1000))
            elif bt > t1:
                break
        return out

    def bpm_at(self, t: float) -> int:
        """Smoothed rate like the strap reports: median of the last 8 beat intervals."""
        ends = [b for b, _r in self.beats_between(t - 10, t)][-9:]
        if len(ends) < 2:
            return int(round(60 / self.base_rr(t)))
        return int(round(60 / float(np.median(np.diff(ends)))))

    skin_off: bool = False  # live simulator: strap "taken off" from the UI

    def in_off(self, t: float) -> bool:
        if self.skin_off:
            return True
        return any(a <= t < b for a, b in self.off_periods)


class SimLink:
    """Drop-in replacement for H10Link that streams in real time."""

    ECG_PER_FRAME = 73
    ACC_PER_FRAME = 36

    def __init__(self, body: Optional[SyntheticBody] = None, acc_fs: float = 50.0):
        self.body = body or SyntheticBody(seed=int(time.time()) % 1000, night=False)
        self.acc_fs = acc_fs
        self._task: Optional[asyncio.Task] = None
        self.info = {"name": "Polar H10 SIM00001", "address": "simulated", "model": "H10 (simulaattori)",
                     "firmware": "sim", "battery": 87, "features": ["ecg", "acc"]}

    async def open(self, on_pmd, on_hr, on_disconnect) -> Dict[str, Any]:
        await asyncio.sleep(0.4)
        self._task = asyncio.get_running_loop().create_task(self._run(on_pmd, on_hr))
        return dict(self.info)

    async def _run(self, on_pmd, on_hr) -> None:
        start = time.monotonic()
        sensor0 = int((time.time() - 946_684_800) * 1e9)
        ei = ai = 0
        last_hr = 0.0
        while True:
            now = time.monotonic() - start
            while (ei + self.ECG_PER_FRAME) / TRUE_FS <= now:
                v = self.body.ecg(ei, self.ECG_PER_FRAME)
                ei += self.ECG_PER_FRAME
                on_pmd(pmd.encode_frame(pmd.ECG, sensor0 + int((ei - 1) / TRUE_FS * 1e9), v))
            while (ai + self.ACC_PER_FRAME) / self.acc_fs <= now:
                t = (np.arange(ai, ai + self.ACC_PER_FRAME)) / self.acc_fs
                ai += self.ACC_PER_FRAME
                on_pmd(pmd.encode_frame(pmd.ACC, sensor0 + int(t[-1] * 1e9), self.body.acc(t)))
            if now - last_hr >= 1.0:
                beats = self.body.beats_between(last_hr, now)
                last_hr = now
                rr = [r for _t, r in beats]
                on_hr(pmd.encode_heart_rate(self.body.bpm_at(now), rr, contact=not self.body.in_off(now)))
            await asyncio.sleep(0.05)

    async def battery(self) -> Optional[int]:
        return 87

    async def rssi(self) -> Optional[int]:
        self._rssi = getattr(self, "_rssi", -55) + float(self.body.rng.normal(0, 1.5))
        self._rssi = min(-42, max(-70, self._rssi))
        return int(round(self._rssi))

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None


def generate_night(root: Path, hours: float = 7.5, start: Optional[datetime] = None, seed: int = 11,
                   progress: Optional[Callable[[float], None]] = None) -> Path:
    """Write a complete simulated night as a closed session (fast, not real time)."""
    start = start or datetime.now().replace(hour=23, minute=12, second=0, microsecond=0)
    t0_ns = int(start.timestamp() * 1e9)
    body = SyntheticBody(seed=seed, night=True, hours=hours)
    stamp = start.strftime("%Y-%m-%d_%H%M%S")
    d = root / stamp
    if d.exists():
        raise FileExistsError(d)
    w = SessionWriter.__new__(SessionWriter)
    w.dir = d
    d.mkdir(parents=True)
    w.started_wall_ns = t0_ns
    w.started_mono_ns = 0
    iso = lambda s: datetime.fromtimestamp((t0_ns + s * 1e9) / 1e9).astimezone().isoformat(timespec="seconds")
    w.meta = {
        "id": stamp, "format": 1, "state": "recording", "started_at": iso(0), "started_wall_ns": t0_ns,
        "ended_at": None, "ended_wall_ns": None, "end_reason": None, "manual_start": False, "simulated": True,
        "device": {"name": "Polar H10 SIM00001", "address": "simulated", "model": "H10 (simulaattori)", "battery": 81},
        "settings": {"ecg_sample_rate": 130, "acc_sample_rate": 50, "acc_range_g": 4, "acc_resolution": 16},
        "connections": [], "events": [], "chunks": [],
    }
    w._init_chunks()

    total = hours * 3600
    # one BLE drop-out during the night-time bathroom trip
    up = next((a for a, _b, p in body.schedule if p == "upright"), total / 2)
    drop = (up + 40, up + 40 + 95)
    conns = [(0, 0.0, drop[0]), (1, drop[1], total)]
    sensor0 = int((t0_ns / 1e9 - 946_684_800) * 1e9) + 3_217_000_000
    latency = lambda: int(body.rng.gamma(2.0, 9e6))
    ef, af = SimLink.ECG_PER_FRAME, SimLink.ACC_PER_FRAME
    for conn, a, b in conns:
        w.meta["connections"].append({"conn": conn, "connected_at": iso(a), "connected_wall_ns": int(t0_ns + a * 1e9),
                                      "disconnected_at": iso(b), "disconnected_wall_ns": int(t0_ns + b * 1e9),
                                      "reason": "link lost" if conn == 0 else "session closed"})
        ei = int(a * TRUE_FS)
        ai = int(a * 50)
        hr_t = a
        while ei / TRUE_FS < b:
            v = body.ecg(ei, ef)
            ei += ef
            te = (ei - 1) / TRUE_FS
            wall = int(t0_ns + te * 1e9) + latency()
            w.write(TAG_PMD, conn, pmd.encode_frame(pmd.ECG, sensor0 + int(te * 1e9), v), wall, int(te * 1e9))
            while (ai + af) / 50 <= te:
                t = np.arange(ai, ai + af) / 50
                ai += af
                wall_a = int(t0_ns + t[-1] * 1e9) + latency()
                w.write(TAG_PMD, conn, pmd.encode_frame(pmd.ACC, sensor0 + int(t[-1] * 1e9), body.acc(t)), wall_a, int(t[-1] * 1e9))
            while hr_t + 1 <= te:
                beats = body.beats_between(hr_t, hr_t + 1)
                hr_t += 1
                rr = [r for _t, r in beats]
                w.write(TAG_HR, conn, pmd.encode_heart_rate(body.bpm_at(hr_t), rr, not body.in_off(hr_t)),
                        int(t0_ns + hr_t * 1e9) + latency(), int(hr_t * 1e9))
            if progress and ei % (ef * 400) < ef:
                progress(te / total)
    w.flush()
    w._chunk.close()
    w._chunk = None
    w.meta.update({"state": "closed", "ended_at": iso(total), "ended_wall_ns": int(t0_ns + total * 1e9),
                   "end_reason": f"strap not seen for 10 min"})
    w.meta["events"].append({"t": iso(drop[0]), "kind": "disconnect"})
    # a few "I felt it" markers: most a couple of seconds after an ectopic beat, one false alarm
    vt_all = [t for t, k in body.beats if k == "V" and 600 < t < total - 600]
    picks = [vt_all[int(i * (len(vt_all) - 1) / 4)] for i in range(4)] if len(vt_all) > 4 else vt_all
    for t in picks + [total * 0.37]:
        lag = body.rng.uniform(1.0, 3.5) if t in picks else 0.0
        w.meta["events"].append({"id": os.urandom(4).hex(), "t": iso(t + lag), "wall_ns": int(t0_ns + (t + lag) * 1e9),
                                 "kind": "symptom"})
    w.meta["events"].sort(key=lambda e: e.get("wall_ns") or 0)
    write_json_atomic(d / "meta.json", w.meta)
    # Ground truth for validating the analysis stage later.
    vt = [round(t, 3) for t, k in body.beats if k == "V" and t < total]
    write_json_atomic(d / "simulation_truth.json", {"ves_times": vt, "schedule": body.schedule[:-1] + [
        (body.schedule[-1][0], total, body.schedule[-1][2])], "off_periods": body.off_periods})
    return d
