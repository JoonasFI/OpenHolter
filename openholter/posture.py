"""Body posture from the H10 accelerometer.

At rest the accelerometer measures the reaction to gravity: a ~1000 mG vector pointing
"up" in the sensor's own frame. A calibration stores that vector for known postures:

    supine (required), left side (required), right side, prone (optional)

From supine and left the body's long axis is b = supine × left (gravity turns around it
when rolling over). For any sample:

    upright   if the gravity component along b is large (sitting/standing)
    otherwise the roll angle around b, measured from supine (left side is positive),
              is matched to the nearest calibrated posture.

Rolling of the strap around the chest is indistinguishable from turning over, which is
why recalibration (also retroactively from a night's own data) is supported.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


import numpy as np

from .i18n import tr

POSTURES = ["supine", "left", "right", "prone", "upright"]
MOVING = 5
NO_DATA = -1
CLASS_NAMES = POSTURES + ["moving"]  # "moving" is shown as "Kääntyminen"
LYING = ["supine", "left", "right", "prone"]

UPRIGHT_AXIS = 0.70  # |cos| to the long axis; ~45° from horizontal
MIN_SEGMENT_S = 30  # shorter postures are merged into their neighbours
MOVE_ANGLE_DEG = 15.0  # direction change between consecutive seconds
MOVE_MAG_STD = 60.0  # mG, std of |a| within one second


def _dot(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    # elementwise instead of matmul: numpy + Accelerate on older macOS emits spurious FP warnings
    return np.sum(np.asarray(a) * np.asarray(b), axis=-1)


def _unit(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-9)


@dataclass
class Calibration:
    id: str
    created_wall_ns: int
    source: str
    refs: Dict[str, np.ndarray]  # posture -> unit vector (sensor frame)
    meta: Dict[str, Any]

    def __post_init__(self) -> None:
        s, l = _unit(self.refs["supine"]), _unit(self.refs["left"])
        b = np.cross(s, l)
        if np.linalg.norm(b) < 0.3:
            raise ValueError("supine and left side are too similar to define the body axis")
        self.axis = _unit(b)
        self.supine = _unit(s - _dot(s, self.axis) * self.axis)
        self.centers: Dict[str, float] = {"supine": 0.0}
        left = self.roll(l[None])[0]
        self.centers["left"] = float(left)
        self.centers["right"] = float(self.roll(_unit(self.refs["right"])[None])[0]) if "right" in self.refs else -float(left)
        self.centers["prone"] = float(self.roll(_unit(self.refs["prone"])[None])[0]) if "prone" in self.refs else 180.0

    def roll(self, u: np.ndarray) -> np.ndarray:
        """Roll angle (deg) around the body axis, 0 = supine, left side positive."""
        p = u - _dot(u, self.axis)[:, None] * self.axis
        sin = _dot(np.cross(self.supine, p), self.axis)
        cos = _dot(p, self.supine)
        return np.degrees(np.arctan2(sin, cos))

    def angles(self, u: np.ndarray) -> Tuple[float, float]:
        """(roll, pitch) in degrees for one unit vector: roll around the body axis (0 supine,
        left side positive), pitch = how far the head end is raised (90 = sitting/standing)."""
        pitch = float(np.degrees(np.arcsin(np.clip(_dot(u, self.axis), -1, 1))))
        return float(self.roll(u[None])[0]), pitch

    def classify(self, u: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Class index per unit vector and angular distance (deg) to the matched centre."""
        along = np.abs(_dot(u, self.axis))
        r = self.roll(u)
        names = LYING
        c = np.array([self.centers[n] for n in names])
        d = np.abs(((r[:, None] - c[None, :]) + 180) % 360 - 180)
        best = np.argmin(d, axis=1)
        cls = np.array([POSTURES.index(names[i]) for i in best])
        dist = d[np.arange(len(r)), best]
        up = along > UPRIGHT_AXIS
        cls[up] = POSTURES.index("upright")
        dist[up] = 0.0
        return cls, dist

    def quality(self) -> Dict[str, Any]:
        """Sanity numbers shown after calibrating."""
        warnings = []
        left = abs(self.centers["left"])
        if not 55 <= left <= 125:
            warnings.append(tr("Selällään ja vasemman kyljen välinen kulma on {0:.0f}°, odotettu noin 90°.", "The angle between supine and left side is {0:.0f}°, expected about 90°.").format(left))
        if "right" in self.refs and self.centers["right"] * self.centers["left"] > 0:
            warnings.append("Oikea kylki on samalla puolella kuin vasen. Tarkista kyljet.")
        if "prone" in self.refs and abs(self.centers["prone"]) < 120:
            warnings.append(tr("Vatsallaan poikkeaa selällään-asennosta vain {0:.0f}°.", "Prone differs from supine by only {0:.0f}°.").format(abs(self.centers['prone'])))
        tilt = max(abs(float(_dot(_unit(v), self.axis))) for v in self.refs.values())
        if tilt > 0.4:
            warnings.append(tr("Jokin asento oli kalteva (pääpuoli koholla?). Makaa mahdollisimman vaakatasossa.", "One of the postures was tilted (head end raised?). Lie as flat as you can."))
        return {"angles": {k: round(v, 1) for k, v in self.centers.items()}, "warnings": warnings}

    def to_json(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "created_wall_ns": self.created_wall_ns,
            "created_at": datetime.fromtimestamp(self.created_wall_ns / 1e9).astimezone().isoformat(timespec="seconds"),
            "source": self.source,
            "refs": {k: [round(float(x), 5) for x in _unit(v)] for k, v in self.refs.items()},
            **self.meta,
            "quality": self.quality(),
        }


# --------------------------------------------------------------------------- storage

class CalibrationStore:
    def __init__(self, root: Path):
        self.dir = root / "calibrations"
        self.dir.mkdir(parents=True, exist_ok=True)

    def all(self) -> List[Calibration]:
        out = []
        for p in sorted(self.dir.glob("*.json")):
            try:
                d = json.loads(p.read_text())
                out.append(Calibration(d["id"], d["created_wall_ns"], d.get("source", "live"),
                                       {k: np.array(v) for k, v in d["refs"].items()},
                                       {k: d[k] for k in ("measurements", "note") if k in d}))
            except (OSError, ValueError, KeyError):
                continue
        return sorted(out, key=lambda c: c.created_wall_ns)

    def get(self, cal_id: str) -> Optional[Calibration]:
        return next((c for c in self.all() if c.id == cal_id), None)

    def latest(self) -> Optional[Calibration]:
        cals = self.all()
        return cals[-1] if cals else None

    def create(self, refs: Dict[str, Any], source: str, measurements: Optional[Dict[str, Any]] = None) -> Calibration:
        now = time.time_ns()
        cal_id = datetime.fromtimestamp(now / 1e9).strftime("%Y-%m-%d_%H%M%S")
        cal = Calibration(cal_id, now, source, {k: _unit(np.array(v, dtype=float)) for k, v in refs.items()},
                          {"measurements": measurements or {}})
        from .storage import write_json_atomic
        write_json_atomic(self.dir / f"{cal_id}.json", cal.to_json())
        return cal

    def for_session(self, session_dir: Path, meta: Dict[str, Any]) -> Tuple[Optional[Calibration], str]:
        """Effective calibration: explicit choice, else latest made before the night ended,
        else the nearest one made later (the H10 clips in one way, so it is still close)."""
        choice = _read_choice(session_dir)
        cals = self.all()
        if choice:
            c = next((c for c in cals if c.id == choice), None)
            if c:
                return c, "chosen"
        if not cals:
            return None, "none"
        end = meta.get("ended_wall_ns") or time.time_ns()
        before = [c for c in cals if c.created_wall_ns <= end]
        if before:
            return before[-1], "auto"
        return cals[0], "later"


def _read_choice(session_dir: Path) -> Optional[str]:
    p = session_dir / "calibration.json"
    try:
        return json.loads(p.read_text()).get("calibration_id")
    except (OSError, ValueError):
        return None


def set_choice(session_dir: Path, cal_id: Optional[str]) -> None:
    from .storage import write_json_atomic
    p = session_dir / "calibration.json"
    if cal_id is None:
        if p.exists():
            p.unlink()
    else:
        write_json_atomic(p, {"calibration_id": cal_id})


# --------------------------------------------------------------------------- measurement

def measure(samples: np.ndarray) -> Dict[str, Any]:
    """Summarise ACC samples (mG) captured while lying still in one posture."""
    g = np.asarray(samples, dtype=np.float64)
    if len(g) < 50:
        return {"ok": False, "reason": tr("liian vähän dataa", "too little data"), "n": int(len(g))}
    mag = np.linalg.norm(g, axis=1)
    u = _unit(g)
    mean = _unit(u.mean(axis=0))
    spread = float(np.degrees(np.arccos(np.clip(_dot(u, mean), -1, 1))).mean())  # mean deviation from the mean direction
    res = {"g": [round(float(x), 5) for x in mean], "magnitude": round(float(mag.mean()), 1),
           "mag_std": round(float(mag.std()), 1), "spread_deg": round(spread, 2), "n": int(len(g))}
    if not 850 <= res["magnitude"] <= 1150:
        res.update(ok=False, reason=f"kiihtyvyys {res['magnitude']:.0f} mG, odotettu noin 1000 mG")
    elif spread > 8 or res["mag_std"] > 80:
        res.update(ok=False, reason=tr("liikettä havaittu, makaa paikallasi", "movement detected, keep still"))
    else:
        res.update(ok=True, reason="")
    return res


# --------------------------------------------------------------------------- per-second track

def per_second(acc_t: np.ndarray, acc_mg: np.ndarray, duration: float) -> Dict[str, np.ndarray]:
    """1 s means of direction, plus a movement flag."""
    n = int(np.ceil(duration)) if duration > 0 else 0
    edges = np.arange(n + 1, dtype=np.float64)
    idx = np.searchsorted(acc_t, edges)
    counts = np.diff(idx)
    have = counts > 0
    g = acc_mg.astype(np.float64)
    mag = np.linalg.norm(g, axis=1) if len(g) else np.zeros(0)
    mean = np.zeros((n, 3))
    mstd = np.zeros(n)
    if have.any():
        starts = idx[:-1][have]
        sums = np.add.reduceat(g, starts, axis=0)[: have.sum()]
        # reduceat of the last non-empty bin runs to the array end; recompute it exactly
        last = np.nonzero(have)[0][-1]
        sums[-1] = g[idx[last]:idx[last + 1]].sum(axis=0)
        mean[have] = sums / counts[have, None]
        m1 = np.add.reduceat(mag, starts)[: have.sum()]
        m2 = np.add.reduceat(mag ** 2, starts)[: have.sum()]
        m1[-1], m2[-1] = mag[idx[last]:idx[last + 1]].sum(), (mag[idx[last]:idx[last + 1]] ** 2).sum()
        c = counts[have]
        mstd[have] = np.sqrt(np.maximum(m2 / c - (m1 / c) ** 2, 0))
    u = _unit(mean)
    turn = np.zeros(n)
    if n > 1:
        cosang = np.clip(np.sum(u[1:] * u[:-1], axis=1), -1, 1)
        turn[1:] = np.degrees(np.arccos(cosang))
        turn[1:][~(have[1:] & have[:-1])] = 0
    moving = have & ((turn > MOVE_ANGLE_DEG) | (mstd > MOVE_MAG_STD))
    # widen movement by a second each side: the mean of a second that contains a turn is in between postures
    moving = moving | np.roll(moving, 1) | np.roll(moving, -1)
    return {"u": u, "have": have, "moving": moving & have}


def classify_night(sec: Dict[str, np.ndarray], cal: Calibration) -> Dict[str, Any]:
    u, have, moving = sec["u"], sec["have"], sec["moving"]
    n = len(have)
    cls = np.full(n, NO_DATA, dtype=np.int8)
    dist = np.zeros(n)
    still = have & ~moving
    if still.any():
        c, d = cal.classify(u[still])
        cls[still] = c
        dist[still] = d
    cls[moving] = MOVING
    cls = _merge_short(cls)
    return {"cls": cls, "dist": dist, "warnings": _fit_warnings(u, cls, dist, cal)}


def _merge_short(cls: np.ndarray) -> np.ndarray:
    """Merge posture runs shorter than MIN_SEGMENT_S (ignoring movement/no-data) into the previous posture."""
    out = cls.copy()
    posture_idx = np.nonzero(out >= 0)[0]
    posture_idx = posture_idx[out[posture_idx] != MOVING]
    if len(posture_idx) == 0:
        return out
    vals = out[posture_idx]
    # runs over the posture-only sequence
    change = np.nonzero(np.diff(vals) != 0)[0] + 1
    starts = np.concatenate([[0], change])
    ends = np.concatenate([change, [len(vals)]])
    for _ in range(3):  # a few passes settle ping-pong between two short runs
        changed = False
        for k, (a, b) in enumerate(zip(starts, ends)):
            span = posture_idx[b - 1] - posture_idx[a] + 1
            if span < MIN_SEGMENT_S and len(starts) > 1:
                fill = vals[starts[k - 1]] if k > 0 else vals[ends[k]] if k + 1 < len(starts) else vals[a]
                if np.any(vals[a:b] != fill):
                    vals[a:b] = fill
                    changed = True
        if not changed:
            break
        change = np.nonzero(np.diff(vals) != 0)[0] + 1
        starts = np.concatenate([[0], change])
        ends = np.concatenate([change, [len(vals)]])
    out[posture_idx] = vals
    return out


def _fit_warnings(u: np.ndarray, cls: np.ndarray, dist: np.ndarray, cal: Calibration) -> List[str]:
    lying = np.isin(cls, [POSTURES.index(p) for p in LYING])
    if lying.sum() < 600:
        return []
    w = []
    tilt = np.median(np.abs(_dot(u[lying], cal.axis)))
    if tilt > 0.35:
        w.append(tr("Vyö näyttää kallistuneen kalibroinnin jälkeen. Asennot voivat olla epätarkkoja.", "The strap seems to have tilted since the calibration. Postures may be inaccurate."))
    far = np.mean(dist[lying] > 30)
    if far > 0.4:
        w.append(tr("{0:.0f} % makuuajasta ei vastaa yhtään kalibroitua asentoa hyvin. Vyö on ehkä kiertynyt. Harkitse jälkikalibrointia tästä tallenteesta.",
                    "{0:.0f} % of the lying time matches no calibrated posture well. The strap may have rotated. Consider retro-calibrating from this recording.").format(far * 100))
    return w


def refs_from_segments(sec: Dict[str, np.ndarray], segments: List[Dict[str, Any]]) -> Tuple[Dict[str, List[float]], Dict[str, Any]]:
    """Average still seconds of user-marked segments into reference vectors."""
    u, still = sec["u"], sec["have"] & ~sec["moving"]
    acc: Dict[str, List[np.ndarray]] = {}
    for s in segments:
        a, b = int(max(0, s["start"])), int(min(len(u), s["end"]))
        m = still[a:b]
        if m.sum() >= 5:
            acc.setdefault(s["posture"], []).append(u[a:b][m])
    refs, info = {}, {}
    for posture, parts in acc.items():
        v = np.concatenate(parts)
        mean = _unit(v.mean(axis=0))
        refs[posture] = [float(x) for x in mean]
        ang = np.degrees(np.arccos(np.clip(_dot(v, mean), -1, 1)))
        info[posture] = {"seconds": int(len(v)), "spread_deg": round(float(ang.mean()), 2)}
    return refs, info


def bucket_classes(cls: np.ndarray, points: int) -> List[Optional[str]]:
    """Majority class per display bucket."""
    n = len(cls)
    if n == 0:
        return []
    points = max(1, min(points, n))
    edges = np.linspace(0, n, points + 1).astype(int)
    out: List[Optional[str]] = []
    for a, b in zip(edges[:-1], edges[1:]):
        seg = cls[a:max(b, a + 1)]
        seg = seg[seg >= 0]
        if len(seg) == 0:
            out.append(None)
        else:
            out.append(CLASS_NAMES[int(np.bincount(seg, minlength=6).argmax())])
    return out


def time_per_class(cls: np.ndarray) -> Dict[str, int]:
    counts = np.bincount(cls[cls >= 0], minlength=6) if len(cls) else np.zeros(6, int)
    return {name: int(counts[i]) for i, name in enumerate(CLASS_NAMES)}
