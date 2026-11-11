"""Morning analysis: runs in a separate low-priority process, once a day or on demand.

Results go to sessions/<id>/cache/analysis-v<N>.json and can always be recomputed from
the raw recording. Version 1 covers posture and heart rate; ectopic beat (VES) detection
is added in stage 5 and bumps the version, which makes the scheduler redo old nights.
"""
from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing as mp
import os
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, Optional

import numpy as np

from . import posture as P
from .storage import list_session_dirs, read_meta, write_json_atomic

log = logging.getLogger(__name__)

ANALYSIS_VERSION = 6  # 4: premature beats from ECG R peaks + QRS morphology; 5: AF episodes, runs, adaptive threshold;
# 6: local-threshold QRS detector with search-back, P wave required to be absent for an AF episode


def result_path(session_dir: Path) -> Path:
    return session_dir / "cache" / f"analysis-v{ANALYSIS_VERSION}.json"


def beats_path(session_dir: Path) -> Path:
    """Every R peak of the recording (ms from the start), for the viewer's RR plot."""
    return session_dir / "cache" / f"beats-v{ANALYSIS_VERSION}.json"


def read_beats(session_dir: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(beats_path(session_dir).read_text())
    except (OSError, ValueError):
        return None


def write_beats(session_dir: Path, r_peaks: np.ndarray) -> Dict[str, Any]:
    out = {"version": ANALYSIS_VERSION, "t_ms": [int(round(float(x) * 1000)) for x in r_peaks]}
    write_json_atomic(beats_path(session_dir), out)
    return out


def compute_beats(session_dir: Path) -> Dict[str, Any]:
    """R peaks for a recording analysed before beat lists were saved: the same detector as the analysis."""
    from .beats import classify_beats
    from .sessions import assemble

    s = assemble(session_dir)
    if len(s.ecg_uv) <= s.ecg_fs * 120:
        return write_beats(session_dir, np.zeros(0))
    res = classify_beats(s.ecg_t, s.ecg_uv, s.ecg_fs, s.duration, s.no_contact)
    return write_beats(session_dir, np.asarray(res.get("r_peaks", np.zeros(0)), dtype=float))


def progress_path(session_dir: Path) -> Path:
    return session_dir / "cache" / "analysis.progress"


def read_result(session_dir: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(result_path(session_dir).read_text())
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------- worker (separate process)

def _lower_priority() -> None:
    try:
        os.nice(10)
    except (OSError, AttributeError):  # os.nice does not exist on Windows
        pass
    # one core is plenty and keeps a small home server's fan quiet
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[var] = "1"


def run_analysis(session_dir_str: str, home_str: str) -> Dict[str, Any]:
    from .sessions import assemble, summarize

    d, home = Path(session_dir_str), Path(home_str)
    (d / "cache").mkdir(exist_ok=True)
    prog = progress_path(d)

    def step(x: float) -> None:
        prog.write_text(f"{x:.2f}")

    t_start = time.time()
    step(0.05)
    s = assemble(d)
    step(0.35)
    summary = summarize(s)
    step(0.55)
    store = P.CalibrationStore(home)
    cal, how = store.for_session(d, s.meta)
    sec = P.per_second(s.acc_t, s.acc_mg, s.duration)
    posture: Dict[str, Any] = {"calibrated": False}
    cls = None
    if cal is not None:
        r = P.classify_night(sec, cal)
        cls = r["cls"]
        times = P.time_per_class(cls)
        lying_total = sum(times[p] for p in P.LYING) or 1
        posture = {
            "calibrated": True,
            "calibration_id": cal.id,
            "calibration_how": how,
            "seconds": times,
            "share_of_lying": {p: round(times[p] / lying_total, 4) for p in P.LYING},
            "transitions": int(np.sum(np.diff(cls[(cls >= 0) & (cls != P.MOVING)]) != 0)) if len(cls) else 0,
            "warnings": r["warnings"],
        }
    step(0.75)

    # heart rate per posture and per clock hour, from the strap's 1 Hz HR
    hr_post: Dict[str, Any] = {}
    if cls is not None and len(s.hr_t):
        i = np.clip(s.hr_t.astype(int), 0, len(cls) - 1)
        c = cls[i]
        for k, name in enumerate(P.CLASS_NAMES):
            v = s.hr_bpm[(c == k) & (s.hr_bpm > 0)]
            if len(v) >= 30:
                hr_post[name] = {"mean": round(float(v.mean()), 1), "min": int(v.min()), "max": int(v.max())}
    t0 = s.meta["started_wall_ns"] / 1e9
    hours = []
    if len(s.hr_t):
        wall = t0 + s.hr_t
        hour_start = np.floor(wall / 3600) * 3600
        for h in np.unique(hour_start):
            m = (hour_start == h) & (s.hr_bpm > 0)
            if m.sum() < 60:
                continue
            row: Dict[str, Any] = {"hour": datetime.fromtimestamp(h).strftime("%H:00"),
                                   "hr_mean": round(float(s.hr_bpm[m].mean()), 1), "minutes": round(m.sum() / 60, 1)}
            if cls is not None:
                idx = np.clip(s.hr_t[m].astype(int), 0, len(cls) - 1)
                cc = cls[idx]
                cc = cc[(cc >= 0) & (cc != P.MOVING)]
                if len(cc):
                    row["posture"] = P.CLASS_NAMES[int(np.bincount(cc, minlength=6).argmax())]
            hours.append(row)

    step(0.85)
    hrv = heart_rate_variability(s.rr_t, s.rr_ms, cls)
    if len(s.ecg_uv) > s.ecg_fs * 120:
        ect = ectopy_ecg(s.ecg_t, s.ecg_uv, s.ecg_fs, s.duration, s.no_contact, cls, t0)
    else:
        ect = ectopy(s.rr_t, s.rr_ms, cls, t0)

    r_peaks = ect.pop("_r_peaks", None)
    if r_peaks is not None:
        write_beats(d, np.asarray(r_peaks, dtype=float))
    result = {
        "version": ANALYSIS_VERSION,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "runtime_s": round(time.time() - t_start, 1),
        "summary": {k: v for k, v in summary.items() if k not in ("hr_spark", "gaps")},
        "posture": posture,
        "hr_by_posture": hr_post,
        "hours": hours,
        "hrv": hrv,
        "ectopy": ect,  # premature beats from the ECG (fallback: strap RR)
        "ves": None,  # stage 5: ECG morphology
    }
    write_json_atomic(result_path(d), result)
    step(1.0)
    prog.unlink()
    return {"runtime_s": result["runtime_s"]}


def premature_beats(rr: np.ndarray) -> np.ndarray:
    """Indices i where beat i is premature with a compensatory pause (interim, RR only).

    Reference = local median of pair means (rr[i] + rr[i+1]) / 2: around an ectopic beat
    with a full compensatory pause the pair mean equals the normal interval, so the
    reference stays right even in bigeminy where every other beat is ectopic.
    """
    n = len(rr)
    if n < 12:
        return np.zeros(0, dtype=int)
    pair = (rr[:-1] + rr[1:]) / 2
    k = 15
    pad = np.pad(pair, k, mode="edge")
    ref = np.median(np.lib.stride_tricks.sliding_window_view(pad, 2 * k + 1), axis=1)  # len n-1
    short = rr[:-1] < 0.8 * ref
    pause = rr[1:] > 1.05 * ref
    total = (rr[:-1] + rr[1:]) / ref
    comp = (total > 1.75) & (total < 2.25)
    plausible = (rr[:-1] > 250) & (rr[1:] < 3000)
    return np.nonzero(short & pause & comp & plausible)[0]


def ectopy(rr_t: np.ndarray, rr_ms: np.ndarray, cls: Optional[np.ndarray], t0_wall: float) -> Dict[str, Any]:
    """Fallback when there is no usable ECG: premature beats from the strap's RR intervals."""
    order = np.argsort(rr_t, kind="stable")
    t, rr = rr_t[order], rr_ms[order]
    # the strap reports an interval when it ends: the premature beat is the end of rr[i]
    return _ectopy_summary(t, premature_beats(rr), cls, t0_wall, "rr_compensatory_pause")


def ectopy_ecg(ecg_t: np.ndarray, ecg_uv: np.ndarray, fs: float, duration: float, no_contact: Any,
               cls: Optional[np.ndarray], t0_wall: float) -> Dict[str, Any]:
    """Premature beats from R peaks detected in the ECG, with QRS morphology (beats.py)."""
    from .beats import classify_beats

    res = classify_beats(ecg_t, ecg_uv, fs, duration, no_contact)
    beats_t = res.get("r_peaks", np.zeros(0))
    ev = np.array(res["events"], dtype=float)
    idx = np.clip(np.searchsorted(beats_t, ev - 1e-6), 0, max(0, len(beats_t) - 1)) if len(beats_t) else np.zeros(0, int)
    out = _ectopy_summary(beats_t, idx.astype(int), cls, t0_wall, "ecg")
    out["events"] = [round(float(x), 3) for x in ev]
    out["details"] = res["details"]
    out["_r_peaks"] = beats_t  # saved to its own file, not into the result
    out["ves"] = sum(1 for d in res["details"] if d["kind"] == "ves")
    out["sves"] = sum(1 for d in res["details"] if d["kind"] == "sves")
    out["unclassified"] = sum(1 for d in res["details"] if d["kind"] == "premature")
    out["couplets"] = sum(1 for d in res["details"] if d.get("couplet")) // 2
    # v5: runs of >= 3 premature beats and irregular-rhythm (possible atrial fibrillation) episodes
    out["runs"] = res.get("runs", [])
    out["af_episodes"] = res.get("af_episodes", [])
    out["af_seconds"] = round(sum(e["duration_s"] for e in out["af_episodes"]), 1)
    out["ves_morphology_only"] = sum(1 for d in res["details"] if d["kind"] == "ves" and not d.get("premature", True))
    return out


def _ectopy_summary(t: np.ndarray, idx: np.ndarray, cls: Optional[np.ndarray], t0_wall: float, method: str) -> Dict[str, Any]:
    """Counts per posture / hour and bigeminy runs; t = every beat's time, idx = premature ones."""
    ev_t = t[idx] if len(idx) else np.zeros(0)
    out: Dict[str, Any] = {
        "method": method,
        "count": int(len(idx)),
        "beats": int(len(t)),
        "share": round(len(idx) / len(t), 6) if len(t) else None,
        "events": [round(float(x), 2) for x in ev_t],
    }
    # runs: bigeminy = premature beats on every other beat
    runs = 0
    if len(idx) >= 3:
        gaps = np.diff(idx)
        k = 0
        for g in gaps:
            k = k + 1 if g == 2 else 0
            if k == 2:  # three in alternation
                runs += 1
    out["bigeminy_runs"] = runs
    if cls is not None and len(cls):
        beat_cls = cls[np.clip(t.astype(int), 0, len(cls) - 1)]
        ev_cls = beat_cls[idx]
        seconds = P.time_per_class(cls)
        by: Dict[str, Any] = {}
        for k2, name in enumerate(P.CLASS_NAMES):
            n_beats = int(np.sum(beat_cls == k2))
            c = int(np.sum(ev_cls == k2))
            if n_beats == 0 and c == 0:
                continue
            # rates over very short stays (a 50 s bathroom trip) are noise: count only
            rate_ok = seconds[name] >= 60
            by[name] = {"count": c, "per_hour": round(c / (seconds[name] / 3600), 2) if rate_ok else None,
                        "share": round(c / n_beats, 6) if n_beats and rate_ok else None, "beats": n_beats}
        # beats with no posture at all (no ACC data) so that the rows always add up to the total
        unknown = int(np.sum(ev_cls < 0))
        if unknown:
            by["unknown"] = {"count": unknown, "per_hour": None, "share": None, "beats": int(np.sum(beat_cls < 0))}
        out["by_posture"] = by
    hours: Dict[str, int] = {}
    for x in ev_t:
        h = datetime.fromtimestamp(t0_wall + x).strftime("%H:00")
        hours[h] = hours.get(h, 0) + 1
    out["by_hour"] = hours
    return out


HRV_WINDOW_S = 300


def nn_mask(rr: np.ndarray) -> np.ndarray:
    """Normal-to-normal beats: plausible and within 20 % of the local median.

    Interim filter until stage 5 classifies beats from the ECG: an ectopic beat is short and
    its compensatory pause long, so both fall outside the band and are excluded.
    """
    ok = (rr > 300) & (rr < 2000)
    if len(rr) < 5:
        return ok
    k = 5
    pad = np.pad(rr, k, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(pad, 2 * k + 1)
    med = np.median(windows, axis=1)
    return ok & (np.abs(rr - med) < 0.2 * med)


def heart_rate_variability(rr_t: np.ndarray, rr_ms: np.ndarray, cls: Optional[np.ndarray]) -> Dict[str, Any]:
    """RMSSD and SDNN in 5-minute windows from the strap's RR intervals."""
    if len(rr_ms) < 100:
        return {"windows": [], "source": "strap_rr", "filter": "median20"}
    order = np.argsort(rr_t, kind="stable")
    t, rr = rr_t[order], rr_ms[order]
    nn = nn_mask(rr)
    pair = nn[1:] & nn[:-1]  # successive differences only between two normal beats
    d = np.diff(rr)
    windows = []
    for w0 in np.arange(0, t[-1], HRV_WINDOW_S):
        a, b = np.searchsorted(t, [w0, w0 + HRV_WINDOW_S])
        n = b - a
        if n < 150:
            continue
        sel = nn[a:b]
        p = pair[a:max(a, b - 1)]
        dd = d[a:max(a, b - 1)][p]
        if sel.mean() < 0.8 or len(dd) < 100:
            windows.append({"t": float(w0), "rmssd": None, "sdnn": None, "beats": int(n), "rejected": round(1 - float(sel.mean()), 3)})
            continue
        row = {"t": float(w0), "rmssd": round(float(np.sqrt(np.mean(dd ** 2))), 1),
               "sdnn": round(float(np.std(rr[a:b][sel], ddof=1)), 1), "beats": int(n),
               "rejected": round(1 - float(sel.mean()), 3)}
        if cls is not None and len(cls):
            cc = cls[int(w0):int(min(len(cls), w0 + HRV_WINDOW_S))]
            cc = cc[(cc >= 0) & (cc != P.MOVING)]
            if len(cc) > HRV_WINDOW_S * 0.6:
                row["posture"] = P.CLASS_NAMES[int(np.bincount(cc, minlength=6).argmax())]
        windows.append(row)
    valid = [w for w in windows if w["rmssd"] is not None]
    by_posture: Dict[str, Any] = {}
    for name in P.CLASS_NAMES:
        vals = [w["rmssd"] for w in valid if w.get("posture") == name]
        if len(vals) >= 2:
            by_posture[name] = {"rmssd_median": round(float(np.median(vals)), 1), "windows": len(vals)}
    return {
        "source": "strap_rr",
        "filter": "median20",
        "window_s": HRV_WINDOW_S,
        "rmssd_median": round(float(np.median([w["rmssd"] for w in valid])), 1) if valid else None,
        "sdnn_median": round(float(np.median([w["sdnn"] for w in valid])), 1) if valid else None,
        "rejected_share": round(1 - float(nn.mean()), 4),
        "by_posture": by_posture,
        "windows": windows,
    }


# --------------------------------------------------------------------------- manager (server process)

class Analyzer:
    def __init__(self, cfg: Any, collector: Any):
        self.cfg = cfg
        self.collector = collector
        self.queue: Deque[str] = deque()
        self.running: Optional[str] = None
        self.errors: Dict[str, str] = {}
        self._wake = asyncio.Event()
        self._pool: Optional[ProcessPoolExecutor] = None
        self.state_path = cfg.home / "state.json"
        self.calibrations = P.CalibrationStore(cfg.home)
        self._last_purge = 0.0

    # ---- status

    def needs_analysis(self, d: Path, meta: Dict[str, Any]) -> bool:
        if meta.get("state") != "closed":
            return False
        res = read_result(d)
        if res is None:
            return True
        cal, _ = self.calibrations.for_session(d, meta)
        return (cal.id if cal else None) != res.get("posture", {}).get("calibration_id")

    def status(self, d: Path, meta: Dict[str, Any]) -> Dict[str, Any]:
        sid = d.name
        res = read_result(d)
        st: Dict[str, Any] = {"version": ANALYSIS_VERSION, "scheduled_at": self.cfg.analysis_time}
        if self.running == sid:
            try:
                st["progress"] = float(progress_path(d).read_text())
            except (OSError, ValueError):
                st["progress"] = 0.0
            st["state"] = "running"
        elif sid in self.queue:
            st["state"] = "queued"
        elif sid in self.errors:
            st["state"] = "error"
            st["error"] = self.errors[sid]
        elif meta.get("state") != "closed":
            st["state"] = "recording"
        elif res is None:
            st["state"] = "pending"
        elif self.needs_analysis(d, meta):
            st["state"] = "stale"
        else:
            st["state"] = "done"
        if res is not None:
            st["created_at"] = res.get("created_at")
        if st["state"] in ("pending", "stale") and self._overdue():
            st["deferred"] = "recording" if self.collector.session is not None else "starting"
        return st

    def _overdue(self) -> bool:
        if not self.cfg.analysis_time:
            return False
        now = datetime.now()
        hh, mm = (int(x) for x in self.cfg.analysis_time.split(":"))
        return now >= now.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # ---- control

    def request(self, session_id: str) -> None:
        self.errors.pop(session_id, None)
        if session_id != self.running and session_id not in self.queue:
            self.queue.append(session_id)
            self._wake.set()

    def request_all(self, only_needed: bool = True) -> int:
        n = 0
        for d in reversed(list_session_dirs(self.cfg.sessions_dir)):  # oldest first
            meta = read_meta(d) or {}
            if meta.get("state") == "closed" and (not only_needed or self.needs_analysis(d, meta)):
                self.request(d.name)
                n += 1
        return n

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        loop.create_task(self._scheduler())
        while True:
            if not self.queue:
                self._wake.clear()
                await self._wake.wait()
                continue
            sid = self.queue.popleft()
            d = self.cfg.sessions_dir / sid
            if not (d / "meta.json").exists():
                continue
            self.running = sid
            log.info("analysis started: %s", sid)
            try:
                if self._pool is None:
                    self._pool = ProcessPoolExecutor(1, mp_context=mp.get_context("spawn"), initializer=_lower_priority)
                info = await loop.run_in_executor(self._pool, run_analysis, str(d), str(self.cfg.home))
                log.info("analysis done: %s (%.1f s)", sid, info["runtime_s"])
            except Exception as e:  # keep the server alive, show the error in the UI
                log.exception("analysis failed: %s", sid)
                self.errors[sid] = str(e) or e.__class__.__name__
                if self._pool is not None:
                    self._pool.shutdown(wait=False, cancel_futures=True)
                    self._pool = None
            finally:
                self.running = None
                if not self.queue and self._pool is not None:
                    self._pool.shutdown(wait=False)  # free the worker's memory between runs
                    self._pool = None

    async def _scheduler(self) -> None:
        """Once a day at analysis_time, catch up on missed days, never during a recording."""
        while True:
            try:
                self._tick()
            except Exception:
                log.exception("scheduler")
            await asyncio.sleep(30)

    def _tick(self) -> None:
        if time.time() - self._last_purge > 3600:
            from .trash import Trash
            self._last_purge = time.time()
            n = Trash(self.cfg.home, self.cfg.sessions_dir).purge_expired()
            if n:
                log.info("trash: purged %d recording(s) older than 30 days", n)
        at = self.cfg.analysis_time
        if not at:
            return
        now = datetime.now()
        hh, mm = (int(x) for x in at.split(":"))
        due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        today = now.strftime("%Y-%m-%d")
        state = self._read_state()
        if now < due or state.get("last_scheduled_run") == today:
            return
        if self.collector.session is not None:
            return  # wait until the recording ends
        n = self.request_all(only_needed=True)
        log.info("scheduled analysis: %d night(s) queued", n)
        state["last_scheduled_run"] = today
        write_json_atomic(self.state_path, state)

    def _read_state(self) -> Dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return {}

    def shutdown(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
