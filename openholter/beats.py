"""Beat detection and premature-beat classification from the ECG itself (analysis v6).

The strap's own RR intervals (BLE Heart Rate service) are convenient but opaque: while
the strap is being put on or taken off, or when its detector slips, they produce
short-long pairs that look exactly like ectopic beats. Here R peaks are found in the
130 Hz ECG directly:

1. Pan–Tompkins style detection: band-pass (difference of moving averages, ~5–15 Hz),
   derivative, squaring, 150 ms moving-window integration. The threshold follows the last
   beats (v6), with search-back over long gaps and T-wave rejection; the R peak is the
   largest |baseline-removed ECG| within ±100 ms of the integrated peak.
2. Artefact rejection: beats in segments whose amplitude is far above the recording's
   typical QRS amplitude, beats across data gaps, and the first/last minute (strap being
   put on / taken off) are excluded.
3. Morphology of every beat (v5): QRS window −80…+120 ms against the median of nearby
   normal beats; correlation at the R peak and the best correlation over ±40 ms shifts,
   QRS width difference and amplitude ratio. At 130 Hz one sample is 7.7 ms.
4. Irregular rhythm (v5): per beat, the median normalised RR difference over 31 intervals
   (minimum over lags 1–3, so bigeminy/trigeminy stay "regular"; intervals next to clearly
   ventricular beats left out). Episodes ≥ 30 s above 0.05 with no visible P wave (v6: the
   −240…−60 ms segments of nearby beats do not average into a repeating wave) are reported
   as irregular rhythm (fits atrial fibrillation) and no SVES are labelled inside them.
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


# Detector parameters (v6). Tuned on MIT-BIH DS1 only.
DET_REFR = 0.20       # s: two QRS cannot be closer than this
DET_K = 0.40          # threshold = noise level + k × (signal level − noise level)
DET_HIST = 8          # signal level: median height of the last 8 accepted peaks
DET_SEARCH = 1.5      # search back when the gap exceeds 1.5 × median of the last 8 RR
DET_BACK_K = 0.5      # in search-back the threshold is this × the normal one
DET_T_S, DET_T_RATIO = 0.42, 0.5  # within 420 ms a peak under 0.5 × the previous one is a T wave
DET_BACK_S = 5.0      # search back at most this far: RR intervals over 3 s are not analysed anyway
DET_FLOOR = 0.12      # never below 12 % of the recording's typical peak (lost contact, noise)
DET_LOC_PRE, DET_LOC_POST = 0.10, 0.10  # R is the largest |baseline-removed ECG| in this window


def _pick_peaks(h: np.ndarray, cand: np.ndarray, fs: float) -> List[int]:
    """Adaptive-threshold peak picking with T-wave rejection and search-back (after Pan–Tompkins).

    Everything is local to the last few beats: one very tall beat cannot hide its neighbours,
    which a threshold fixed per block did. `h` are peak heights, `cand` their sample indices.
    """
    n = len(cand)
    typical = float(np.median(h[h >= np.percentile(h, 50)]))
    floor = DET_FLOOR * typical
    spk: List[float] = [typical]
    npk = 0.1 * typical
    rrs: List[int] = []
    keep: List[int] = []  # indices into cand
    last_rej: List[int] = []  # rejected since the last accepted peak
    t_gap, refr, back_max = int(DET_T_S * fs), int(DET_REFR * fs), int(DET_BACK_S * fs)

    def level() -> float:
        return max(floor, npk + DET_K * (float(np.median(spk[-DET_HIST:])) - npk))

    def accept(j: int) -> None:
        if keep:
            rrs.append(int(cand[j] - cand[keep[-1]]))
        keep.append(j)
        spk.append(float(h[j]))

    for j in range(n):
        if keep and cand[j] - cand[keep[-1]] < refr:
            if h[j] > h[keep[-1]]:  # same complex, higher peak
                spk[-1] = float(h[j])
                keep[-1] = j
            continue
        # a stretch without beats (strap off) must not make the list grow: keep only the last few seconds
        if last_rej and cand[j] - cand[last_rej[0]] > back_max:
            last_rej = [q for q in last_rej if cand[j] - cand[q] <= back_max]
        # search back: the gap has grown too long, take the highest rejected peak in it
        if keep and rrs and last_rej:
            med = float(np.median(rrs[-DET_HIST:]))
            if cand[j] - cand[keep[-1]] > DET_SEARCH * med:
                # not the T wave of the last beat: inside the T window a peak must be tall to count
                ok_rej = [q for q in last_rej if cand[q] - cand[keep[-1]] >= refr and cand[j] - cand[q] >= refr
                          and (cand[q] - cand[keep[-1]] >= t_gap or h[q] >= DET_T_RATIO * h[keep[-1]])]
                if ok_rej:
                    q = max(ok_rej, key=lambda v: h[v])
                    if h[q] >= max(floor, DET_BACK_K * level()):
                        accept(q)
                        last_rej = [v for v in last_rej if v > q]
        thr = level()
        if h[j] >= thr:
            if keep and cand[j] - cand[keep[-1]] < t_gap and h[j] < DET_T_RATIO * h[keep[-1]]:
                npk = 0.875 * npk + 0.125 * float(h[j])  # T wave
                last_rej.append(j)
                continue
            accept(j)
            last_rej = []
        else:
            npk = 0.875 * npk + 0.125 * float(h[j])
            last_rej.append(j)
    return keep


def detect_r_peaks(t: np.ndarray, uv: np.ndarray, fs: float) -> Tuple[np.ndarray, np.ndarray]:
    """Indices of R peaks and the baseline-removed signal they were located on."""
    if len(uv) < fs * 5:
        return np.zeros(0, dtype=int), uv.astype(np.float64)
    x = uv.astype(np.float64)
    base = x - _movavg(x, fs * 1.0)  # baseline wander removed, for locating R
    band = _movavg(x - _movavg(x, round(fs / 5)), 3)  # crude 5–15 Hz band-pass
    d = np.diff(band, prepend=band[0])
    # square root of the integrated energy: same units as the signal, so a tall beat dominates less
    e = np.sqrt(_movavg(d * d, round(0.15 * fs)))
    cand = np.nonzero((e[1:-1] >= e[:-2]) & (e[1:-1] > e[2:]))[0] + 1
    if len(cand) < 5:
        return np.zeros(0, dtype=int), base
    keep = _pick_peaks(e[cand], cand, fs)
    a, b = int(DET_LOC_PRE * fs), int(DET_LOC_POST * fs)
    r = []
    for i in cand[keep]:
        lo, hi = max(0, i - a), min(len(base), i + b + 1)
        r.append(lo + int(np.argmax(np.abs(base[lo:hi]))))
    r = np.unique(np.array(r, dtype=int))
    # merge peaks that collapsed onto each other after relocation
    if len(r) > 1:
        refr = int(DET_REFR * fs)
        r = r[np.concatenate([[True], np.diff(r) >= refr])]
    return r, base


# ------------------------------------------------------------------ classification parameters
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
AF_THR = 0.05              # median normalised successive difference (min over lags 1-3)
AF_MIN_VALID = 0.2         # at least 20 % of the window must be usable intervals
AF_MIN_S, AF_MERGE_S = 30.0, 10.0
AF_PAD_S = 10.0
P_PRE, P_POST = 0.24, 0.06  # window searched for the P wave, before the R peak (s)
P_MIN_BEATS = 10
P_COH, P_AMP = 0.75, 0.05   # P wave present: coherence >= 0.75 and height >= 5 % of the QRS
P_SMOOTH = 15               # beats either side, median
RUN_MIN = 3
MORPH_REACH = 40           # template from normal beats within this many beats
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
               block: int = 16, reach: int = 0, shift_s: float = 0.04) -> Dict[str, np.ndarray]:
    """QRS correlation, width difference and amplitude ratio of every beat against the local
    dominant-beat template (median of up to 30 `normal` beats within ±`reach` beats).

    The correlation is the best over shifts of up to ±40 ms: the detector puts the fiducial point
    on the largest deflection, which for an RS-shaped complex can be the R or the S wave."""
    reach = reach or MORPH_REACH
    pre, post = int(QRS_PRE * fs), int(QRS_POST * fs)
    m = int(round(shift_s * fs))
    L = pre + post + 1
    wide, inside = _windows(base, r, pre + m, post + m)
    w = wide[:, m:m + L] - np.median(wide[:, m:m + L], axis=1, keepdims=True)
    n = len(r)
    corr = np.full(n, np.nan)
    corr0 = np.full(n, np.nan)
    shift = np.zeros(n, dtype=int)
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
            shift[s:e][c > best] = sh
            best = np.maximum(best, c)
            if sh == 0:
                corr0[s:e] = np.where(np.isfinite(c), c, np.nan)
        corr[s:e] = np.where(np.isfinite(best), best, np.nan)
        amp[s:e] = np.ptp(w[s:e], axis=1) / max(np.ptp(tpl), 1e-9)
        dw[s:e] = _widths(w[s:e], fs) - _widths(tpl[None, :], fs)[0]
    corr[~inside] = np.nan
    corr0[~inside] = np.nan
    return {"corr": corr0, "corr_shift": corr, "dw": dw, "amp": amp, "shift": shift}


def p_wave_presence(base: np.ndarray, r: np.ndarray, fs: float, good: np.ndarray,
                    reach: int = 20, block: int = 8) -> Tuple[np.ndarray, np.ndarray]:
    """Per beat: is there a repeating wave before the QRS? Returns (coherence, relative amplitude).

    The −240…−60 ms segments of nearby sinus-like beats are averaged in two halves. A P wave at a
    fixed distance from the QRS makes the two averages alike (coherence near 1), and their shape
    has height; in atrial fibrillation there is nothing locked to the QRS, so they do not match.
    """
    n = len(r)
    a, b = int(P_PRE * fs), int(P_POST * fs)
    L = a - b
    inside = (r - a >= 0) & (r - b < len(base))
    w = np.zeros((n, L))
    w[inside] = base[r[inside, None] + np.arange(-a, -b)]
    ramp = np.linspace(0.0, 1.0, L)
    e0, e1 = w[:, :3].mean(axis=1, keepdims=True), w[:, -3:].mean(axis=1, keepdims=True)
    w = w - (e0 + (e1 - e0) * ramp)  # a straight line between the ends of the segment is not a wave
    coh, amp = np.full(n, np.nan), np.full(n, np.nan)
    use = good & inside
    if not use.any():
        return coh, amp
    qrs = float(np.median(np.abs(base[r[use]])))
    for s in range(0, n, block):
        e = min(n, s + block)
        c = np.nonzero(use[max(0, s - reach):min(n, e + reach)])[0] + max(0, s - reach)
        if len(c) < P_MIN_BEATS:
            continue
        odd, even = w[c[::2]].mean(axis=0), w[c[1::2]].mean(axis=0)
        if odd.std() > 0 and even.std() > 0:
            coh[s:e] = np.corrcoef(odd, even)[0, 1]
        amp[s:e] = np.ptp(np.median(w[c], axis=0)) / max(qrs, 1e-9)
    return coh, amp


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
    # ... and only when no P wave is seen: frequent atrial extra beats are irregular too, but the
    # sinus beats between them still have a P wave
    sinus_like = ok & nshape & ~ves_morph & ~prem0 & (np.nan_to_num(prev) >= 0.45)
    coh, pamp = p_wave_presence(base, r, fs, sinus_like)
    coh_s = _nanmedian_rows(_sliding(coh, P_SMOOTH), 5)
    amp_s = _nanmedian_rows(_sliding(pamp, P_SMOOTH), 5)
    p_seen = (coh_s >= P_COH) & (amp_s >= P_AMP)
    eps = af_episodes(rt, np.where(ok & ~p_seen, irr_beat, np.nan))
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
