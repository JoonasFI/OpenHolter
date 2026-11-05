"""Protocol, storage and decoding round trips. Run: python -m pytest tests  (or python tests/test_pipeline.py)"""
import gzip
import struct
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np

from openholter import pmd
from openholter.sessions import assemble, ecg_window, summarize
from openholter.simulator import TRUE_FS, generate_night
from openholter.storage import iter_records


def test_ecg_frame_roundtrip():
    v = np.array([0, 1, -1, 8_388_607, -8_388_608, 1234, -1234], dtype=np.int32)
    f = pmd.parse_frame(pmd.encode_frame(pmd.ECG, 123456789, v))
    assert f.measurement == pmd.ECG and f.sensor_ts_ns == 123456789
    assert f.samples.tolist() == v.tolist()


def test_known_h10_ecg_bytes():
    # measurement 0, timestamp, frame type 0, samples 0x000064 (=100) and 0xFFFF9C (=-100)
    raw = bytes([0x00]) + struct.pack("<Q", 5) + bytes([0x00, 0x64, 0x00, 0x00, 0x9C, 0xFF, 0xFF])
    assert pmd.parse_frame(raw).samples.tolist() == [100, -100]


def test_acc_frame_roundtrip():
    g = np.array([[10, -20, 1000], [-1000, 5, 3]], dtype=np.int32)
    f = pmd.parse_frame(pmd.encode_frame(pmd.ACC, 1, g))
    assert f.samples.tolist() == g.tolist()


def test_start_commands():
    assert pmd.start_ecg_command().hex() == "02000001820001010e00"
    assert pmd.start_acc_command(50, 16, 4).hex() == "02020001320001011000020104 00".replace(" ", "")


def test_heart_rate():
    hr = pmd.parse_heart_rate(pmd.encode_heart_rate(61, [983.4, 1001.0]))
    assert hr.bpm == 61 and [round(r) for r in hr.rr_ms] == [983, 1001] and hr.contact is True


def test_control_response_and_settings():
    resp = pmd.parse_control_response(bytes([0xF0, 0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x82, 0x00, 0x01, 0x01, 0x0E, 0x00]))
    assert resp.ok
    assert pmd.parse_settings(resp.params) == {"sample_rate": [130], "resolution": [14]}


def test_truncated_chunk_is_readable():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.rec.gz"
        with gzip.open(p, "wb") as f:
            for i in range(100):
                f.write(struct.pack("<BHHqq", 1, 0, 3, i, i) + b"abc")
        data = p.read_bytes()
        p.write_bytes(data[: len(data) - 30])  # simulate a crash mid-write
        n = sum(1 for _ in iter_records(p))
        assert 0 < n <= 100


def test_simulated_night_decodes():
    with tempfile.TemporaryDirectory() as d:
        sd = generate_night(Path(d), hours=0.25, start=datetime(2026, 1, 1, 23, 0), seed=3)
        s = assemble(sd)
        assert abs(s.ecg_fs - TRUE_FS) < 0.01
        assert len(s.ecg_uv) > 0.18 * 3600 * 130  # minus the simulated ~95 s BLE drop-out
        assert np.all(np.diff(s.ecg_t) > 0)
        assert any(b - a > 60 for a, b in summarize(s)["gaps"])
        # sample spacing equals the sensor clock, independent of BLE latency jitter
        d_t = np.diff(s.ecg_t)
        assert np.median(np.abs(d_t - 1 / TRUE_FS)) < 1e-6
        # session time starts near 0 despite simulated BLE latency
        assert 0 <= s.ecg_t[0] < 1.0
        w = ecg_window(s, 60, 70, 1500)
        assert w["mode"] == "raw" and len(w["v"]) > 1200
        e = ecg_window(s, 0, s.duration, 800)
        assert e["mode"] == "envelope" and len(e["min"]) == 800
        summ = summarize(s)
        assert 40 < summ["hr_mean"] < 90 and summ["quality_score"] > 0.5


def test_posture_and_ectopy_on_simulated_night():
    import json
    from openholter import posture as P
    from openholter.analysis import ectopy, heart_rate_variability
    from openholter.simulator import POSTURE_G, SyntheticBody
    with tempfile.TemporaryDirectory() as d:
        sd = generate_night(Path(d), hours=1.5, start=datetime(2026, 1, 1, 23, 0), seed=4)
        s = assemble(sd)
        truth = json.loads((sd / "simulation_truth.json").read_text())
        body = SyntheticBody(seed=4, night=True, hours=1.5)  # same seed -> same strap orientation
        cal = P.Calibration("t", 0, "test", {k: body.strap @ np.array(POSTURE_G[k], float) for k in ("supine", "left")}, {})
        assert not cal.quality()["warnings"]
        cls = P.classify_night(P.per_second(s.acc_t, s.acc_mg, s.duration), cal)["cls"]
        true = np.full(len(cls), -1)
        for a, b, p in truth["schedule"]:
            true[int(a):min(len(cls), int(b))] = P.POSTURES.index(p)
        m = (cls >= 0) & (cls < 5) & (true >= 0)
        assert (cls[m] == true[m]).mean() > 0.97
        e = ectopy(s.rr_t, s.rr_ms, cls, 0)
        ves = np.array(truth["ves_times"])
        ev = np.array(e["events"])
        hits = sum(np.min(np.abs(ves - x)) < 1.5 for x in ev)
        assert len(ev) > 0 and hits / len(ev) > 0.95  # precision
        assert hits / len(ves) > 0.85  # recall (couplets count once)
        hrv = heart_rate_variability(s.rr_t, s.rr_ms, cls)
        assert 20 < hrv["rmssd_median"] < 90


def test_trash_roundtrip():
    from openholter.trash import Trash
    with tempfile.TemporaryDirectory() as d:
        home = Path(d)
        sessions = home / "sessions"
        sd = generate_night(sessions, hours=0.05, start=datetime(2026, 1, 1, 23, 0), seed=2)
        t = Trash(home, sessions)
        name = t.move_in(sd)
        assert not sd.exists() and [e["name"] for e in t.list()] == [name]
        assert t.list()[0]["purge_in_days"] > 29
        assert t.restore(name) == sd.name and sd.exists() and not t.list()
        assert not (sd / ".deleted.json").exists()
        t.purge(t.move_in(sd))
        assert not t.list() and not sd.exists()
        try:
            t.purge("../sessions")  # never outside the trash
            raise AssertionError("path escape not rejected")
        except KeyError:
            pass


def test_pdf_report():
    from openholter.report import build_report
    with tempfile.TemporaryDirectory() as d:
        home = Path(d)
        sd = generate_night(home / "sessions", hours=0.3, start=datetime(2026, 1, 1, 23, 0), seed=6)
        info = build_report(str(sd), str(home))
        pdf = Path(info["path"]).read_bytes()
        assert pdf.startswith(b"%PDF") and info["bytes"] > 20_000
        assert pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages") >= 3  # summary, strips, full disclosure


def test_no_skin_contact_is_excluded():
    """An unworn H10 keeps streaming noise and an invented rate; contact=False periods must not count."""
    from openholter import simulator
    from openholter.analysis import ectopy
    original = simulator.SyntheticBody.in_off
    simulator.SyntheticBody.in_off = lambda self, t: 300 <= t < 500
    try:
        with tempfile.TemporaryDirectory() as d:
            sd = generate_night(Path(d), hours=0.25, start=datetime(2026, 1, 1, 23, 0), seed=9)
            s = assemble(sd)
    finally:
        simulator.SyntheticBody.in_off = original
    # the simulated night also has a BLE drop-out from 490 s, so the flagged period ends there
    assert len(s.no_contact) == 1 and abs(s.no_contact[0][0] - 300) < 3 and 485 < s.no_contact[0][1] < 502
    assert not np.any((s.rr_t > 302) & (s.rr_t < 498)) and not np.any((s.hr_t > 302) & (s.hr_t < 498))
    summ = summarize(s)
    assert summ["quality_windows"]["none"] >= 17 and 180 < summ["no_contact_s"] < 210
    assert all(not (302 < t < 498) for t in ectopy(s.rr_t, s.rr_ms, None, 0)["events"])


def test_ecg_beat_detection_and_morphology():
    """Premature beats found from the ECG itself, couplets included, simulated VES classified as VES."""
    import json
    from openholter.beats import classify_beats
    with tempfile.TemporaryDirectory() as d:
        sd = generate_night(Path(d), hours=1.0, start=datetime(2026, 1, 1, 23, 0), seed=12)
        s = assemble(sd)
        truth = np.array(json.loads((sd / "simulation_truth.json").read_text())["ves_times"])
    res = classify_beats(s.ecg_t, s.ecg_uv, s.ecg_fs, s.duration, s.no_contact)
    ev = np.array(res["events"])
    from openholter.sessions import gaps
    inner = truth[(truth > 61) & (truth < s.duration - 61)]
    for a, b in gaps(s.ecg_t, s.duration):  # simulated BLE drop-out: no ECG to find them in
        inner = inner[(inner < a - 3) | (inner > b + 3)]
    assert len(ev) > 20
    assert np.mean([np.min(np.abs(truth - x)) < 0.06 for x in ev]) > 0.98  # precision, R peaks within 60 ms
    assert np.mean([np.min(np.abs(ev - x)) < 0.06 for x in inner]) > 0.95  # sensitivity
    assert np.mean([x["kind"] == "ves" for x in res["details"]]) > 0.95
    assert not np.any(ev < 60) and not np.any(ev > s.duration - 60)  # strap on/off minutes ignored


def test_v5_sves_runs_af_and_late_ves():
    """Analysis v5 on a synthetic ECG: SVES without a full pause, an SVT run, an atrial
    fibrillation episode (no SVES inside, reported as an episode) and late, non-premature VES."""
    from openholter.analysis import ectopy_ecg
    from openholter.beats import classify_beats
    from openholter.simulator import SyntheticBody
    rng = np.random.default_rng(5)
    dur = 1200.0
    beats, sves, ves_late, run = [(0.5, "N")], [], [], []
    t = 0.5
    while t < dur + 5:
        rr = 1.0 * (1 + 0.04 * np.sin(2 * np.pi * 0.25 * t)) * (1 + rng.normal(0, 0.008))
        if 600 <= t < 780:  # atrial fibrillation: irregularly irregular, normal QRS, no P wave
            t += rng.uniform(0.5, 1.2)
            beats.append((t, "F"))
            continue
        k = len(beats)
        if 100 < t < 590 and k % 23 == 0:  # SVES: 30 % early, the next interval only a normal one (sinus reset)
            t += 0.7 * rr
            beats.append((t, "N"))
            sves.append(t)
            t += rr
            beats.append((t, "N"))
        elif abs(t - 400) < 0.6 and not run:  # SVT run of 6 beats at ~130/min
            for _ in range(6):
                t += 0.46
                beats.append((t, "N"))
                run.append(t)
            t += 1.0
            beats.append((t, "N"))
        elif 800 < t < 1130 and k % 31 == 0:  # late VES: not premature, wide and different
            t += 0.97 * rr
            beats.append((t, "V"))
            ves_late.append(t)
            t += 1.1 * rr
            beats.append((t, "N"))
        else:
            t += rr
            beats.append((t, "N"))
    body = SyntheticBody(seed=5, night=False)
    body.beats = beats
    fs = 130.0
    uv = body.ecg(0, int(dur * fs), fs).astype(float)
    tt = np.arange(len(uv)) / fs
    res = classify_beats(tt, uv, fs, dur, None)
    det = res["details"]
    st = np.array([d["t"] for d in det if d["kind"] == "sves"])
    vt = np.array([d["t"] for d in det if d["kind"] == "ves"])
    near = lambda a, x: len(a) > 0 and np.min(np.abs(a - x)) < 0.06
    sves_in = [x for x in sves if 61 < x < dur - 61]
    assert np.mean([near(st, x) for x in sves_in]) > 0.9  # v4 missed these: no pause > 105 %
    assert all(near(st, x) for x in run)
    assert any(r["beats"] == 6 and r["kind"] == "sves" and r["rate_bpm"] > 120 for r in res["runs"])
    assert len(res["runs"]) == 1
    af = res["af_episodes"]
    assert len(af) == 1 and af[0]["start"] < 620 and af[0]["end"] > 760
    assert not np.any((st > 600) & (st < 780))  # no SVES during AF
    late = [d for d in det if d["kind"] == "ves" and near(np.array(ves_late), d["t"])]
    assert len(late) >= 0.8 * len(ves_late) and not any(d["premature"] for d in late)
    truth = np.array(sves + run + ves_late)
    false = [d for d in det if not near(truth, d["t"])]
    assert len(false) <= 3, false
    ect = ectopy_ecg(tt, uv, fs, dur, None, None, 0)
    assert ect["af_episodes"] == af and ect["runs"] == res["runs"] and ect["af_seconds"] > 140
    assert ect["ves_morphology_only"] >= len(late)


def test_frequent_atrial_beats_are_not_af():
    """An irregular rhythm with P waves (frequent atrial extra beats) is not reported as AF, and its
    SVES are kept. This is what v5 got wrong: it took such recordings for atrial fibrillation."""
    from openholter.beats import classify_beats
    from openholter.simulator import SyntheticBody
    rng = np.random.default_rng(8)
    dur = 900.0
    beats, sves = [(0.5, "N")], []
    t = 0.5
    while t < dur + 5:
        rr = 1.0 + rng.normal(0, 0.01)
        if len(beats) > 3 and rng.random() < 0.3 and beats[-1][0] not in sves:
            t += rr * rng.uniform(0.6, 0.75)
            sves.append(t)
        else:
            t += rr
        beats.append((t, "N"))
    body = SyntheticBody(seed=8, night=False)
    body.beats = beats
    fs = 130.0
    uv = body.ecg(0, int(dur * fs), fs).astype(float)
    res = classify_beats(np.arange(len(uv)) / fs, uv, fs, dur, None)
    assert res["af_episodes"] == []
    st = np.array([d["t"] for d in res["details"] if d["kind"] == "sves"])
    inner = [x for x in sves if 61 < x < dur - 61]
    assert np.mean([len(st) > 0 and np.min(np.abs(st - x)) < 0.06 for x in inner]) > 0.8


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
