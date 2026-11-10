"""FastAPI app: REST for sessions, WebSocket for the live stream, static frontend."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict

from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, build_id
from . import posture as P
from .analysis import Analyzer, compute_beats, read_beats, read_result
from .storage import read_meta, write_json_atomic
from .trash import Trash
from .collector import Collector
from .config import Config
from .i18n import LANG, LangMiddleware, tr
from .live import LiveHub
from .sessions import SessionStore, ecg_window, gaps, hr_series, posture_preview, public_meta, rr_window, summarize

STATIC = Path(__file__).parent / "static"


PBKDF2_ITERATIONS = 300_000  # pbkdf2 is in every Python build; scrypt is missing with LibreSSL


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${h.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _algo, iterations, salt, digest = stored.split("$")
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(h.hex(), digest)
    except ValueError:
        return False


class RevalidatingStatic(StaticFiles):
    """Browsers must revalidate (cheap 304) so an update never leaves old JS running."""

    def file_response(self, *args: Any, **kwargs: Any):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


class BasicAuth:
    """ASGI middleware covering both HTTP and WebSocket. Disabled when no password is set."""

    def __init__(self, app: Any, cfg: Config):
        self.app = app
        self.cfg = cfg
        self._ok: set = set()  # cache verified header values; PBKDF2 is deliberately slow

    def _authorized(self, scope: Dict[str, Any]) -> bool:
        if not self.cfg.auth.password_hash:
            return True
        header = dict(scope.get("headers") or []).get(b"authorization", b"")
        if header in self._ok:
            return True
        if not header.lower().startswith(b"basic "):
            return False
        try:
            user, _, pw = base64.b64decode(header[6:]).decode().partition(":")
        except ValueError:
            return False
        if hmac.compare_digest(user, self.cfg.auth.username) and check_password(pw, self.cfg.auth.password_hash):
            self._ok.add(header)
            return True
        return False

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket") and not self._authorized(scope):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4401})
                return
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"www-authenticate", b'Basic realm="OpenHolter"'), (b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"Authentication required"})
            return
        await self.app(scope, receive, send)


def create_app(cfg: Config, collector: Collector, hub: LiveHub, analyzer: Analyzer) -> Any:
    app = FastAPI(title="OpenHolter", version=__version__, docs_url=None, redoc_url=None)
    store = SessionStore(cfg.sessions_dir)
    trash = Trash(cfg.home, cfg.sessions_dir)

    @app.get("/api/status")
    def status() -> Dict[str, Any]:
        return {**collector.status(), "version": __version__, "build": build_id()}

    @app.post("/api/recording/start")
    def start() -> Dict[str, Any]:
        return collector.start_recording()

    @app.post("/api/recording/stop")
    def stop() -> Dict[str, Any]:
        return collector.stop_recording()

    @app.get("/api/sessions")
    def sessions() -> Any:
        out = store.list()
        for row in out:
            d = store.dir(row["meta"]["id"])
            row["analysis"] = analyzer.status(d, row["meta"])
            res = read_result(d)
            if res:
                row["analysis"]["hrv_rmssd"] = (res.get("hrv") or {}).get("rmssd_median")
        return out

    @app.get("/api/trends")
    def trends() -> Any:
        """One point per analysed recording, oldest first, for the trend chart."""
        from .storage import list_session_dirs
        out = []
        for d in reversed(list_session_dirs(cfg.sessions_dir)):
            res = read_result(d)
            meta = read_meta(d) or {}
            if not res or meta.get("state") != "closed":
                continue
            sm, ect, hrv, pos = res.get("summary") or {}, (res.get("ectopy") or res.get("ectopy_rr") or {}), res.get("hrv") or {}, res.get("posture") or {}
            dur = sm.get("duration_s") or 0
            out.append({
                "id": d.name, "start_wall_ns": meta.get("started_wall_ns"), "duration_s": dur,
                "ectopy_share": ect.get("share"), "ectopy_per_hour": (ect.get("count", 0) / (dur / 3600)) if dur else None,
                "ectopy_by_posture": {k: {"share": v["share"], "per_hour": v["per_hour"]}
                                      for k, v in (ect.get("by_posture") or {}).items() if k in P.LYING},
                "posture_share": pos.get("share_of_lying") if pos.get("calibrated") else None,
                "rmssd": hrv.get("rmssd_median"), "hr_mean": sm.get("hr_mean"), "quality": sm.get("quality_score"),
                "symptoms": sum(1 for e in meta.get("events", []) if e.get("kind") == "symptom"),
            })
        return out

    def _get(session_id: str):
        try:
            return store.get(session_id)
        except KeyError:
            raise HTTPException(404, "no such session")

    @app.get("/api/sessions/{session_id}")
    def session(session_id: str, points: int = Query(720, ge=50, le=4000)) -> Any:
        s = _get(session_id)
        summary = store.summary(session_id) if s.meta.get("state") == "closed" else summarize(s)
        # HR arrives once a second; finer buckets would leave the line full of holes.
        coarse = int(max(20, min(points, s.duration / 2)))
        d = store.dir(session_id)
        cal, how = analyzer.calibrations.for_session(d, s.meta)
        if cal is not None:
            track = P.classify_night(P.per_second(s.acc_t, s.acc_mg, s.duration), cal)
            posture = {"calibrated": True, "classes": P.bucket_classes(track["cls"], coarse),
                       "seconds": P.time_per_class(track["cls"]), "warnings": track["warnings"],
                       "calibration": {**cal.to_json(), "how": how}}
        else:
            posture = {**posture_preview(s, coarse), "calibrated": False}
        return {
            "meta": public_meta(s.meta),
            "summary": summary,
            "duration": s.duration,
            "ecg_fs": s.ecg_fs,
            "gaps": gaps(s.ecg_t, s.duration),
            "hr": hr_series(s, coarse),
            "posture": posture,
            "analysis": {"status": analyzer.status(d, s.meta), "result": read_result(d)},
            "calibrations": [{"id": c.id, "created_at": c.to_json()["created_at"], "source": c.source,
                              "postures": sorted(c.refs)} for c in reversed(analyzer.calibrations.all())],
        }

    def _dir(session_id: str):
        try:
            return store.dir(session_id)
        except KeyError:
            raise HTTPException(404, "no such session")

    # ---------------------------------------------------------------- calibration

    @app.get("/api/calibrations")
    def calibrations() -> Any:
        return [c.to_json() for c in reversed(analyzer.calibrations.all())]

    @app.post("/api/calibration/capture")
    async def capture(posture: str = Query(...), seconds: float = Query(15.0, ge=5, le=60)) -> Any:
        if posture not in P.LYING:
            raise HTTPException(400, "unknown posture")
        if collector.state != "streaming":
            raise HTTPException(409, tr("Vyö ei ole yhdistettynä.", "The strap is not connected."))
        samples = await collector.capture_acc(seconds)
        return {"posture": posture, **P.measure(samples)}

    @app.post("/api/calibrations")
    def create_calibration(payload: Dict[str, Any] = Body(...)) -> Any:
        refs = payload.get("refs") or {}
        if not {"supine", "left"} <= set(refs):
            raise HTTPException(400, tr("Selällään ja vasen kylki tarvitaan.", "Supine and left side are required."))
        try:
            cal = analyzer.calibrations.create({k: v for k, v in refs.items() if k in P.LYING}, "live",
                                               payload.get("measurements"))
        except ValueError as e:
            raise HTTPException(400, str(e))
        collector.reload_calibration()
        return cal.to_json()

    @app.put("/api/sessions/{session_id}/calibration")
    def choose_calibration(session_id: str, payload: Dict[str, Any] = Body(...)) -> Any:
        d = _dir(session_id)
        cal_id = payload.get("calibration_id")
        if cal_id is not None and analyzer.calibrations.get(cal_id) is None:
            raise HTTPException(404, "no such calibration")
        P.set_choice(d, cal_id)
        analyzer.request(session_id)
        return {"ok": True}

    @app.post("/api/sessions/{session_id}/calibration-from-segments")
    def calibrate_from_night(session_id: str, payload: Dict[str, Any] = Body(...)) -> Any:
        s = _get(session_id)
        segments = [x for x in payload.get("segments", []) if x.get("posture") in P.LYING]
        refs, info = P.refs_from_segments(P.per_second(s.acc_t, s.acc_mg, s.duration), segments)
        if not {"supine", "left"} <= set(refs):
            raise HTTPException(400, tr("Merkitse ainakin yksi selällään- ja yksi vasen kylki -jakso, joiden aikana olit paikallasi.", "Mark at least one supine and one left-side span during which you lay still."))
        try:
            cal = analyzer.calibrations.create(refs, f"session:{session_id}", {"segments": segments, "info": info})
        except ValueError as e:
            raise HTTPException(400, str(e))
        P.set_choice(_dir(session_id), cal.id)
        analyzer.request(session_id)
        collector.reload_calibration()
        return cal.to_json()

    # ---------------------------------------------------------------- analysis

    @app.get("/api/sessions/{session_id}/analysis")
    def analysis(session_id: str) -> Any:
        d = _dir(session_id)
        from .storage import read_meta
        return {"status": analyzer.status(d, read_meta(d) or {}), "result": read_result(d)}

    @app.post("/api/sessions/{session_id}/analyze")
    def analyze(session_id: str) -> Any:
        _dir(session_id)
        analyzer.request(session_id)
        return {"queued": True}

    @app.post("/api/analyze-all")
    def analyze_all() -> Any:
        return {"queued": analyzer.request_all(only_needed=False)}

    # ---------------------------------------------------------------- settings

    EDITABLE = {
        "device_name_prefix": str, "device_address": (str, type(None)),
        "session_timeout_min": (int, float), "data_timeout_s": (int, float),
        "prevent_sleep": str, "analysis_time": str,
        "acc_sample_rate": int, "acc_range_g": int, "auto_record": bool,
    }

    def _validate(key: str, value: Any) -> Any:
        if EDITABLE[key] is bool:
            if not isinstance(value, bool):
                raise HTTPException(400, f"{key}: " + tr("väärä tyyppi", "wrong type"))
            return value
        if not isinstance(value, EDITABLE[key]) or isinstance(value, bool):
            raise HTTPException(400, f"{key}: " + tr("väärä tyyppi", "wrong type"))
        if key == "prevent_sleep" and value not in ("always", "recording", "never"):
            raise HTTPException(400, "prevent_sleep: always / recording / never")
        if key == "analysis_time" and value:
            try:
                hh, mm = (int(x) for x in value.split(":"))
                assert 0 <= hh < 24 and 0 <= mm < 60
            except (ValueError, AssertionError):
                raise HTTPException(400, tr("Anna aika muodossa HH:MM", "Give the time as HH:MM"))
            value = f"{hh:02d}:{mm:02d}"
        if key == "session_timeout_min" and not 1 <= value <= 180:
            raise HTTPException(400, tr("Aikakatkaisu 1–180 min", "Timeout 1–180 min"))
        if key == "data_timeout_s" and not 5 <= value <= 120:
            raise HTTPException(400, tr("Datan aikakatkaisu 5–120 s", "Data timeout 5–120 s"))
        if key == "acc_sample_rate" and value not in (25, 50, 100, 200):
            raise HTTPException(400, tr("H10 tukee 25, 50, 100 tai 200 Hz", "The H10 supports 25, 50, 100 or 200 Hz"))
        if key == "acc_range_g" and value not in (2, 4, 8):
            raise HTTPException(400, tr("H10 tukee ±2, ±4 tai ±8 G", "The H10 supports ±2, ±4 or ±8 G"))
        if key == "device_name_prefix" and not value.strip():
            raise HTTPException(400, tr("Nimen alku ei voi olla tyhjä", "The name prefix cannot be empty"))
        if key == "device_address" and value == "":
            value = None
        return value

    def _disk() -> Dict[str, Any]:
        import shutil
        total = sum(p.stat().st_size for p in cfg.sessions_dir.rglob("*") if p.is_file())
        free = shutil.disk_usage(cfg.home).free
        n = sum(1 for p in cfg.sessions_dir.iterdir() if (p / "meta.json").exists())
        return {"sessions": n, "bytes": total, "free_bytes": free, "path": str(cfg.home)}

    @app.get("/api/settings")
    def get_settings() -> Any:
        now = time.time()
        seen = sorted((dict(v, ago=round(now - v["last_seen"])) for v in collector.seen.values()
                       if now - v["last_seen"] < 600), key=lambda v: -(v.get("rssi") or -999))
        return {
            "config": {k: getattr(cfg, k) for k in EDITABLE},
            "readonly": {"port": cfg.port, "host": cfg.host, "ecg_sample_rate": cfg.ecg_sample_rate,
                         "auth_enabled": bool(cfg.auth.password_hash), "auth_username": cfg.auth.username},
            "device": collector.device if collector.state == "streaming" else None,
            "state": collector.state,
            "seen": seen,
            "calibrations": [c.to_json() for c in reversed(analyzer.calibrations.all())],
            "disk": _disk(),
            "version": __version__,
            "build": build_id(),
            "simulated": collector.link_factory is not None,
        }

    @app.put("/api/settings")
    def put_settings(payload: Dict[str, Any] = Body(...)) -> Any:
        changes = {k: _validate(k, v) for k, v in payload.items() if k in EDITABLE}
        reconnect = False
        for k, v in changes.items():
            if getattr(cfg, k) != v and k in ("device_address", "device_name_prefix", "acc_sample_rate", "acc_range_g"):
                reconnect = True
            setattr(cfg, k, v)
        if "prevent_sleep" in changes:
            collector.apply_sleep_policy()
        cfg.save()
        if reconnect:
            # a different strap or ACC settings take effect on a fresh connection
            locked_elsewhere = cfg.device_address and collector.device.get("address") != cfg.device_address
            if locked_elsewhere or "acc_sample_rate" in changes or "acc_range_g" in changes or "device_name_prefix" in changes:
                collector.reconnect("settings changed")
        return get_settings()

    # ---------------------------------------------------------------- PDF report

    report_pool: Dict[str, Any] = {}

    @app.get("/api/sessions/{session_id}/report.pdf")
    async def report_pdf(session_id: str, inline: bool = False) -> Any:
        d = _dir(session_id)
        if collector.session is not None and collector.session.id == session_id:
            raise HTTPException(409, tr("Raportin voi tehdä, kun tallennus on päättynyt.", "The report can be made once the recording has ended."))
        import multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor

        from .analysis import _lower_priority
        from .report import build_report
        if "pool" not in report_pool:
            report_pool["pool"] = ProcessPoolExecutor(1, mp_context=mp.get_context("spawn"), initializer=_lower_priority)
        try:
            info = await asyncio.get_running_loop().run_in_executor(report_pool["pool"], build_report, str(d), str(cfg.home), LANG.get())
        except Exception:
            report_pool.pop("pool", None)
            raise
        start = (read_meta(d) or {}).get("started_at", session_id)[:10]
        return FileResponse(info["path"], media_type="application/pdf", filename=f"openholter-{tr('ekg', 'ecg')}-{start}.pdf",
                            content_disposition_type="inline" if inline else "attachment",
                            headers={"Cache-Control": "no-store"})

    # ---------------------------------------------------------------- symptom markers

    @app.post("/api/events")
    def add_event(payload: Dict[str, Any] = Body(default={})) -> Any:
        """'I felt an extra beat' from the Live view; stored in the running recording."""
        if collector.session is None:
            raise HTTPException(409, tr("Tallennus ei ole käynnissä, joten merkintää ei voi tallentaa.", "No recording is running, so the mark cannot be saved."))
        note = str(payload.get("note") or "")[:200]
        ev = collector.session.event("symptom", note=note) if note else collector.session.event("symptom")
        return {"session_id": collector.session.id, "event": ev}

    @app.delete("/api/sessions/{session_id}/events/{event_id}")
    def delete_event(session_id: str, event_id: str) -> Any:
        d = _dir(session_id)
        live = collector.session is not None and collector.session.id == session_id
        meta = collector.session.meta if live else (read_meta(d) or {})
        before = len(meta.get("events", []))
        meta["events"] = [e for e in meta.get("events", []) if e.get("id") != event_id]
        if len(meta["events"]) == before:
            raise HTTPException(404, "no such event")
        if live:
            collector.session.save_meta()  # the writer owns meta.json while recording
        else:
            write_json_atomic(d / "meta.json", meta)
        store.forget(session_id)
        return {"deleted": event_id}

    # ---------------------------------------------------------------- delete / trash

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: str) -> Any:
        d = _dir(session_id)
        if collector.session is not None and collector.session.id == session_id:
            raise HTTPException(409, tr("Tallennus on käynnissä. Lopeta tallennus ennen poistamista.", "A recording is running. Stop it before deleting."))
        if analyzer.running == session_id:
            raise HTTPException(409, tr("Tallennetta analysoidaan juuri. Yritä hetken päästä uudelleen.", "The recording is being analysed. Try again in a moment."))
        if session_id in analyzer.queue:
            analyzer.queue.remove(session_id)
        store.forget(session_id)
        name = trash.move_in(d)
        return {"trashed": name, "retention_days": 30}

    @app.get("/api/trash")
    def trash_list() -> Any:
        return trash.list()

    @app.post("/api/trash/{name}/restore")
    def trash_restore(name: str) -> Any:
        try:
            return {"restored": trash.restore(name)}
        except KeyError:
            raise HTTPException(404, "not in trash")
        except FileExistsError:
            raise HTTPException(409, tr("Samanniminen tallenne on jo olemassa.", "A recording with the same name already exists."))

    @app.delete("/api/trash/{name}")
    def trash_purge(name: str) -> Any:
        try:
            trash.purge(name)
        except KeyError:
            raise HTTPException(404, "not in trash")
        return {"purged": name}

    @app.delete("/api/trash")
    def trash_empty() -> Any:
        items = trash.list()
        for e in items:
            trash.purge(e["name"])
        return {"purged": len(items)}

    @app.post("/api/sim/contact")
    def sim_contact(payload: Dict[str, Any] = Body(...)) -> Any:
        if collector.sim_body is None:
            raise HTTPException(404, "not simulated")
        collector.sim_body.skin_off = not bool(payload.get("on", True))
        return {"on": not collector.sim_body.skin_off}

    @app.post("/api/sim/posture")
    def sim_posture(payload: Dict[str, Any] = Body(...)) -> Any:
        if collector.sim_body is None:
            raise HTTPException(404, "not simulated")
        p = payload.get("posture")
        collector.sim_body.override = p if p in P.POSTURES else None
        return {"posture": collector.sim_body.override}

    beats_lock = threading.Lock()

    @app.get("/api/sessions/{session_id}/beats")
    def beats(session_id: str) -> Any:
        """Every R peak (ms from the start). Saved by the analysis; recordings analysed before that
        get it computed once here with the same detector."""
        s = _get(session_id)
        d = store.dir(session_id)
        b = read_beats(d)
        if b is None:
            if s.meta.get("state") != "closed" or read_result(d) is None:
                raise HTTPException(409, tr("Tallennetta ei ole vielä analysoitu.", "The recording has not been analysed yet."))
            with beats_lock:  # one computation at a time; a second request finds the file
                b = read_beats(d) or compute_beats(d)
        return b

    templates_lock = threading.Lock()

    @app.get("/api/sessions/{session_id}/templates")
    def templates(session_id: str) -> Any:
        """Beats grouped by QRS shape (median waveform, examples, beat times), computed once and cached."""
        from .templates import compute_templates, read_templates
        s = _get(session_id)
        d = store.dir(session_id)
        tp = read_templates(d)
        if tp is None:
            if s.meta.get("state") != "closed" or read_result(d) is None:
                raise HTTPException(409, tr("Tallennetta ei ole vielä analysoitu.", "The recording has not been analysed yet."))
            with templates_lock:
                tp = read_templates(d) or compute_templates(d)
        return tp

    @app.get("/api/sessions/{session_id}/orientation")
    def orientation(session_id: str) -> Any:
        s = _get(session_id)
        cal, _ = analyzer.calibrations.for_session(store.dir(session_id), s.meta)
        if cal is None:
            return {"calibrated": False}
        return {"calibrated": True, **P.orientation_track(P.per_second(s.acc_t, s.acc_mg, s.duration), cal)}

    @app.get("/api/sessions/{session_id}/ecg")
    def ecg(session_id: str, start: float = 0.0, end: float = 10.0, points: int = Query(1500, ge=50, le=6000)) -> Any:
        return ecg_window(_get(session_id), start, end, points)

    @app.get("/api/sessions/{session_id}/rr")
    def rr(session_id: str, start: float = 0.0, end: float = 60.0) -> Any:
        return rr_window(_get(session_id), start, end)

    @app.websocket("/ws/live")
    async def live(ws: WebSocket) -> None:
        await ws.accept()
        q = hub.subscribe()
        try:
            while True:
                msg = await q.get()
                await ws.send_json(msg)
        except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
            pass
        finally:
            hub.unsubscribe(q)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", RevalidatingStatic(directory=STATIC), name="static")

    @app.exception_handler(Exception)
    async def errors(_req, exc):  # keep stack traces in the log, not in the browser
        import logging
        logging.getLogger(__name__).exception("request failed")
        return JSONResponse({"detail": "internal error"}, status_code=500)

    return LangMiddleware(BasicAuth(app, cfg))
