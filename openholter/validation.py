"""Validation of the ECG beat analysis against the MIT-BIH Arrhythmia and INCART databases.

The databases (PhysioNet, ODC-BY 1.0) are not bundled. Download them, check them against
PhysioNet's SHA256SUMS.txt and run:

    python -m openholter validate --mitdb /path/to/mit-bih-arrhythmia-database-1.0.0
    python -m openholter validate --incartdb /path/to/incart/files

MIT-BIH results are also given separately for the de Chazal et al. (2004) halves DS1 and
DS2. Analysis v5 was tuned on DS1 only; DS2 and INCART are held-out test data.

INCART (St Petersburg INCART 12-lead Arrhythmia Database): 75 records of 30 min at 257 Hz,
format 16; lead II is used, resampled 257 → 130 Hz. The same EC57 rules apply (there are
no paced records).

What is done, so that the numbers can be checked and reproduced:

* Readers for the WFDB header (.hea), signal format 212 (.dat) and MIT annotation
  format (.atr) are written here (~60 lines), so no third-party package sits between
  the data and the result.
* Signal: the first channel (MLII in 44 of the 48 records; V5 in 102 and 104), converted
  to µV with the header's gain and baseline, then resampled 360 → 130 Hz (the Polar H10
  rate) by FFT. The algorithm is run exactly as on a real recording; nothing is tuned
  per record.
* Reference: the cardiologists' beat labels, grouped into the ANSI/AAMI EC57 classes
  N (N, L, R, e, j), S (A, a, J, S), V (V, E), F (F) and Q (/, f, Q).
* As EC57 prescribes: the four paced records (102, 104, 107, 217) are excluded from the
  class statistics, beat-by-beat comparison starts 5 minutes into each record, a
  detection matches a reference beat within 150 ms, and ventricular flutter episodes
  are excluded from QRS detection statistics. Additionally the last 60 s are excluded,
  because the app always ignores the last minute (strap being taken off).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from .beats import classify_beats, detect_r_peaks

FS_OUT = 130.0
TOL = 0.150
START_S = 300.0
END_S = 60.0
PACED = {"102", "104", "107", "217"}
# de Chazal P, O'Dwyer M, Reilly RB (2004): training (DS1) and test (DS2) halves, paced records excluded
DS1 = ["101", "106", "108", "109", "112", "114", "115", "116", "118", "119", "122", "124", "201", "203",
       "205", "207", "208", "209", "215", "220", "223", "230"]
DS2 = ["100", "103", "105", "111", "113", "117", "121", "123", "200", "202", "210", "212", "213", "214",
       "219", "221", "222", "228", "231", "232", "233", "234"]

# MIT annotation codes → mnemonic (WFDB ecgcodes.h)
CODES = {1: "N", 2: "L", 3: "R", 4: "a", 5: "V", 6: "F", 7: "J", 8: "A", 9: "S", 10: "E",
         11: "j", 12: "/", 13: "Q", 14: "~", 16: "|", 18: "s", 19: "T", 20: "*", 21: "D",
         22: '"', 23: "=", 24: "p", 25: "B", 26: "^", 27: "t", 28: "+", 29: "u", 30: "?",
         31: "!", 32: "[", 33: "]", 34: "e", 35: "n", 36: "@", 37: "x", 38: "f", 39: "(",
         40: ")", 41: "r"}
AAMI = {**{c: "N" for c in "NLRej"}, **{c: "S" for c in "AaJSn"}, **{c: "V" for c in "VEr"},
        "F": "F", **{c: "Q" for c in "/fQ"}}
CLASSES = ["N", "S", "V", "F", "Q"]


# ---------------------------------------------------------------- WFDB readers
def read_header(path: Path) -> Dict[str, Any]:
    lines = [ln for ln in path.read_text().splitlines() if ln and not ln.startswith("#")]
    name, nsig, fs, nsamp = lines[0].split()[:4]
    sigs = []
    for ln in lines[1:1 + int(nsig)]:
        f = ln.split()
        gain = float(f[2].split("(")[0].split("/")[0])
        baseline = int(f[2].split("(")[1].split(")")[0]) if "(" in f[2] else int(f[4])
        sigs.append({"file": f[0], "fmt": f[1], "gain": gain, "baseline": baseline, "desc": " ".join(f[8:])})
    return {"name": name, "nsig": int(nsig), "fs": float(fs), "nsamp": int(nsamp), "signals": sigs}


def read_212(path: Path, nsig: int) -> np.ndarray:
    """Format 212: two 12-bit two's-complement samples packed in three bytes, channels interleaved."""
    b = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    b = b[: len(b) // 3 * 3].reshape(-1, 3).astype(np.int32)
    s0 = b[:, 0] | ((b[:, 1] & 0x0F) << 8)
    s1 = b[:, 2] | ((b[:, 1] & 0xF0) << 4)
    s = np.empty(len(b) * 2, dtype=np.int32)
    s[0::2], s[1::2] = s0, s1
    s[s >= 2048] -= 4096
    return s[: len(s) // nsig * nsig].reshape(-1, nsig)


def read_16(path: Path, nsig: int) -> np.ndarray:
    """Format 16: 16-bit little-endian two's-complement samples, channels interleaved."""
    s = np.frombuffer(path.read_bytes(), dtype="<i2").astype(np.int32)
    return s[: len(s) // nsig * nsig].reshape(-1, nsig)


def read_signal(db: Path, h: Dict[str, Any], lead: str = "") -> Tuple[np.ndarray, Dict[str, Any]]:
    """One channel in µV: the named lead, or the first channel when `lead` is empty."""
    k = next((i for i, sg in enumerate(h["signals"]) if sg["desc"] == lead), 0) if lead else 0
    sig = h["signals"][k]
    reader = {"212": read_212, "16": read_16}[sig["fmt"].split("+")[0].split(":")[0]]
    raw = reader(db / sig["file"], h["nsig"])[:, k].astype(np.float64)
    return (raw - sig["baseline"]) / sig["gain"] * 1000.0, sig


def read_atr(path: Path) -> Tuple[np.ndarray, List[str], List[str]]:
    """MIT annotation format: 16-bit words, code in the top 6 bits, time increment in the low 10."""
    d = path.read_bytes()
    t, i = 0, 0
    samples: List[int] = []
    codes: List[str] = []
    aux: List[str] = []
    while i + 1 < len(d):
        w = d[i] | (d[i + 1] << 8)
        i += 2
        a, n = w >> 10, w & 0x3FF
        if a == 0 and n == 0:
            break
        if a == 59:  # SKIP: 32-bit interval, high 16 bits first
            hi = d[i] | (d[i + 1] << 8)
            lo = d[i + 2] | (d[i + 3] << 8)
            skip = (hi << 16) | lo
            if skip >= 1 << 31:
                skip -= 1 << 32
            t += skip
            i += 4
        elif a == 63:  # AUX string belongs to the previous annotation
            txt = d[i:i + n].split(b"\0")[0].decode("latin-1")
            if aux:
                aux[-1] = txt
            i += n + (n & 1)
        elif a in (60, 61, 62):  # NUM, SUB, CHN: not needed here
            pass
        else:
            t += n
            samples.append(t)
            codes.append(CODES.get(a, "?"))
            aux.append("")
    return np.array(samples, dtype=np.int64), codes, aux


def resample(x: np.ndarray, fs_in: float, fs_out: float) -> np.ndarray:
    n = len(x)
    m = int(round(n * fs_out / fs_in))
    spec = np.fft.rfft(x - x.mean())
    return np.fft.irfft(spec[: m // 2 + 1], m) * (m / n) + x.mean()


# ---------------------------------------------------------------- matching
def match(ref: np.ndarray, det: np.ndarray, tol: float = TOL) -> np.ndarray:
    """For each reference time the index of its matched detection, or -1 (one-to-one, nearest first)."""
    out = np.full(len(ref), -1, dtype=int)
    if not len(det):
        return out
    j = np.clip(np.searchsorted(det, ref), 1, len(det) - 1)
    nearest = np.where(np.abs(det[j - 1] - ref) <= np.abs(det[j] - ref), j - 1, j)
    dist = np.abs(det[nearest] - ref)
    used = np.zeros(len(det), bool)
    for k in np.argsort(dist):
        if dist[k] <= tol and not used[nearest[k]]:
            out[k] = nearest[k]
            used[nearest[k]] = True
    return out


def _excluded(times: np.ndarray, spans: List[Tuple[float, float]]) -> np.ndarray:
    m = np.zeros(len(times), bool)
    for a, b in spans:
        m |= (times >= a) & (times <= b)
    return m


# ---------------------------------------------------------------- one record
def _rhythm_spans(at: np.ndarray, codes: List[str], aux: List[str], duration: float,
                  prefixes: Tuple[str, ...]) -> List[Tuple[float, float]]:
    """Spans of rhythm annotations ('+' with aux like "(AFIB") whose label starts with a prefix."""
    spans: List[Tuple[float, float]] = []
    start = None
    for ti, c, a in zip(at, codes, aux):
        if c != "+":
            continue
        if start is not None:
            spans.append((start, ti))
            start = None
        if a.startswith(prefixes):
            start = ti
    if start is not None:
        spans.append((start, duration))
    return spans


def _ref_runs(bt: np.ndarray, bcls: np.ndarray) -> List[Tuple[float, float, str]]:
    """Reference runs: ≥ 3 consecutive S or V beats (class 'S', 'V' or 'mixed')."""
    runs: List[Tuple[float, float, str]] = []
    i = 0
    while i < len(bcls):
        if bcls[i] in ("S", "V"):
            j = i
            while j + 1 < len(bcls) and bcls[j + 1] in ("S", "V"):
                j += 1
            if j - i + 1 >= 3:
                ks = set(bcls[i:j + 1])
                runs.append((float(bt[i]), float(bt[j]), ks.pop() if len(ks) == 1 else "mixed"))
            i = j + 1
        else:
            i += 1
    return runs


def _overlaps(a: Tuple[float, float], spans: List[Tuple[float, float]], tol: float = TOL) -> bool:
    return any(a[0] <= y + tol and x - tol <= a[1] for x, y in spans)


def run_record(db: Path, rec: str, lead: str = "", paced: Any = PACED) -> Dict[str, Any]:
    h = read_header(db / f"{rec}.hea")
    uv, sig = read_signal(db, h, lead)
    x = resample(uv, h["fs"], FS_OUT)
    t = np.arange(len(x)) / FS_OUT
    duration = len(x) / FS_OUT

    samp, codes, aux = read_atr(db / f"{rec}.atr")
    at = samp / h["fs"]
    # ventricular flutter/fibrillation episodes: [ … ] or rhythm (VFL … next rhythm change
    vf: List[Tuple[float, float]] = []
    start = None
    for ti, c, a in zip(at, codes, aux):
        if c == "[" or (c == "+" and a.startswith("(VF")):
            start = ti if start is None else start
        elif start is not None and (c == "]" or c == "+"):
            vf.append((start, ti))
            start = None
    if start is not None:
        vf.append((start, duration))

    beat = np.array([c in AAMI for c in codes])
    bt = at[beat]
    bcls = np.array([AAMI[c] for c, b in zip(codes, beat) if b])
    win = (bt >= START_S) & (bt <= duration - END_S)

    t0 = time.perf_counter()
    r, _ = detect_r_peaks(t, x, FS_OUT)
    res = classify_beats(t, x, FS_OUT, duration, None)
    elapsed = time.perf_counter() - t0
    rt = t[r]

    # --- QRS detection (all detections, before artefact rejection), VF excluded
    dwin = (rt >= START_S) & (rt <= duration - END_S) & ~_excluded(rt, vf)
    qwin = win & ~_excluded(bt, vf)
    m = match(bt[qwin], rt[dwin])
    qrs = {"ref": int(qwin.sum()), "tp": int((m >= 0).sum()),
           "fn": int((m < 0).sum()), "fp": int(dwin.sum() - (m >= 0).sum())}
    # beats kept after artefact rejection (the ones the app actually analyses)
    kept = np.asarray(res.get("r_peaks", np.zeros(0)))
    mk = match(bt[qwin], kept[(kept >= START_S) & (kept <= duration - END_S) & ~_excluded(kept, vf)])
    qrs["usable"] = int((mk >= 0).sum())

    # --- premature beats: events (with label) vs reference classes
    det = res["details"]
    et = np.array([d["t"] for d in det], dtype=float)
    ek = np.array([d["kind"] for d in det])
    eprem = np.array([d.get("premature", True) for d in det], dtype=bool)
    ewin = (et >= START_S) & (et <= duration - END_S)
    et, ek, eprem = et[ewin], ek[ewin], eprem[ewin]
    ref_t, ref_c = bt[win], bcls[win]
    mm = match(ref_t, et)  # per reference beat → event index
    ev_ref = np.full(len(et), "-", dtype=object)  # per event → matched reference class ("-" = no beat)
    for i, j in enumerate(mm):
        if j >= 0:
            ev_ref[j] = ref_c[i]
    labels = ["ves", "sves", "premature", "none"]
    conf = {c: {l: 0 for l in labels} for c in CLASSES}
    for i, c in enumerate(ref_c):
        conf[c][ek[mm[i]] if mm[i] >= 0 else "none"] += 1
    extra = {l: int(((ev_ref == "-") & (ek == l)).sum()) for l in labels[:3]}
    # VES found by morphology alone (not premature): how many, and what they really were
    morph_only = {c: int(((ev_ref == c) & (ek == "ves") & ~eprem).sum()) for c in CLASSES + ["-"]}
    # subgroups by the reference rhythm around each ectopic beat (from the annotations alone):
    # isolated = both neighbours class N; typical = isolated, premature (< 80 % of the local
    # median RR) and followed by a pause (> 105 %), i.e. the pattern the v4 method looks for
    rr = np.diff(bt)
    med = np.array([np.median(rr[max(0, i - 15):i + 15]) for i in range(len(rr))])
    af_ref = _rhythm_spans(at, codes, aux, duration, ("(AFIB", "(AFL"))
    af = bool(af_ref)
    sub = {c: {g: [0, 0] for g in ("isolated", "typical")} for c in ("V", "S")}
    idx = np.nonzero(win)[0]
    pos = {int(i): k for k, i in enumerate(idx)}
    for i in idx:
        c = bcls[i]
        if c not in sub or i == 0 or i >= len(bt) - 1:
            continue
        if bcls[i - 1] != "N" or bcls[i + 1] != "N":
            continue
        hit = int(mm[pos[int(i)]] >= 0)
        sub[c]["isolated"][0] += 1
        sub[c]["isolated"][1] += hit
        if rr[i - 1] < 0.8 * med[i - 1] and rr[i] > 1.05 * med[i]:
            sub[c]["typical"][0] += 1
            sub[c]["typical"][1] += hit

    # --- irregular rhythm (AF) episodes vs the reference rhythm annotations, beat by beat
    det_af = [(e["start"], e["end"]) for e in res.get("af_episodes", [])]
    in_ref = _excluded(ref_t, af_ref)
    in_det = _excluded(ref_t, det_af)
    afs = {"ref_beats": int(in_ref.sum()), "det_beats": int(in_det.sum()), "both": int((in_ref & in_det).sum()),
           "episodes": len(det_af), "ref_episodes": len(af_ref),
           "det_s": round(sum(min(b, duration - END_S) - max(a, START_S) for a, b in det_af
                              if b > START_S and a < duration - END_S), 1)}

    # --- runs of ≥ 3 consecutive ectopic beats
    rr_runs = [x for x in _ref_runs(bt, bcls) if x[0] >= START_S and x[1] <= duration - END_S]
    dr = [(x["start"], x["end"]) for x in res.get("runs", []) if x["start"] >= START_S and x["end"] <= duration - END_S]
    runs = {"ref": len(rr_runs), "ref_S": sum(1 for x in rr_runs if x[2] == "S"),
            "ref_V": sum(1 for x in rr_runs if x[2] == "V"),
            "ref_found": sum(1 for x in rr_runs if _overlaps(x[:2], dr)),
            "ref_S_found": sum(1 for x in rr_runs if x[2] == "S" and _overlaps(x[:2], dr)),
            "ref_V_found": sum(1 for x in rr_runs if x[2] == "V" and _overlaps(x[:2], dr)),
            "det": len(dr), "det_true": sum(1 for x in dr if _overlaps(x, [y[:2] for y in rr_runs]))}
    return {"record": rec, "lead": sig["desc"], "paced": rec in paced, "duration_s": round(duration, 1),
            "elapsed_s": round(elapsed, 2), "qrs": qrs, "confusion": conf, "unmatched_events": extra,
            "morphology_only_ves": morph_only, "subgroups": sub, "atrial_fibrillation_or_flutter": af,
            "af": afs, "runs": runs, "vf_excluded_s": round(sum(b - a for a, b in vf), 1)}


# ---------------------------------------------------------------- summary
def _ratio(a: int, b: int) -> Any:
    return None if b == 0 else round(100.0 * a / b, 2)


def summarize_results(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    nonpaced = [r for r in rows if not r["paced"]]
    q = {k: sum(r["qrs"][k] for r in rows) for k in ("ref", "tp", "fn", "fp", "usable")}
    conf = {c: {l: sum(r["confusion"][c][l] for r in nonpaced) for l in ("ves", "sves", "premature", "none")}
            for c in CLASSES}
    extra = {l: sum(r["unmatched_events"][l] for r in nonpaced) for l in ("ves", "sves", "premature")}

    def flagged(c: str) -> int:
        return conf[c]["ves"] + conf[c]["sves"] + conf[c]["premature"]

    ves_pred = sum(conf[c]["ves"] for c in CLASSES) + extra["ves"]
    sves_pred = sum(conf[c]["sves"] for c in CLASSES) + extra["sves"]
    all_pred = sum(flagged(c) for c in CLASSES) + sum(extra.values())
    ect = flagged("V") + flagged("S")
    ref_v = sum(conf["V"].values())
    ref_s = sum(conf["S"].values())
    subg = {c: {g: {"ref": sum(r["subgroups"][c][g][0] for r in nonpaced),
                    "found": sum(r["subgroups"][c][g][1] for r in nonpaced)} for g in ("isolated", "typical")}
            for c in ("V", "S")}
    for c in subg.values():
        for g in c.values():
            g["se"] = _ratio(g["found"], g["ref"])
    mo = {c: sum(r.get("morphology_only_ves", {}).get(c, 0) for r in nonpaced) for c in CLASSES + ["-"]}
    af = {k: sum(r["af"][k] for r in nonpaced) for k in ("ref_beats", "det_beats", "both", "episodes", "ref_episodes")}
    af["det_s"] = round(sum(r["af"]["det_s"] for r in nonpaced), 1)
    af["se"] = _ratio(af["both"], af["ref_beats"])
    af["ppv"] = _ratio(af["both"], af["det_beats"])
    af["records_with_ref"] = sum(1 for r in nonpaced if r["af"]["ref_beats"])
    af["records_with_det"] = sum(1 for r in nonpaced if r["af"]["episodes"])
    af["records_with_det_no_ref"] = sum(1 for r in nonpaced if r["af"]["episodes"] and not r["af"]["ref_beats"])
    ru = {k: sum(r["runs"][k] for r in nonpaced) for k in nonpaced[0]["runs"]} if nonpaced else {}
    if ru:
        ru["se"] = _ratio(ru["ref_found"], ru["ref"])
        ru["se_S"] = _ratio(ru["ref_S_found"], ru["ref_S"])
        ru["se_V"] = _ratio(ru["ref_V_found"], ru["ref_V"])
        ru["ppv"] = _ratio(ru["det_true"], ru["det"])
    # the same without records that contain atrial fibrillation / flutter
    noaf = [r for r in nonpaced if not r["atrial_fibrillation_or_flutter"]]
    c2 = {c: {l: sum(r["confusion"][c][l] for r in noaf) for l in ("ves", "sves")} for c in CLASSES}
    e2 = {l: sum(r["unmatched_events"][l] for r in noaf) for l in ("ves", "sves")}
    v2p = sum(c2[c]["ves"] for c in CLASSES) + e2["ves"]
    s2p = sum(c2[c]["sves"] for c in CLASSES) + e2["sves"]
    no_af = {"records": len(noaf),
             "veb_se": _ratio(c2["V"]["ves"], sum(sum(r["confusion"]["V"].values()) for r in noaf)),
             "veb_ppv": _ratio(c2["V"]["ves"], v2p),
             "sveb_se": _ratio(c2["S"]["sves"], sum(sum(r["confusion"]["S"].values()) for r in noaf)),
             "sveb_ppv": _ratio(c2["S"]["sves"], s2p)}
    return {
        "records": len(rows), "records_class_stats": len(nonpaced), "subgroups": subg,
        "qrs": {**q, "se": _ratio(q["tp"], q["ref"]), "ppv": _ratio(q["tp"], q["tp"] + q["fp"]),
                "usable_pct": _ratio(q["usable"], q["ref"])},
        "confusion": conf, "unmatched_events": extra, "morphology_only_ves": mo,
        "veb": {"ref": ref_v, "found_any": flagged("V"), "found_as_ves": conf["V"]["ves"],
                "se_any": _ratio(flagged("V"), ref_v), "se": _ratio(conf["V"]["ves"], ref_v),
                "pred": ves_pred, "ppv": _ratio(conf["V"]["ves"], ves_pred)},
        "sveb": {"ref": ref_s, "found_any": flagged("S"), "found_as_sves": conf["S"]["sves"],
                 "se_any": _ratio(flagged("S"), ref_s), "se": _ratio(conf["S"]["sves"], ref_s),
                 "pred": sves_pred, "ppv": _ratio(conf["S"]["sves"], sves_pred)},
        "ectopic": {"ref": ref_v + ref_s, "found": ect, "se": _ratio(ect, ref_v + ref_s),
                    "pred": all_pred, "ppv": _ratio(ect + flagged("F"), all_pred),
                    "false_on_normal": flagged("N"), "false_no_beat": sum(extra.values())},
        "af": af, "runs": ru, "without_af_records": no_af,
    }


DATABASES = {
    "mitdb": {"title": "MIT-BIH Arrhythmia Database 1.0.0 (PhysioNet)", "lead": "", "paced": PACED},
    "incartdb": {"title": "St Petersburg INCART 12-lead Arrhythmia Database 1.0.0 (PhysioNet)", "lead": "II",
                 "paced": set()},
}


def run_all(db: Path, kind: str = "mitdb", records: Any = None, verbose: bool = True) -> List[Dict[str, Any]]:
    spec = DATABASES[kind]
    recs = records or (db / "RECORDS").read_text().split()
    rows = []
    for rec in recs:
        row = run_record(db, rec, spec["lead"], spec["paced"])
        rows.append(row)
        if verbose:
            q, c = row["qrs"], row["confusion"]
            print(f"{rec}: QRS Se {_ratio(q['tp'], q['ref'])} % +P {_ratio(q['tp'], q['tp'] + q['fp'])} %"
                  f"  V {sum(c['V'].values())} → ves {c['V']['ves']}  S {sum(c['S'].values())} → sves {c['S']['sves']}",
                  flush=True)
    return rows


def validate(db: Path, out: Path, kind: str = "mitdb") -> Dict[str, Any]:
    rows = run_all(db, kind)
    from . import __version__
    from .analysis import ANALYSIS_VERSION
    result = {"openholter_version": __version__, "analysis_version": ANALYSIS_VERSION,
              "database": DATABASES[kind]["title"], "fs_hz": FS_OUT,
              "tolerance_s": TOL, "start_s": START_S, "end_excluded_s": END_S,
              "summary": summarize_results(rows)}
    if kind == "mitdb":
        result["summary_ds1"] = summarize_results([r for r in rows if r["record"] in DS1])
        result["summary_ds2"] = summarize_results([r for r in rows if r["record"] in DS2])
        result["ds1_records"], result["ds2_records"] = DS1, DS2
    result["records"] = rows
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{kind}-v{ANALYSIS_VERSION}"
    (out / f"{stem}-results.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    write_markdown(result, out / f"{stem}-records.md", kind)
    return result


def _pct(v: Any) -> str:
    return "–" if v is None else f"{v:.1f}".replace(".", ",")


def write_markdown(result: Dict[str, Any], path: Path, kind: str = "mitdb") -> None:
    """Per-record table (generated; do not edit by hand)."""
    L = [f"<!-- generated by `python -m openholter validate`, OpenHolter {result['openholter_version']}, "
         f"analysis v{result['analysis_version']} -->",
         f"Aineisto: {result['database']}, analyysiversio {result['analysis_version']}.", "",
         "| Tallenne | Osa | Kytkentä | Huom. | QRS Se % | QRS +P % | VES viite | VES löydetty | VES väärä | "
         "SVES viite | SVES löydetty | SVES väärä | Epäsäänn. rytmi, viite / löydetty (lyöntejä) | Sarjat viite / löydetty / väärä |",
         "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in result["records"]:
        q, c, a, ru = r["qrs"], r["confusion"], r["af"], r["runs"]
        part = "DS1" if r["record"] in DS1 else "DS2" if r["record"] in DS2 else "–"
        if kind != "mitdb":
            part = "testi"
        note = ", ".join(x for x in ("tahdistettu" if r["paced"] else "",
                                     "eteisvärinä/-lepatus" if r["atrial_fibrillation_or_flutter"] else "") if x)
        ves_fp = sum(c[k]["ves"] for k in CLASSES if k != "V") + r["unmatched_events"]["ves"]
        sves_fp = sum(c[k]["sves"] for k in CLASSES if k != "S") + r["unmatched_events"]["sves"]
        L.append(f"| {r['record']} | {part} | {r['lead']} | {note} | {_pct(_ratio(q['tp'], q['ref']))} | "
                 f"{_pct(_ratio(q['tp'], q['tp'] + q['fp']))} | {sum(c['V'].values())} | {c['V']['ves']} | {ves_fp} | "
                 f"{sum(c['S'].values())} | {c['S']['sves']} | {sves_fp} | {a['ref_beats']} / {a['det_beats']} | "
                 f"{ru['ref']} / {ru['ref_found']} / {ru['det'] - ru['det_true']} |")
    L += ["", "*VES/SVES väärä* = merkinnät, joiden viitelyönti on jotain muuta luokkaa tai joille ei ole viitelyöntiä. "
          "*Epäsäännöllinen rytmi:* viitteen eteisvärinä-/lepatusjaksoihin osuvat lyönnit / ohjelman "
          "epäsäännöllisen rytmin jaksoihin osuvat lyönnit. *Sarjat:* vähintään 3 peräkkäistä S- tai V-lyöntiä "
          "viitteessä / niistä löydetyt / ohjelman sarjat, joille ei ole viitesarjaa."]
    path.write_text("\n".join(L) + "\n")
