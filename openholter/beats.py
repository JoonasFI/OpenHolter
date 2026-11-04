"""Beat detection and premature-beat classification from the ECG itself (analysis v5).

The strap's own RR intervals (BLE Heart Rate service) are convenient but opaque: while
the strap is being put on or taken off, or when its detector slips, they produce
short-long pairs that look exactly like ectopic beats. Here R peaks are found in the
130 Hz ECG directly:

1. Pan–Tompkins style detection: band-pass (difference of moving averages, ~5–15 Hz),
   derivative, squaring, 150 ms moving-window integration, adaptive threshold per 8 s
   block, 250 ms refractory period; the R peak is the largest |baseline-removed ECG|
   near the integrated peak. (Unchanged since v4.)
2. Artefact rejection: beats in segments whose amplitude is far above the recording's
   typical QRS amplitude, beats across data gaps, and the first/last minute (strap being
   put on / taken off) are excluded.
3. Morphology of every beat (v5): QRS window −80…+120 ms against the median of nearby
   normal beats; correlation at the R peak and the best correlation over ±40 ms shifts,
   QRS width difference and amplitude ratio. At 130 Hz one sample is 7.7 ms.
4. Irregular rhythm (v5): per beat, the median normalised RR difference over 31 intervals
   (minimum over lags 1–3, so bigeminy/trigeminy stay "regular"; intervals next to clearly
   ventricular beats left out). Episodes ≥ 30 s above 0.10 are reported as irregular rhythm
   (fits atrial fibrillation) and no SVES are labelled inside them.
5. Premature beats (v5): RR shorter than the local reference by 12–20 %, the required
   amount scaled to 3 × the robust local spread of RR. The reference is the larger of the
   centred median of pair means and the same median over the beats before (so that a long
   run does not drag its own reference down). Consecutive premature beats form a sequence:
   SVES need a sudden onset (< 90 % of the interval before) and an interval after that is
   at least as long as the premature one and ≥ 85 % of the reference (v4 demanded a pause
   > 105 %); VES (correlation < 0.85 or QRS ≥ 40 ms wider) need an interval after ≥ 95 %.
   Sequences of ≥ 3 at > 100/min are reported as runs.
6. VES by shape alone (v5): a clean beat that differs clearly from the template (correlation
   < 0.70 even at the best shift, and wider or 1.5 × larger) while both neighbours fit it,
   is a VES even when it is not premature.

All thresholds were tuned on MIT-BIH DS1 only; see docs/VALIDATION.md.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

EDGE_S = 60.0  # ignore the first and last minute: the strap is being put on / taken off
QRS_PRE, QRS_POST = 0.08, 0.12


def _movavg(x: np.ndarray, k: int) -> np.ndarray:
    k = max(1, int(k))
    if k == 1:
        return x.astype(np.float64)
    pad = np.pad(x.astype(np.float64), (k // 2, k - k // 2 - 1), mode="edge")
    c = np.cumsum(np.concatenate([[0.0], pad]))
    return (c[k:] - c[:-k]) / k


def detect_r_peaks(t: np.ndarray, uv: np.ndarray, fs: float) -> Tuple[np.ndarray, np.ndarray]:
    """Indices of R peaks and the baseline-removed signal they were located on."""
    if len(uv) < fs * 5:
        return np.zeros(0, dtype=int), uv.astype(np.float64)
    x = uv.astype(np.float64)
    base = x - _movavg(x, fs * 1.0)  # baseline wander removed, for locating R
    band = _movavg(x - _movavg(x, round(fs / 5)), 3)  # crude 5–15 Hz band-pass
    d = np.diff(band, prepend=band[0])
    e = _movavg(d * d, round(0.15 * fs))
    # adaptive threshold: 35 % of the 98th percentile of the energy in 8 s blocks (smoothed)
    blk = int(8 * fs)
    nb = int(np.ceil(len(e) / blk))
    lvl = np.array([np.percentile(e[i * blk:(i + 1) * blk], 98) for i in range(nb)])
    lvl = np.maximum(lvl, np.median(lvl) * 0.05)
    thr = 0.35 * np.repeat(lvl, blk)[: len(e)]
    cand = np.nonzero((e[1:-1] > thr[1:-1]) & (e[1:-1] >= e[:-2]) & (e[1:-1] > e[2:]))[0] + 1
    refr = int(0.25 * fs)
    keep: List[int] = []
    for i in cand:
        if keep and i - keep[-1] < refr:
            if e[i] > e[keep[-1]]:
                keep[-1] = i
            continue
        keep.append(int(i))
    # integration delays the energy peak: R is the largest |base| in [-150 ms, +50 ms]
    a, b = int(0.15 * fs), int(0.05 * fs)
    r = []
    for i in keep:
        lo, hi = max(0, i - a), min(len(base), i + b + 1)
        r.append(lo + int(np.argmax(np.abs(base[lo:hi]))))
    r = np.unique(np.array(r, dtype=int))
    # merge peaks that collapsed onto each other after relocation
    if len(r) > 1:
        r = r[np.concatenate([[True], np.diff(r) >= refr])]
    return r, base


# ------------------------------------------------------------------ v5 parameters
# Tuned on MIT-BIH DS1 only (de Chazal 2004 training half); DS2 and INCART are test data.
REF_K = 15                 # reference: median of pair means over 2*15+1 beats
PREM_MIN, PREM_MAX = 0.12, 0.20  # required prematurity: between 12 % and 20 % shorter than reference ...
PREM_SPREAD_K = 3.0        # ... scaled as k × local robust spread of RR / reference
ABRUPT = 0.90              # SVES: the premature interval is < 90 % of the interval before it (not a gradual speed-up)
PAUSE_REL_S = 1.00         # SVES: the interval after is >= the premature one ...
PAUSE_REF_S = 0.85         # ... and >= 0.85 × reference (v4 required > 1.05 × reference)
PAUSE_REF_V = 0.95         # premature VES: the interval after is >= 0.95 × reference
MORPH_CORR, MORPH_DW = 0.85, 0.04  # premature beat: VES if corr < 0.85 or QRS >= 40 ms wider (as v4)
STRICT_CORR, STRICT_DW = 0.70, 0.04  # any beat: VES if corr < 0.70 (best shift) and QRS >= 40 ms wider ...
STRICT_AMP = 1.5           # ... or corr < 0.70 and amplitude >= 1.5 × template
STRICT_CORR0, STRICT_CORR_S = 0.0, 0.80  # ... or inverted at the R peak (corr < 0), < 0.8 at best shift, wide
AF_WIN = 31                # irregular-rhythm window (intervals)
AF_THR = 0.10              # median normalised successive difference (min over lags 1-3)
AF_MIN_VALID = 0.2         # at least 20 % of the window must be usable intervals
AF_MIN_S, AF_MERGE_S = 30.0, 10.0
AF_PAD_S = 10.0
RUN_MIN = 3
LONG_RUN_BPM = 100.0       # runs of >= RUN_RATE_FROM beats must be faster than this (tachycardia)
RUN_RATE_FROM = 3


def _sliding(x: np.ndarray, k: int) -> np.ndarray:
    pad = np.pad(x, k, mode="edge")
    return np.lib.stride_tricks.sliding_window_view(pad, 2 * k + 1)


def _nanmedian_rows(w: np.ndarray, min_valid: int) -> np.ndarray:
    ok = np.sum(~np.isnan(w), axis=1) >= min_valid
    out = np.full(len(w), np.nan)
    if ok.any():
        out[ok] = np.nanmedian(w[ok], axis=1)
    return out


def irregularity(rr: np.ndarray, valid: np.ndarray, win: int = AF_WIN) -> np.ndarray:
    """Per interval: how irregular the rhythm around it is (≈0.02 sinus, ≈0.1–0.2 atrial fibrillation).

    Median of |rr[j+lag] − rr[j]| / local median RR over a window of `win` intervals, the minimum
    over lags 1–3: bigeminy and trigeminy repeat every 2 or 3 beats, so one lag stays small;
    in atrial fibrillation every lag is irregular. Isolated ectopic beats barely move a median.
    """
    n = len(rr)
    x = np.where(valid, rr, np.nan)
    k = win // 2
    mv = int(AF_MIN_VALID * win)
    med = _nanmedian_rows(_sliding(x, k), mv)
    best = np.full(n, np.inf)
    for lag in (1, 2, 3):
        d = np.full(n, np.nan)
        d[:-lag] = np.abs(x[lag:] - x[:-lag])
        s = _nanmedian_rows(_sliding(d, k), mv) / med
        best = np.fmin(best, np.where(np.isnan(s), np.inf, s))
    best[~np.isfinite(best)] = np.nan
    return best


def af_episodes(rt: np.ndarray, irr_beat: np.ndarray) -> List[Tuple[float, float]]:
    """Irregular-rhythm episodes (≥ AF_MIN_S, gaps < AF_MERGE_S merged) from per-beat irregularity."""
    flag = irr_beat > AF_THR
    eps: List[List[float]] = []
    for i in np.nonzero(flag)[0]:
        if eps and rt[i] - eps[-1][1] < AF_MERGE_S:
            eps[-1][1] = float(rt[i])
        else:
            eps.append([float(rt[i]), float(rt[i])])
    # the windowed median crosses the threshold only once half the window is irregular: widen the
    # episode by AF_PAD_S on both sides so that its first and last beats are not taken for SVES
    out: List[Tuple[float, float]] = []
    for a, b in eps:
        if b - a >= AF_MIN_S:
            a, b = max(float(rt[0]), a - AF_PAD_S), min(float(rt[-1]), b + AF_PAD_S)
            if out and a <= out[-1][1]:
                out[-1] = (out[-1][0], b)
            else:
                out.append((a, b))
    return out


def _windows(base: np.ndarray, r: np.ndarray, pre: int, post: int) -> Tuple[np.ndarray, np.ndarray]:
    inside = (r - pre >= 0) & (r + post + 1 <= len(base))
    w = np.zeros((len(r), pre + post + 1))
    idx = r[inside, None] + np.arange(-pre, post + 1)
    w[inside] = base[idx]
    w -= np.median(w, axis=1, keepdims=True)
    return w, inside


def _widths(w: np.ndarray, fs: float) -> np.ndarray:
    a = np.abs(w)
    above = a > 0.3 * a.max(axis=1, keepdims=True)
    first = np.argmax(above, axis=1)
    last = w.shape[1] - 1 - np.argmax(above[:, ::-1], axis=1)
    return np.where(above.any(axis=1), (last - first + 1) / fs, 0.0)


def morphology(base: np.ndarray, r: np.ndarray, fs: float, normal: np.ndarray,
               block: int = 16, reach: int = 40, shift_s: float = 0.04) -> Dict[str, np.ndarray]:
    """QRS correlation, width difference and amplitude ratio of every beat against the local
    dominant-beat template (median of up to 30 `normal` beats within ±`reach` beats).

    The correlation is the best over shifts of up to ±40 ms: the detector puts the fiducial point
    on the largest deflection, which for an RS-shaped complex can be the R or the S wave."""
    pre, post = int(QRS_PRE * fs), int(QRS_POST * fs)
    m = int(round(shift_s * fs))
    L = pre + post + 1
    wide, inside = _windows(base, r, pre + m, post + m)
    w = wide[:, m:m + L] - np.median(wide[:, m:m + L], axis=1, keepdims=True)
    n = len(r)
    corr = np.full(n, np.nan)
    corr0 = np.full(n, np.nan)
    dw = np.full(n, np.nan)
    amp = np.full(n, np.nan)
    use = normal & inside
    for s in range(0, n, block):
        e = min(n, s + block)
        cand = np.nonzero(use[max(0, s - reach):min(n, e + reach)])[0] + max(0, s - reach)
        if len(cand) < 5:
            continue
        cand = cand[:: max(1, len(cand) // 30)]
        tpl = np.median(w[cand], axis=0)
        tc = tpl - tpl.mean()
        tn = np.sqrt(np.sum(tc * tc))
        if tn == 0:
            continue
        best = np.full(e - s, -np.inf)
        for sh in range(-m, m + 1):
            seg = wide[s:e, m + sh:m + sh + L]
            seg = seg - seg.mean(axis=1, keepdims=True)
            sn = np.sqrt(np.sum(seg * seg, axis=1))
            with np.errstate(invalid="ignore", divide="ignore"):
                c = np.where(sn > 0, seg @ tc / (sn * tn), -np.inf)
            best = np.maximum(best, c)
            if sh == 0:
                corr0[s:e] = np.where(np.isfinite(c), c, np.nan)
        corr[s:e] = np.where(np.isfinite(best), best, np.nan)
        amp[s:e] = np.ptp(w[s:e], axis=1) / max(np.ptp(tpl), 1e-9)
        dw[s:e] = _widths(w[s:e], fs) - _widths(tpl[None, :], fs)[0]
    corr[~inside] = np.nan
    corr0[~inside] = np.nan
    return {"corr": corr0, "corr_shift": corr, "dw": dw, "amp": amp}


def classify_beats(t: np.ndarray, uv: np.ndarray, fs: float, duration: float,
                   no_contact: Optional[List[List[float]]] = None) -> Dict[str, Any]:
    """Premature beats, runs and irregular-rhythm episodes from the ECG (analysis v5)."""
    r, base = detect_r_peaks(t, uv, fs)
    out: Dict[str, Any] = {"method": "ecg", "beats": 0, "events": [], "details": [],
                           "af_episodes": [], "runs": []}
    if len(r) < 20:
        return out
    rt = t[r]
    amp_r = np.abs(base[r])
    typical = np.median(amp_r)
    # --- artefact flags per beat
    ok = (rt > EDGE_S) & (rt < duration - EDGE_S)
    ok &= amp_r < typical * 3.0  # huge spikes: movement, strap handling
    ok &= amp_r > typical * 0.25  # tiny: lost contact, detector picked noise
    for a0, b0 in no_contact or []:
        ok &= ~((rt >= a0 - 2) & (rt <= b0 + 2))
    # local noise: signal spread in ±1 s far above usual → reject the neighbourhood
    w1 = int(fs)
    spread_sig = np.array([np.ptp(base[max(0, i - w1):i + w1]) for i in r])
    ok &= spread_sig < np.median(spread_sig) * 3.0
    rr = np.diff(rt)
    good_pair = ok[1:] & ok[:-1] & (rr > 0.25) & (rr < 3.0)
    # data gaps (BLE drop-outs) break the sequence
    for g in np.nonzero(np.diff(t) > 1.0)[0]:
        good_pair &= ~((rt[:-1] <= t[g]) & (rt[1:] >= t[g + 1]))
    out["beats"] = int(ok.sum())
    out["r_peaks"] = rt[ok]  # numpy, for callers that need the beat sequence (not serialised)
    nb = len(r)
    n = len(rr)
    if n < 12:
        return out

    # --- per-beat RR context (beat b: interval before = rr[b-1], after = rr[b])
    pair = (rr[:-1] + rr[1:]) / 2  # pair[i] is centred on beat i+1
    ref_pair = np.median(_sliding(pair, REF_K), axis=1)
    ref = np.empty(nb)
    ref[1:-1] = ref_pair
    ref[0], ref[-1] = ref_pair[0], ref_pair[-1]
    prev = np.full(nb, np.nan)
    prev[1:] = rr
    nxt = np.full(nb, np.nan)
    nxt[:-1] = rr
    vprev = np.zeros(nb, bool)
    vprev[1:] = good_pair
    vnext = np.zeros(nb, bool)
    vnext[:-1] = good_pair
    dev = np.where(vprev, prev / ref, np.nan)
    prem0 = vprev & (dev < 0.8)  # first guess (v4 threshold), only to keep ectopic beats out of templates

    # --- morphology of every beat against nearby dominant beats (two passes)
    m = morphology(base, r, fs, ok & ~prem0)
    normal2 = ok & ~prem0 & ~(m["corr"] < MORPH_CORR)
    m = morphology(base, r, fs, normal2)
    corr, corr_s, dwid, ampr = m["corr"], m["corr_shift"], m["dw"], m["amp"]
    has_m = ~np.isnan(corr)
    ves_morph = has_m & ((corr < MORPH_CORR) | (dwid >= MORPH_DW))
    # strict: clearly different even at the best alignment (±40 ms), and wide or large; or opposite
    # polarity at the R peak and wide
    ves_strict = has_m & (((corr_s < STRICT_CORR) & ((dwid >= STRICT_DW) | (ampr >= STRICT_AMP)))
                          | ((corr < STRICT_CORR0) & (corr_s < STRICT_CORR_S) & (dwid >= STRICT_DW)))
    # a beat that stands out must stand out from its neighbours too: if the beats around it do not
    # fit the template either, the template (or the signal) is wrong there, not the beat
    fits = has_m & (corr_s >= MORPH_CORR)
    nb_fit = np.zeros(nb, bool)
    nb_fit[1:-1] = fits[:-2] & fits[2:]
    ves_alone = ves_strict & nb_fit

    # (b) prematurity threshold from the local spread of RR / reference (robust: MAD), estimated from
    # beats of normal shape that do not follow a beat of abnormal shape (frequent VES would inflate it)
    after_v = np.zeros(nb, bool)
    after_v[1:] = ves_morph[:-1]
    dv = np.where(ves_morph | after_v, np.nan, dev)
    dw_ = _sliding(dv, REF_K)
    with np.errstate(all="ignore"):
        cen = _nanmedian_rows(dw_, 8)
        mad = _nanmedian_rows(np.abs(dw_ - cen[:, None]), 8)
    spread = 1.4826 * np.where(np.isnan(mad), 0.0, mad)
    need = np.clip(PREM_SPREAD_K * spread, PREM_MIN, PREM_MAX)
    thr = 1.0 - need
    # reference from the beats before (not centred): a long run must not drag its own reference down
    ref_pre = ref.copy()
    if len(pair) > 2 * REF_K:
        med_before = np.median(np.lib.stride_tricks.sliding_window_view(pair, 2 * REF_K + 1), axis=1)
        j = np.arange(nb) - 3 - 2 * REF_K  # pairs ending before the interval leading to beat b
        have = (j >= 0) & (j < len(med_before))
        ref_pre[have] = med_before[j[have]]
    refx = np.fmax(ref, ref_pre)
    prem = vprev & (prev < thr * refx)

    # --- (a) irregular rhythm / atrial fibrillation episodes, from intervals between beats of
    # normal shape only (ventricular bigeminy or frequent VES are regular-irregular, not AF)
    nshape = ~(ves_strict | (prem & ves_morph))
    irr = irregularity(rr, good_pair & nshape[1:] & nshape[:-1])
    irr_beat = np.full(nb, np.nan)
    irr_beat[1:] = irr
    eps = af_episodes(rt, np.where(ok, irr_beat, np.nan))
    in_af = np.zeros(nb, bool)
    for a0, b0 in eps:
        in_af |= (rt >= a0) & (rt <= b0)

    # --- premature sequences: s..e consecutive beats shorter than thr[s] × ref[s] (ref fixed at onset,
    # so a long run does not drag its own reference down)
    accepted: Dict[int, Dict[str, Any]] = {}
    runs: List[Dict[str, Any]] = []
    done = np.zeros(nb, bool)
    for s in np.nonzero(prem)[0]:
        if done[s] or s < 1:
            continue
        R, T = refx[s], thr[s]
        e = s
        while e + 1 < nb and vprev[e + 1] and prev[e + 1] < T * R:
            e += 1
        done[s:e + 1] = True
        if not vnext[e] or not ok[s:e + 1].all():
            continue
        post, last = nxt[e], prev[e]
        abrupt = s >= 2 and vprev[s - 1] and prev[s] < ABRUPT * prev[s - 1]
        sves_pause = post >= PAUSE_REL_S * last and post >= PAUSE_REF_S * R
        ves_pause = post >= PAUSE_REF_V * R and post > last
        seq = list(range(s, e + 1))
        kinds = []
        for b in seq:
            if not has_m[b]:
                kinds.append("premature" if ves_pause and not in_af[b] else None)
            elif ves_morph[b]:
                kinds.append("ves" if (ves_pause or sves_pause) else None)
            else:
                kinds.append("sves" if (sves_pause and abrupt and not in_af[b]) else None)
        n_v, n_s = kinds.count("ves"), kinds.count("sves")
        if n_v and n_s > 2 * n_v:
            # mostly supraventricular run: a mildly different beat in it is aberrant conduction
            kinds = ["ves" if k == "ves" and ves_strict[b] else k for b, k in zip(seq, kinds)]
        elif n_v and n_s:
            # VES next to a normal-shaped short beat: the normal-shaped one is almost always a sinus
            # beat (speed-up before, or the return after), not a second, supraventricular ectopic
            kinds = [k if k == "ves" else None for k in kinds]
        if None in kinds:
            # broken sequence: keep only beats that are VES by morphology (they stand on their own)
            kinds = ["ves" if has_m[b] and ves_strict[b] else None for b in seq]
        comp = (prev[s] + post) / R
        groups: List[List[int]] = []
        for b, k in zip(seq, kinds):
            if k is None:
                continue
            if groups and groups[-1][-1] == b - 1:
                groups[-1].append(b)
            else:
                groups.append([b])
        for g in groups:
            kk = [kinds[b - s] for b in g]
            rate = 60.0 / float(np.mean(prev[g[0]:g[-1] + 1]))
            if len(g) >= RUN_RATE_FROM and rate <= LONG_RUN_BPM:
                # three or more in a row but not a tachycardia: more likely a change of the underlying
                # rate than ectopic beats; keep only beats whose shape alone says VES
                for b in g:
                    if ves_strict[b]:
                        accepted[b] = {"kind": "ves", "premature": True, "ref": R, "comp": False, "seq": 1}
                continue
            for b, k in zip(g, kk):
                accepted[b] = {"kind": k, "premature": True, "ref": R, "seq": len(g),
                               "comp": len(g) == 1 and g[0] == s == e and 1.75 < comp < 2.25}
            if len(g) >= RUN_MIN:
                ks = set(kk)
                runs.append({"start": round(float(rt[g[0]]), 3), "end": round(float(rt[g[-1]]), 3), "beats": len(g),
                             "kind": ks.pop() if len(ks) == 1 else "mixed", "rate_bpm": round(rate),
                             "in_af": bool(in_af[g[0]:g[-1] + 1].any())})

    # --- (e) VES by morphology alone: any clean beat with a clearly different, wide or large QRS
    for b in np.nonzero(ves_alone & ok & vprev & vnext)[0]:
        if b not in accepted:
            accepted[b] = {"kind": "ves", "premature": False, "ref": ref[b], "comp": False, "seq": 1}

    events, details = [], []
    for b in sorted(accepted):
        a = accepted[b]
        events.append(round(float(rt[b]), 3))
        details.append({"t": round(float(rt[b]), 3), "kind": a["kind"], "compensatory": bool(a["comp"]),
                        "couplet": a["seq"] == 2, "premature": a["premature"],
                        "run": a["seq"] >= RUN_MIN, "in_af": bool(in_af[b]),
                        "rr_ms": round(float(prev[b]) * 1000), "pause_ms": round(float(nxt[b]) * 1000),
                        "ref_ms": round(float(a["ref"]) * 1000),
                        "corr": None if not has_m[b] else round(float(corr[b]), 3),
                        "width_diff_ms": None if not has_m[b] else round(float(dwid[b]) * 1000)})
    out["events"] = events
    out["details"] = details
    out["runs"] = runs
    hr_af = []
    for a0, b0 in eps:
        mm = (rt[1:] >= a0) & (rt[1:] <= b0) & good_pair
        hr_af.append(round(60.0 / float(np.median(rr[mm]))) if mm.any() else None)
    out["af_episodes"] = [{"start": round(a0, 2), "end": round(b0, 2), "duration_s": round(b0 - a0, 1),
                           "hr_median": h} for (a0, b0), h in zip(eps, hr_af)]
    return out
