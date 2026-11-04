"""PDF report of one recording: summary page, ECG strips at 25 mm/s, full disclosure.

Runs in a separate low-priority process (like the analysis). Everything is drawn as vector
graphics with reportlab, so strips stay sharp when printed or zoomed.
"""
from __future__ import annotations

import io
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from . import posture as P
from .analysis import read_result, run_analysis

MM = 72 / 25.4  # points per millimetre
PAGE_W, PAGE_H = 210 * MM, 297 * MM
MARGIN = 14 * MM

INK = (0.12, 0.14, 0.18)
MUTED = (0.42, 0.46, 0.53)
FAINT = (0.62, 0.65, 0.71)
GRID_MINOR = (0.98, 0.86, 0.87)
GRID_MAJOR = (0.94, 0.66, 0.69)
ECG = (0.08, 0.09, 0.12)
ACCENT = (0.86, 0.22, 0.33)
SYM = (0.88, 0.33, 0.62)
POSTURE_RGB = {
    "supine": (0.49, 0.55, 1.0), "left": (0.2, 0.78, 0.71), "right": (0.96, 0.69, 0.3),
    "prone": (0.75, 0.52, 0.99), "upright": (0.58, 0.64, 0.72), "moving": (0.8, 0.82, 0.86),
    "unknown": (0.9, 0.9, 0.92),
}
_LANG = {"lang": "fi"}  # set per report by build_report (the worker builds one report at a time)


def T(fi: str, en: str) -> str:
    return en if _LANG["lang"] == "en" else fi


class _Labels(dict):
    """Posture names in the report's language; LABEL[k] / LABEL.get(k) as before."""
    NAMES = {"supine": ("Selällään", "Supine"), "left": ("Vasen kylki", "Left side"), "right": ("Oikea kylki", "Right side"),
             "prone": ("Vatsallaan", "Prone"), "upright": ("Pystyssä", "Upright"), "moving": ("Kääntyminen", "Turning"),
             "unknown": ("Ei asentotietoa", "No posture data")}

    def __getitem__(self, k: str) -> str:
        fi, en = self.NAMES[k]
        return T(fi, en)

    def get(self, k: Any, default: Any = None) -> Any:
        return self[k] if k in self.NAMES else default


LABEL = _Labels()
WEEKDAYS = {"fi": ["maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai"],
            "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}


def _date(d: datetime, with_time: bool = False) -> str:
    if _LANG["lang"] == "en":
        return d.strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y")
    return d.strftime("%d.%m.%Y %H.%M" if with_time else "%d.%m.%Y")


def _clock(ts: float, sec: bool = False) -> str:
    sep = ":" if _LANG["lang"] == "en" else "."
    return datetime.fromtimestamp(ts).strftime(sep.join(["%H", "%M", "%S"] if sec else ["%H", "%M"]))


def _dur(s: float) -> str:
    h, m = int(s // 3600), int(s % 3600 // 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def _num(x: float, d: int = 1) -> str:
    s = f"{x:.{d}f}"
    return s if _LANG["lang"] == "en" else s.replace(".", ",")


def _baseline_removed(v: np.ndarray, fs: float) -> np.ndarray:
    """Subtract a 1 s moving average (display only)."""
    k = max(3, int(fs))
    pad = np.pad(v.astype(np.float64), (k // 2, k - k // 2 - 1), mode="edge")
    return v - np.convolve(pad, np.ones(k) / k, mode="valid")


class Report:
    def __init__(self, session_dir: Path, home: Path):
        from .sessions import assemble

        self.dir = session_dir
        self.res = read_result(session_dir)
        if self.res is None or self.res.get("version") is None:
            run_analysis(str(session_dir), str(home))
            self.res = read_result(session_dir)
        self.s = assemble(session_dir)
        self.meta = self.s.meta
        self.t0 = self.meta["started_wall_ns"] / 1e9
        self.dur = self.s.duration
        cal, _ = P.CalibrationStore(home).for_session(session_dir, self.meta)
        self.cls = None
        if cal is not None:
            self.cls = P.classify_night(P.per_second(self.s.acc_t, self.s.acc_mg, self.dur), cal)["cls"]
        ect = (self.res or {}).get("ectopy", (self.res or {}).get("ectopy_rr")) or {}
        self.ectopics = np.array(ect.get("events") or [], dtype=float)
        self.symptoms = [((e["wall_ns"] / 1e9) - self.t0, e.get("note", ""))
                         for e in self.meta.get("events", []) if e.get("kind") == "symptom" and e.get("wall_ns")]
        self.page = 0

    # ------------------------------------------------------------------ helpers

    def kind_label(self, t: float) -> str:
        for d in ((self.res or {}).get("ectopy") or {}).get("details") or []:
            if abs(d["t"] - t) < 0.01:
                return {"ves": "(VES)", "sves": "(SVES)"}.get(d["kind"], "")
        return ""

    def posture_at(self, t: float) -> Optional[str]:
        if self.cls is None or len(self.cls) == 0:
            return None
        c = int(self.cls[int(np.clip(t, 0, len(self.cls) - 1))])
        return P.CLASS_NAMES[c] if c >= 0 else None

    def hr_at(self, t: float) -> Optional[float]:
        if not len(self.s.hr_t):
            return None
        a, b = np.searchsorted(self.s.hr_t, [t - 5, t + 5])
        v = self.s.hr_bpm[a:b]
        v = v[v > 0]
        return float(v.mean()) if len(v) else None

    def ecg(self, a: float, b: float) -> Tuple[np.ndarray, np.ndarray]:
        i, j = np.searchsorted(self.s.ecg_t, [a, b])
        return self.s.ecg_t[i:j], self.s.ecg_uv[i:j]

    def text(self, c: Any, x: float, y: float, s: str, size: float = 9, color=INK, bold: bool = False, align: str = "l") -> None:
        c.setFillColorRGB(*color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        if align == "r":
            c.drawRightString(x, y, s)
        elif align == "c":
            c.drawCentredString(x, y, s)
        else:
            c.drawString(x, y, s)

    def new_page(self, c: Any, title: str) -> float:
        if self.page:
            c.showPage()
        self.page += 1
        c.setFillColorRGB(1, 1, 1)  # explicit paper: some viewers show transparent pages as black
        c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        start = datetime.fromtimestamp(self.t0)
        self.text(c, MARGIN, PAGE_H - 10 * MM, f"OpenHolter · {T('EKG-tallenne', 'ECG recording')} {_date(start)} {_clock(self.t0)}–{_clock(self.t0 + self.dur)}", 7.5, MUTED)
        self.text(c, PAGE_W - MARGIN, PAGE_H - 10 * MM, f"{T('sivu', 'page')} {self.page}", 7.5, MUTED, align="r")
        self.text(c, MARGIN, 8 * MM, T("Tutkimuskäyttöön, ei lääkinnällinen laite. Ei korvaa lääkärin arviota. Sydänoireissa ota yhteys lääkäriin, hätätilanteessa soita 112.", "For research use, not a medical device. Does not replace a doctor's assessment. If you have heart symptoms, contact a doctor; in an emergency call 112 / 911."), 7, FAINT)
        self.text(c, MARGIN, PAGE_H - 20 * MM, title, 15, INK, bold=True)
        return PAGE_H - 27 * MM

    # ------------------------------------------------------------------ page 1

    def summary_page(self, c: Any) -> None:
        start = datetime.fromtimestamp(self.t0)
        y = self.new_page(c, f"{WEEKDAYS[_LANG['lang']][start.weekday()].capitalize()} {_date(start)}")
        dev = self.meta.get("device") or {}
        self.text(c, MARGIN, y, f"{_clock(self.t0)}–{_clock(self.t0 + self.dur)}  ·  {_dur(self.dur)}  ·  {dev.get('name') or 'Polar H10'}"
                  f"  ·  {T('yksikytkentäinen EKG 130 Hz', 'single-lead ECG 130 Hz')}", 9, MUTED)
        y -= 9 * MM

        sm = (self.res or {}).get("summary") or {}
        ect = (self.res or {}).get("ectopy", (self.res or {}).get("ectopy_rr")) or {}
        hrv = (self.res or {}).get("hrv") or {}
        qw = sm.get("quality_windows") or {}
        nq = sum(qw.values()) or 1
        tiles = [
            (T("Tallennettu", "Recorded"), f"{_num((sm.get('coverage') or 0) * 100)} %", f"{T('katkoja', 'gaps')} {len(self.meta.get('connections', [])) - 1}"),
            (T("Signaalin laatu", "Signal quality"), f"{round((sm.get('quality_score') or 0) * 100)} %", f"{T('heikkoa', 'poor')} {_num((qw.get('poor', 0) + qw.get('none', 0)) / nq * 100)} %"),
            (T("Keskisyke", "Mean heart rate"), f"{round(sm['hr_mean'])} bpm" if sm.get("hr_mean") else "–", f"{sm.get('hr_min', '–')}–{sm.get('hr_max', '–')} bpm"),
            (T("Lyöntejä", "Beats"), f"{(ect.get('beats') if ect.get('method') == 'ecg' else sm.get('rr_count', 0)) or 0:,}".replace(",", " "),
             T("EKG:n R-piikit", "R peaks from the ECG") if ect.get("method") == "ecg" else T("vyön RR-välit", "strap's RR intervals")),
            (T("Lisälyönnit*", "Extra beats*"), f"{ect.get('count', 0):,}".replace(",", " "),
             f"VES {ect['ves']} · SVES {ect['sves']} · {T('pareja', 'couplets')} {ect.get('couplets', 0)}" if "ves" in ect else f"{_num((ect.get('share') or 0) * 100, 2)} % {T('lyönneistä', 'of beats')}"),
            (T("Lisälyöntejä / h", "Extra beats / h"), _num(ect.get("count", 0) / max(self.dur / 3600, 1e-6)), f"{T('bigeminiajaksoja', 'bigeminy runs')} {ect.get('bigeminy_runs', 0)}"),
            ("RMSSD", f"{round(hrv['rmssd_median'])} ms" if hrv.get("rmssd_median") else "–", T("mediaani, 5 min ikkunat", "median, 5 min windows")),
            (T("Oiremerkinnät", "Symptom marks"), str(len(self.symptoms)), T("Tunsin lisälyönnin -painike", "'I felt an extra beat' button")),
        ]
        tw = (PAGE_W - 2 * MARGIN) / 4
        for i, (k, v, sub) in enumerate(tiles):
            x = MARGIN + (i % 4) * tw
            yy = y - (i // 4) * 17 * MM
            c.setStrokeColorRGB(0.88, 0.89, 0.92); c.setLineWidth(0.6)
            c.roundRect(x + 1, yy - 13 * MM, tw - 3, 15 * MM, 4, stroke=1, fill=0)
            self.text(c, x + 3.5 * MM, yy - 2.5 * MM, k.upper(), 6.5, MUTED, bold=True)
            self.text(c, x + 3.5 * MM, yy - 8.5 * MM, v, 13, INK, bold=True)
            self.text(c, x + 3.5 * MM, yy - 11.8 * MM, sub, 6.5, MUTED)
        y -= 37 * MM

        y = self.timeline(c, y)
        y -= 6 * MM
        y = self.posture_table(c, y)
        y -= 5 * MM
        y = self.hour_table(c, y)
        if self.symptoms:
            y -= 5 * MM
            self.symptom_table(c, y)
        self.text(c, MARGIN, 15 * MM, T("* EKG:stä tunnistetut ennenaikaiset lyönnit, joita seuraa tauko. VES = leveä tai erimuotoinen QRS (todennäköisesti kammioperäinen),", "* Premature beats detected from the ECG, followed by a pause. VES = wide or differently shaped QRS (probably ventricular),"), 6.5, MUTED)
        self.text(c, MARGIN, 12 * MM, T("  SVES = normaalimuotoinen (todennäköisesti eteisperäinen). Yksikytkentäinen 130 Hz:n EKG: luokittelu on suuntaa antava, ei diagnoosi.", "  SVES = normally shaped (probably supraventricular). Single-lead 130 Hz ECG: the classification is indicative, not a diagnosis."), 6.5, MUTED)

    def timeline(self, c: Any, y: float) -> float:
        x0, w = MARGIN + 14 * MM, PAGE_W - 2 * MARGIN - 14 * MM
        X = lambda t: x0 + t / max(self.dur, 1) * w
        self.text(c, MARGIN, y, T("AIKAJANA", "TIMELINE"), 7, MUTED, bold=True)
        y -= 4 * MM
        # ectopics per 10 min
        bins = max(1, int(np.ceil(self.dur / 600)))
        counts = np.histogram(self.ectopics, bins=bins, range=(0, bins * 600))[0] if len(self.ectopics) else np.zeros(bins)
        h = 16 * MM
        top = max(5, counts.max() if len(counts) else 5)
        self.text(c, MARGIN, y - 4 * MM, T("Lisälyönnit", "Extra beats"), 6.5, MUTED)
        self.text(c, MARGIN, y - 7 * MM, "/ 10 min", 6.5, FAINT)
        c.setFillColorRGB(*ACCENT)
        for i, n in enumerate(counts):
            if n:
                bh = n / top * h
                c.rect(X(i * 600) + 0.3, y - h, max(0.6, X(600) - x0 - 0.6), bh, stroke=0, fill=1)
        self.text(c, x0 - 1.5 * MM, y - 2 * MM, str(int(top)), 6, FAINT, align="r")
        y -= h + 3 * MM
        # heart rate
        h = 20 * MM
        hr_t, hr = self.s.hr_t, self.s.hr_bpm
        m = hr > 0
        self.text(c, MARGIN, y - 4 * MM, T("Syke", "Heart rate"), 6.5, MUTED)
        if m.sum() > 10:
            nb = int(w / 0.8)
            edges = np.linspace(0, self.dur, nb + 1)
            idx = np.searchsorted(hr_t[m], edges)
            vals = np.array([hr[m][a:b].mean() if b > a else np.nan for a, b in zip(idx[:-1], idx[1:])])
            lo, hi = np.floor(np.nanmin(vals) / 10) * 10 - 5, np.ceil(np.nanmax(vals) / 10) * 10 + 5
            Y = lambda v: y - h + (v - lo) / (hi - lo) * h
            c.setStrokeColorRGB(0.9, 0.91, 0.93); c.setLineWidth(0.4)
            for v in range(int(lo) + 5, int(hi), 10):
                c.line(x0, Y(v), x0 + w, Y(v))
                self.text(c, x0 - 1.5 * MM, Y(v) - 1.5, str(v), 6, FAINT, align="r")
            c.setStrokeColorRGB(0.25, 0.45, 0.85); c.setLineWidth(0.9)
            p, pen = c.beginPath(), False
            for i, v in enumerate(vals):
                if np.isnan(v):
                    pen = False
                    continue
                xx = x0 + (i + 0.5) / nb * w
                (p.lineTo if pen else p.moveTo)(xx, Y(v))
                pen = True
            c.drawPath(p, stroke=1, fill=0)
        y -= h + 2.5 * MM
        # posture strip
        self.text(c, MARGIN, y - 3.2 * MM, T("Asento", "Posture"), 6.5, MUTED)
        if self.cls is not None:
            n = len(self.cls)
            step = max(1, int(n / (w / 0.5)))
            for a in range(0, n, step):
                seg = self.cls[a:a + step]
                seg = seg[seg >= 0]
                if not len(seg):
                    continue
                name = P.CLASS_NAMES[int(np.bincount(seg, minlength=6).argmax())]
                c.setFillColorRGB(*POSTURE_RGB[name])
                c.rect(X(a), y - 5 * MM, X(a + step) - X(a) + 0.2, 5 * MM, stroke=0, fill=1)
        else:
            self.text(c, x0, y - 3.5 * MM, T("ei kalibrointia", "not calibrated"), 6.5, FAINT)
        ytop = y + 2.5 * MM + 20 * MM + 3 * MM + 16 * MM
        # symptom marks across all tracks
        c.setStrokeColorRGB(*SYM); c.setLineWidth(0.8)
        for t, _ in self.symptoms:
            c.line(X(t), y - 5 * MM, X(t), ytop)
        y -= 5 * MM + 1.5 * MM
        # clock axis
        first = (int(self.t0 // 3600) + 1) * 3600
        for tm in range(first, int(self.t0 + self.dur), 3600):
            xx = X(tm - self.t0)
            c.setStrokeColorRGB(*FAINT); c.setLineWidth(0.4); c.line(xx, y, xx, y + 1.2 * MM)
            self.text(c, xx, y - 3 * MM, _clock(tm), 6.5, MUTED, align="c")
        legend_x = x0
        y -= 7 * MM
        for name in ("supine", "left", "right", "prone", "upright"):
            c.setFillColorRGB(*POSTURE_RGB[name]); c.rect(legend_x, y, 2.5 * MM, 2.5 * MM, stroke=0, fill=1)
            self.text(c, legend_x + 3.5 * MM, y + 0.4 * MM, LABEL[name], 6.5, MUTED)
            legend_x += 25 * MM
        c.setStrokeColorRGB(*SYM); c.setLineWidth(1); c.line(legend_x, y, legend_x, y + 2.5 * MM)
        self.text(c, legend_x + 2 * MM, y + 0.4 * MM, T("oiremerkintä", "symptom mark"), 6.5, MUTED)
        return y - 3 * MM

    def table(self, c: Any, y: float, title: str, head: List[str], rows: List[List[str]], widths: List[float],
              swatch: Optional[List[Optional[str]]] = None) -> float:
        self.text(c, MARGIN, y, title, 7, MUTED, bold=True)
        y -= 5 * MM
        x = MARGIN
        for hd, wd in zip(head, widths):
            self.text(c, x, y, hd, 6.5, FAINT, bold=True)
            x += wd * MM
        y -= 1.5 * MM
        c.setStrokeColorRGB(0.88, 0.89, 0.92); c.setLineWidth(0.5); c.line(MARGIN, y, PAGE_W - MARGIN, y)
        for ri, row in enumerate(rows):
            y -= 4.6 * MM
            x = MARGIN
            for ci, (cell, wd) in enumerate(zip(row, widths)):
                dx = 0
                if ci == 0 and swatch and swatch[ri]:
                    c.setFillColorRGB(*POSTURE_RGB[swatch[ri]]); c.rect(x, y - 0.2 * MM, 2.3 * MM, 2.3 * MM, stroke=0, fill=1)
                    dx = 3.5 * MM
                self.text(c, x + dx, y, cell, 8, INK, bold=(ci == 0))
                x += wd * MM
        return y - 2 * MM

    def posture_table(self, c: Any, y: float) -> float:
        p = (self.res or {}).get("posture") or {}
        if not p.get("calibrated"):
            self.text(c, MARGIN, y, T("ASENNOITTAIN", "BY POSTURE"), 7, MUTED, bold=True)
            self.text(c, MARGIN, y - 5 * MM, T("Asentoa ei ole kalibroitu, joten asennoittaista jakaumaa ei voitu laskea.", "Posture is not calibrated, so the distribution by posture could not be computed."), 8, MUTED)
            return y - 8 * MM
        sec = p["seconds"]
        lying = sum(sec[k] for k in P.LYING) or 1
        eb = ((self.res or {}).get("ectopy", (self.res or {}).get("ectopy_rr")) or {}).get("by_posture") or {}
        hp = (self.res or {}).get("hr_by_posture") or {}
        hb = ((self.res or {}).get("hrv") or {}).get("by_posture") or {}
        names = [k for k in P.LYING + ["upright", "moving", "unknown"] if sec.get(k, 0) > 0 or (k in eb and eb[k]["count"])]
        rate = lambda v: "–" if v is None else _num(v, 1 if v < 10 else 0)
        rows = [[LABEL[k], _dur(sec[k]) if sec.get(k) else "–", f"{round(sec[k] / lying * 100)} %" if k in P.LYING else "–",
                 str(eb[k]["count"]) if k in eb else "0", rate(eb[k]["per_hour"]) if k in eb else "–",
                 f"{_num(eb[k]['share'] * 100, 2)} %" if k in eb and eb[k]["share"] is not None else "–",
                 f"{round(hp[k]['mean'])}" if k in hp else "–", f"{round(hb[k]['rmssd_median'])} ms" if k in hb else "–"] for k in names]
        return self.table(c, y, T("ASENNOITTAIN", "BY POSTURE"), [T("Asento", "Posture"), T("Aika", "Time"), T("Makuuajasta", "Of lying"), T("Lisälyönnit", "Extra beats"), "/ h", T("% lyönneistä", "% of beats"), T("Syke", "HR"), "RMSSD"],
                          rows, [30, 24, 22, 22, 16, 24, 16, 18], names)

    def hour_table(self, c: Any, y: float) -> float:
        hours = (self.res or {}).get("hours") or []
        byh = ((self.res or {}).get("ectopy", (self.res or {}).get("ectopy_rr")) or {}).get("by_hour") or {}
        rows = [[h["hour"] if _LANG["lang"] == "en" else h["hour"].replace(":", "."), f"{round(h['hr_mean'])}", str(byh.get(h["hour"], 0)),
                 LABEL.get(h.get("posture"), "–"), f"{round(h['minutes'])} min"] for h in hours]
        return self.table(c, y, T("TUNNEITTAIN", "BY HOUR"), [T("Tunti", "Hour"), T("Syke", "HR"), T("Lisälyönnit", "Extra beats"), T("Yleisin asento", "Main posture"), T("Dataa", "Data")], rows, [22, 18, 24, 34, 22])

    def symptom_table(self, c: Any, y: float) -> float:
        rows = []
        for t, note in self.symptoms[:10]:
            near = self.ectopics[(self.ectopics >= t - 15) & (self.ectopics <= t + 2)] if len(self.ectopics) else []
            if len(near):
                d = t - near[np.argmin(np.abs(t - near))]
                found = (T("lisälyönti {0} s ennen", "extra beat {0} s before") if d >= 0 else T("lisälyönti {0} s jälkeen", "extra beat {0} s after")).format(_num(abs(d)))
            else:
                found = T("ei lisälyöntiä lähellä", "no extra beat nearby")
            rows.append([_clock(self.t0 + t, sec=True), LABEL.get(self.posture_at(t), "–"), found, note[:40]])
        return self.table(c, y, T("OIREMERKINNÄT", "SYMPTOM MARKS"), [T("Aika", "Time"), T("Asento", "Posture"), T("Lisälyönti (15 s ennen – 2 s jälkeen)", "Extra beat (15 s before – 2 s after)"), T("Huomio", "Note")], rows, [24, 30, 70, 50])

    # ------------------------------------------------------------------ strips

    def strip(self, c: Any, x: float, y: float, t_start: float, seconds: float, caption: str, marks: List[Tuple[float, Tuple]] = ()) -> None:
        """ECG paper strip at 25 mm/s and 10 mm/mV; (x, y) = top-left."""
        w, h = seconds * 25 * MM, 30 * MM
        mid = y - h / 2
        c.setLineWidth(0.25)
        for i in range(int(seconds / 0.04) + 1):
            c.setStrokeColorRGB(*(GRID_MAJOR if i % 5 == 0 else GRID_MINOR))
            c.line(x + i * MM, y, x + i * MM, y - h)
        for i in range(0, 31):
            c.setStrokeColorRGB(*(GRID_MAJOR if (i - 15) % 5 == 0 else GRID_MINOR))
            c.line(x, y - i * MM, x + w, y - i * MM)
        t, v = self.ecg(t_start - 1, t_start + seconds + 1)
        if len(t) > 10:
            vv = _baseline_removed(v, self.s.ecg_fs) / 1000.0 * 10 * MM  # mV -> mm -> points
            keep = (t >= t_start) & (t <= t_start + seconds)
            tt, vv = t[keep], np.clip(vv[keep], -h / 2, h / 2)
            c.setStrokeColorRGB(*ECG); c.setLineWidth(0.7); c.setLineJoin(1)
            p, prev = c.beginPath(), None
            for a, b in zip(tt, vv):
                xx = x + (a - t_start) * 25 * MM
                if prev is None or a - prev > 0.5:
                    p.moveTo(xx, mid + b)
                else:
                    p.lineTo(xx, mid + b)
                prev = a
            c.drawPath(p, stroke=1, fill=0)
        else:
            self.text(c, x + w / 2, mid, T("ei dataa", "no data"), 8, MUTED, align="c")
        for tm, col in marks:
            if t_start <= tm <= t_start + seconds:
                xx = x + (tm - t_start) * 25 * MM
                c.setStrokeColorRGB(*col); c.setLineWidth(0.8); c.setDash(2, 2)
                c.line(xx, y, xx, y - h); c.setDash()
        # 1 mV calibration pulse
        c.setStrokeColorRGB(*ECG); c.setLineWidth(0.7)
        c.line(x + 1 * MM, mid, x + 1 * MM, mid + 10 * MM)
        self.text(c, x, y + 1.8 * MM, caption, 7.5, INK)
        self.text(c, x + w, y + 1.8 * MM, "25 mm/s · 10 mm/mV", 6.5, MUTED, align="r")

    def strip_pages(self, c: Any) -> None:
        sec = 7.0  # 175 mm at 25 mm/s fits the A4 width
        items: List[Tuple[float, str]] = []
        for t, note in self.symptoms[:12]:
            items.append((t - sec * 0.7, f"{T('Oiremerkintä', 'Symptom mark')} {_clock(self.t0 + t, True)}" + (f" – {note}" if note else "")))
        # ectopic examples spread through the night, one per posture first
        ex: List[float] = []
        seen = set()
        for e in self.ectopics:
            p = self.posture_at(e)
            if p not in seen and all(abs(e - x) > 120 for x in ex):
                ex.append(e); seen.add(p)
        if len(self.ectopics):
            for e in self.ectopics[np.linspace(0, len(self.ectopics) - 1, 8).astype(int)]:
                if len(ex) >= 8:
                    break
                if all(abs(e - x) > 300 for x in ex):
                    ex.append(float(e))
        for e in sorted(ex):
            items.append((e - sec * 0.5, f"{T('Lisälyönti', 'Extra beat')} {self.kind_label(e)} {_clock(self.t0 + e, True)}"))
        # one quiet sample per hour
        for h in range(int(self.dur // 3600) + 1):
            t = h * 3600 + 1800
            if t + sec < self.dur:
                items.append((t, f"{T('Tuntinäyte', 'Hourly sample')} {_clock(self.t0 + t, True)}"))
        if not items:
            return
        y = self.new_page(c, T("EKG-liuskat", "ECG strips"))
        for t, cap in items:
            if y < 50 * MM:
                y = self.new_page(c, T("EKG-liuskat (jatkuu)", "ECG strips (continued)"))
            t = max(0.0, min(t, self.dur - sec))
            p, hr = self.posture_at(t + sec / 2), self.hr_at(t + sec / 2)
            extra = "  ·  ".join(x for x in (LABEL.get(p) if p else None, f"{round(hr)} bpm" if hr else None) if x)
            marks = [(st, SYM) for st, _ in self.symptoms] + [(e, ACCENT) for e in self.ectopics[(self.ectopics > t) & (self.ectopics < t + sec)]]
            self.strip(c, MARGIN + 3 * MM, y - 3 * MM, t, sec, f"{cap}{'  ·  ' + extra if extra else ''}", marks)
            y -= 40 * MM

    # ------------------------------------------------------------------ full disclosure

    def full_disclosure(self, c: Any) -> None:
        row_s, row_h = 60.0, 8.6 * MM
        x0 = MARGIN + 12 * MM
        w = PAGE_W - MARGIN - x0
        rows = int(np.ceil(self.dur / row_s))
        y = self.new_page(c, T("Koko tallenne", "Full disclosure"))
        self.text(c, MARGIN, y, T("1 minuutti riviä kohden, 2,9 mm/s · 4 mm/mV.  Punainen = lisälyönti, violetti = oiremerkintä, harmaa = ei dataa.",
                                  "1 minute per row, 2.9 mm/s · 4 mm/mV.  Red = extra beat, violet = symptom mark, grey = no data."), 7, MUTED)
        y -= 6 * MM
        scale = 4 * MM / 1000.0
        cols = int(w / (0.3 * MM))
        for r in range(rows):
            if y - row_h < 14 * MM:
                y = self.new_page(c, T("Koko tallenne (jatkuu)", "Full disclosure (continued)")) - 2 * MM
            a = r * row_s
            mid = y - row_h / 2
            if r % 5 == 0 or True:
                self.text(c, MARGIN, mid - 2, _clock(self.t0 + a), 6.5, MUTED)
            t, v = self.ecg(a - 1, a + row_s + 1)
            if len(t) > 100:
                vv = _baseline_removed(v, self.s.ecg_fs)
                keep = (t >= a) & (t < a + row_s)
                t, vv = t[keep], vv[keep]
                edges = np.linspace(a, a + row_s, cols + 1)
                idx = np.searchsorted(t, edges)
                c.setStrokeColorRGB(*ECG); c.setLineWidth(0.35)
                p, pen = c.beginPath(), False
                for i in range(cols):
                    s0, s1 = idx[i], idx[i + 1]
                    if s1 <= s0:
                        pen = False
                        continue
                    seg = vv[s0:s1]
                    lo, hi = np.clip(seg.min() * scale, -row_h * 0.55, row_h * 0.55), np.clip(seg.max() * scale, -row_h * 0.55, row_h * 0.55)
                    xx = x0 + i * w / cols
                    first, second = (lo, hi) if seg.argmin() < seg.argmax() else (hi, lo)
                    (p.lineTo if pen else p.moveTo)(xx, mid + first)
                    p.lineTo(xx + 0.15 * MM, mid + second)
                    pen = True
                c.drawPath(p, stroke=1, fill=0)
            else:
                c.setFillColorRGB(0.93, 0.94, 0.95); c.rect(x0, mid - 1 * MM, w, 2 * MM, stroke=0, fill=1)
            # marks
            for e in self.ectopics[(self.ectopics >= a) & (self.ectopics < a + row_s)] if len(self.ectopics) else []:
                xx = x0 + (e - a) / row_s * w
                c.setFillColorRGB(*ACCENT); c.rect(xx - 0.3, y - 1.4 * MM, 0.8, 1.2 * MM, stroke=0, fill=1)
            for st, _ in self.symptoms:
                if a <= st < a + row_s:
                    xx = x0 + (st - a) / row_s * w
                    c.setStrokeColorRGB(*SYM); c.setLineWidth(0.9); c.line(xx, y, xx, y - row_h)
            y -= row_h

    def build(self) -> bytes:
        from reportlab.pdfgen import canvas

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H), pageCompression=1)
        start = datetime.fromtimestamp(self.t0)
        c.setTitle(f"{T('EKG-tallenne', 'ECG recording')} {_date(start, True)}")
        c.setAuthor("OpenHolter")
        c.setSubject(T("Polar H10 -yksikytkentäinen EKG. Ei lääkinnällinen laite.", "Polar H10 single-lead ECG. Not a medical device."))
        self.summary_page(c)
        self.strip_pages(c)
        self.full_disclosure(c)
        c.save()
        return buf.getvalue()


def build_report(session_dir_str: str, home_str: str, lang: str = "fi") -> Dict[str, Any]:
    """Worker entry point: writes cache/report-<lang>.pdf and returns its path."""
    t = time.time()
    _LANG["lang"] = lang if lang in ("fi", "en") else "fi"
    d = Path(session_dir_str)
    pdf = Report(d, Path(home_str)).build()
    out = d / "cache" / f"report-{_LANG['lang']}.pdf"
    out.parent.mkdir(exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes(pdf)
    tmp.replace(out)
    return {"path": str(out), "bytes": len(pdf), "seconds": round(time.time() - t, 1)}
