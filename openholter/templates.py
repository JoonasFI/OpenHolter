"""Beat templates for the viewer: beats grouped by QRS shape, as in clinical Holter software.

Reading a recording beat by beat is slow. Grouping beats by shape lets the reader check whole
groups at once: the usual beat, each distinct VES shape, SVES, and normal-labelled beats whose shape
differs from the usual one (often artefact, sometimes a missed extra beat). Each group carries its
median waveform, a few member beats to draw on top of each other, and the times of its beats.

This only groups what the analysis already found; it changes no labels or counts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from .analysis import ANALYSIS_VERSION, compute_beats, read_beats, read_result
from .beats import _movavg
from .sessions import assemble
from .storage import write_json_atomic

TEMPLATES_VERSION = 2        # bump when the grouping changes: older cached groupings are ignored
PRE_S, POST_S = 0.25, 0.45   # window around the R peak
# Set on the author's own H10 recordings (one night, four short recordings): on the chest lead normal
# beats correlate 0.7-0.95 with the usual beat (noise, breathing), VES about 0.4-0.75. Below 0.65 a
# normal-labelled beat is clearly different (0.0-0.4 % of beats; 0.8 had flagged 12 %).
ODD_CORR = 0.65              # a normal-labelled beat this unlike the usual beat is shown apart
CLUSTER_CORR = 0.80          # VES joins a group when it correlates this well with the group's mean
MAX_GROUPS = 8               # VES shapes shown separately at most
MIN_GROUP = 3                # ...and only if they have at least this many beats (or 2 % of all VES);
                             # single noisy beats would otherwise each become a "shape"
EXAMPLES = 24                # member beats drawn on top of each other
NORMAL_SAMPLE = 3000         # beats used for the usual beat's median


def templates_path(session_dir: Path) -> Path:
    return session_dir / "cache" / f"templates-v{ANALYSIS_VERSION}.{TEMPLATES_VERSION}.json"


def read_templates(session_dir: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(templates_path(session_dir).read_text())
    except (OSError, ValueError):
        return None


def _unit_rows(w: np.ndarray) -> np.ndarray:
    w = w - w.mean(axis=1, keepdims=True)
    return w / np.maximum(np.linalg.norm(w, axis=1, keepdims=True), 1e-9)


def _group(kind: str, label: str, rows: np.ndarray, times: np.ndarray, rng: np.random.Generator,
           with_times: bool = True) -> Dict[str, Any]:
    pick = rows if len(rows) <= EXAMPLES else rows[rng.choice(len(rows), EXAMPLES, replace=False)]
    return {
        "kind": kind, "label": label, "count": int(len(rows)),
        "mean": [int(round(x)) for x in np.median(rows, axis=0)],
        "examples": [[int(round(x)) for x in r] for r in pick],
        "t": [round(float(x), 3) for x in times] if with_times else [],
    }


def compute_templates(session_dir: Path) -> Dict[str, Any]:
    d = Path(session_dir)
    s = assemble(d)
    b = read_beats(d) or compute_beats(d)
    rt = np.asarray(b.get("t_ms") or [], dtype=float) / 1000
    res = read_result(d) or {}
    details = ((res.get("ectopy") or {}).get("details")) or []
    fs = float(s.ecg_fs)
    out: Dict[str, Any] = {"version": ANALYSIS_VERSION, "templates_version": TEMPLATES_VERSION, "fs": fs, "pre_s": PRE_S, "templates": []}
    if len(rt) < 10 or len(s.ecg_uv) < fs * 10:
        write_json_atomic(templates_path(d), out)
        return out

    t = s.ecg_t
    v = s.ecg_uv.astype(np.float64)
    k = int(round(0.6 * fs))
    base = v - _movavg(_movavg(v, k), k)  # baseline wander removed, QRS kept
    pre, post = int(round(PRE_S * fs)), int(round(POST_S * fs))
    idx = np.searchsorted(t, rt)
    ok = (idx - pre >= 0) & (idx + post < len(t))
    idx_ok = np.clip(idx, pre, len(t) - post - 1)
    # the window must be one continuous stretch of samples (no gap inside it)
    ok &= (t[idx_ok + post] - t[idx_ok - pre]) < (pre + post + 3) / fs
    idx, rt = idx[ok], rt[ok]
    win = base[idx[:, None] + np.arange(-pre, post)[None, :]]

    kind = np.zeros(len(rt), dtype=np.int8)  # 0 normal, 1 VES, 2 SVES
    for det in details:
        i = int(np.searchsorted(rt, det["t"] - 0.01))
        if i < len(rt) and abs(rt[i] - det["t"]) < 0.01:
            kind[i] = 2 if det.get("kind") == "sves" else 1

    rng = np.random.default_rng(0)
    groups: List[Dict[str, Any]] = []
    normal = np.nonzero(kind == 0)[0]
    if len(normal):
        sample = normal if len(normal) <= NORMAL_SAMPLE else rng.choice(normal, NORMAL_SAMPLE, replace=False)
        usual = np.median(win[sample], axis=0)
        # elementwise rather than matmul: numpy + Accelerate on older macOS emits spurious FP warnings
        c = np.sum(_unit_rows(win[normal]) * _unit_rows(usual[None, :]), axis=1)
        odd = normal[c < ODD_CORR]
        typical = normal[c >= ODD_CORR]
        if len(typical):
            groups.append(_group("N", "usual", win[typical], rt[typical], rng, with_times=False))
        if len(odd):
            groups.append(_group("N_odd", "odd", win[odd], rt[odd], rng))

    ves = np.nonzero(kind == 1)[0]
    if len(ves):
        units = _unit_rows(win[ves])
        sums: List[np.ndarray] = []
        members: List[List[int]] = []
        for j, u in enumerate(units):
            best, bc = -1, CLUSTER_CORR
            for g, sm in enumerate(sums):
                cc = float(np.sum(u * sm) / max(float(np.sqrt(np.sum(sm * sm))), 1e-9))
                if cc >= bc:
                    best, bc = g, cc
            if best < 0:
                sums.append(u.copy()); members.append([j])
            else:
                sums[best] += u; members[best].append(j)
        order = sorted(range(len(members)), key=lambda g: -len(members[g]))
        least = max(MIN_GROUP, int(np.ceil(0.02 * len(ves))))
        big = [g for g in order if len(members[g]) >= least]
        shown = big[:MAX_GROUPS]
        rest = [g for g in order if g not in shown]
        for n, g in enumerate(shown):
            rows = ves[members[g]]
            groups.append(_group("VES", chr(ord("A") + n), win[rows], rt[rows], rng))
        if rest:
            rows = ves[[j for g in rest for j in members[g]]]
            # no shape common enough to show apart: then they are simply "VES", not "other shapes"
            groups.append(_group("VES", "other" if shown else "all", win[rows], rt[rows], rng))

    sves = np.nonzero(kind == 2)[0]
    if len(sves):
        groups.append(_group("SVES", "", win[sves], rt[sves], rng))

    out["templates"] = groups
    write_json_atomic(templates_path(d), out)
    return out
