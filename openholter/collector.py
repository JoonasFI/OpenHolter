"""Acquisition: find the H10, stream ECG + ACC + HR, manage sessions, reconnect forever."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, Optional, Tuple

import numpy as np

from . import pmd
from . import posture as P
from .config import Config
from .live import LiveHub
from .power import SleepGuard
from .storage import TAG_HR, TAG_PMD, SessionWriter, list_session_dirs, read_meta, write_json_atomic

log = logging.getLogger(__name__)

OnData = Callable[[bytes], None]


CONTACT_STEADY_S = 10.0  # seconds of uninterrupted skin contact before a recording starts by itself


class LinkError(Exception):
    pass


class H10Link:
    """One BLE connection to a Polar H10 via bleak/CoreBluetooth."""

    def __init__(self, device: Any, cfg: Config):
        self.device = device
        self.cfg = cfg
        self.client = None
        self._cp_waiter: Optional[asyncio.Future] = None
        self._cp_buffer = b""
        self.info: Dict[str, Any] = {"name": getattr(device, "name", None), "address": getattr(device, "address", None)}

    @staticmethod
    async def find(cfg: Config, seen: Dict[str, Dict[str, Any]], timeout: float = 10.0) -> Optional[Any]:
        """Scan until the configured strap shows up; every Polar device heard goes into `seen`
        (for the settings page)."""
        from bleak import BleakScanner

        found: "asyncio.Future[Any]" = asyncio.get_running_loop().create_future()

        def on_adv(d: Any, ad: Any) -> None:
            name = d.name or ad.local_name or ""
            if "polar" in name.lower():
                seen[d.address] = {"name": name, "address": d.address, "rssi": ad.rssi, "last_seen": time.time()}
            if cfg.device_address:
                ok = d.address.lower() == cfg.device_address.lower()
            else:
                ok = name.startswith(cfg.device_name_prefix)
            if ok and not found.done():
                found.set_result(d)

        async with BleakScanner(detection_callback=on_adv):
            try:
                return await asyncio.wait_for(asyncio.shield(found), timeout)
            except asyncio.TimeoutError:
                return None

    async def open(self, on_pmd: OnData, on_hr: OnData, on_disconnect: Callable[[], None]) -> Dict[str, Any]:
        from bleak import BleakClient

        loop = asyncio.get_running_loop()
        self.client = BleakClient(self.device, disconnected_callback=lambda _c: loop.call_soon_threadsafe(on_disconnect))
        await self.client.connect(timeout=20.0)
        for key, uuid in (("model", "00002a24-0000-1000-8000-00805f9b34fb"),
                          ("firmware", "00002a26-0000-1000-8000-00805f9b34fb")):
            try:
                self.info[key] = bytes(await self.client.read_gatt_char(uuid)).decode(errors="replace").strip("\x00 ")
            except Exception:  # optional characteristics
                pass
        self.info["battery"] = await self.battery()
        try:
            self.info["features"] = pmd.parse_features(bytes(await self.client.read_gatt_char(pmd.PMD_CONTROL)))
        except Exception as e:
            raise LinkError(f"PMD service not available: {e}") from e

        await self.client.start_notify(pmd.PMD_CONTROL, self._on_control)
        await self.client.start_notify(pmd.PMD_DATA, lambda _c, d: on_pmd(bytes(d)))
        await self.client.start_notify(pmd.HR_MEASUREMENT, lambda _c, d: on_hr(bytes(d)))

        for m in (pmd.ECG, pmd.ACC):
            resp = await self._request(pmd.get_settings_command(m))
            if resp.ok:
                self.info[f"{pmd.MEASUREMENT_NAMES[m]}_available"] = pmd.parse_settings(resp.params)

        ecg = await self._request(pmd.start_ecg_command(self.cfg.ecg_sample_rate))
        if not ecg.ok and ecg.error != 6:  # 6 = already streaming
            raise LinkError(f"ECG start failed: {ecg.error_text}")
        acc = await self._request(pmd.start_acc_command(self.cfg.acc_sample_rate, 16, self.cfg.acc_range_g))
        if not acc.ok and acc.error != 6:
            log.warning("ACC start failed (%s); continuing with ECG only", acc.error_text)
            self.info["acc_error"] = acc.error_text
        return self.info

    async def battery(self) -> Optional[int]:
        try:
            return int(bytes(await self.client.read_gatt_char(pmd.BATTERY_LEVEL))[0])
        except Exception:
            return None

    async def rssi(self) -> Optional[int]:
        """Signal strength of the live connection (CoreBluetooth readRSSI; not in bleak's public API)."""
        try:
            return int(await self.client._backend.get_rssi())
        except Exception:
            return None

    def _on_control(self, _c: Any, data: bytearray) -> None:
        resp = pmd.parse_control_response(bytes(data))
        if resp is None:
            return
        self._cp_buffer += resp.params
        if resp.more:
            return
        resp.params, self._cp_buffer = self._cp_buffer, b""
        if self._cp_waiter and not self._cp_waiter.done():
            self._cp_waiter.set_result(resp)

    async def _request(self, cmd: bytes) -> pmd.ControlResponse:
        self._cp_waiter = asyncio.get_running_loop().create_future()
        self._cp_buffer = b""
        await self.client.write_gatt_char(pmd.PMD_CONTROL, cmd, response=True)
        try:
            return await asyncio.wait_for(self._cp_waiter, 5.0)
        except asyncio.TimeoutError as e:
            raise LinkError(f"no control point response to {cmd.hex()}") from e

    async def close(self) -> None:
        if self.client is None:
            return
        try:
            if self.client.is_connected:
                for m in (pmd.ECG, pmd.ACC):
                    try:
                        await self.client.write_gatt_char(pmd.PMD_CONTROL, pmd.stop_command(m), response=True)
                    except Exception:
                        pass
                await self.client.disconnect()
        except Exception as e:
            log.debug("disconnect error: %s", e)


class Collector:
    def __init__(self, cfg: Config, hub: LiveHub, link_factory: Optional[Callable[[], Any]] = None):
        self.cfg = cfg
        self.hub = hub
        self.sleep = SleepGuard()
        self.link_factory = link_factory  # simulator hook; None = real BLE
        self.state = "starting"
        self.detail = ""
        self.device: Dict[str, Any] = {}
        self.session: Optional[SessionWriter] = None
        self.auto_armed = True
        self.conn = -1
        self.connected_since: Optional[float] = None
        self.last_seen = time.monotonic()
        self.last_data = 0.0
        self.counts = {"ecg": 0, "acc": 0, "hr": 0}
        self.last_bpm: Optional[int] = None
        self._link: Any = None
        self._disconnected = asyncio.Event()
        self._wake = asyncio.Event()
        self._ecg_fs = float(cfg.ecg_sample_rate)
        self._last_ecg_ts: Optional[int] = None
        # last minute of raw ACC for calibration captures: (monotonic s, samples)
        self._acc_ring: Deque[Tuple[float, np.ndarray]] = deque(maxlen=200)
        self.calibrations = P.CalibrationStore(cfg.home)
        self.calibration: Optional[P.Calibration] = self.calibrations.latest()
        self.sim_body: Any = None  # set when running the simulator
        self.seen: Dict[str, Dict[str, Any]] = {}  # Polar devices heard while scanning
        # skin contact from the HR service: an unworn but connected H10 streams noise
        self.contact: Optional[bool] = None
        self.contact_since = time.monotonic()  # when `contact` last changed
        # an unworn strap that was let go is left alone until then, so it can sleep (see Config)
        self._rest_until = 0.0
        self._release_reason: Optional[str] = None
        # link quality: ECG samples received per notification over the last seconds
        self._arrivals: Deque[Tuple[float, int]] = deque(maxlen=600)
        self.rssi: Optional[int] = None
        self.link: Dict[str, Any] = {"level": "none"}

    # ------------------------------------------------------------------ public API

    def status(self) -> Dict[str, Any]:
        s = self.session
        return {
            "state": self.state,
            "detail": self.detail,
            "device": self.device,
            "connected_for": (time.monotonic() - self.connected_since) if self.connected_since else None,
            "recording": s is not None,
            "session_id": s.id if s else None,
            "session_started_wall_ns": s.started_wall_ns if s else None,
            "session_bytes": s.bytes_written if s else 0,
            "auto_armed": self.auto_armed,
            "auto_record": self.cfg.auto_record,
            "quality": self.hub.quality,
            "bpm": self.last_bpm,
            "contact": self.contact,
            "counts": self.counts,
            "simulated": self.link_factory is not None,
            "calibration_id": self.calibration.id if self.calibration else None,
            "sleep_prevented": self.sleep.active,
            "link": self.link,
        }

    def reconnect(self, reason: str) -> None:
        """Drop the current link; the main loop scans again with the current settings."""
        if self.state == "streaming":
            log.info("reconnecting: %s", reason)
            self._end_connection(reason)
            self._disconnected.set()

    def apply_sleep_policy(self) -> None:
        if self.cfg.prevent_sleep == "always" or (self.cfg.prevent_sleep == "recording" and self.session is not None):
            self.sleep.hold()
        else:
            self.sleep.release()

    def start_recording(self) -> Dict[str, Any]:
        self.auto_armed = True
        if self.session is None and self.state == "streaming":
            self._open_session(manual=True)
        self._publish()
        return self.status()

    def stop_recording(self) -> Dict[str, Any]:
        if self.session is not None:
            self._close_session("manual stop")
        # Stay disarmed until the strap goes away, otherwise we would restart immediately.
        self.auto_armed = False
        self._publish()
        return self.status()

    def live_posture(self, samples: np.ndarray) -> Tuple[Optional[str], Optional[Tuple[float, float]]]:
        """Posture class and (roll, pitch) for the live view; (None, None) without calibration."""
        if self.calibration is None or len(samples) == 0:
            return None, None
        g = samples.astype(np.float64)
        mag = np.linalg.norm(g, axis=1)
        u = g.mean(axis=0)
        u = u / max(np.linalg.norm(u), 1e-9)
        angles = self.calibration.angles(u)
        if mag.std() > P.MOVE_MAG_STD:
            return "moving", angles
        cls, _ = self.calibration.classify(u[None])
        return P.CLASS_NAMES[int(cls[0])], angles

    def reload_calibration(self) -> None:
        self.calibration = self.calibrations.latest()

    async def capture_acc(self, seconds: float) -> np.ndarray:
        """Collect raw ACC samples for the next `seconds` (calibration step)."""
        start = time.monotonic()
        await asyncio.sleep(seconds)
        parts = [s for t, s in list(self._acc_ring) if t >= start]
        return np.concatenate(parts) if parts else np.zeros((0, 3))

    # ------------------------------------------------------------------ main loop

    async def run(self) -> None:
        self._recover_sessions()
        if self.cfg.prevent_sleep == "always":
            self.sleep.hold()
        asyncio.get_running_loop().create_task(self._housekeeping())
        while True:
            try:
                self._set("scanning", f"etsitään {self.cfg.device_name_prefix}")
                link = await self._find()
                if link is None:
                    continue
                try:
                    await self._stream(link)
                finally:
                    await link.close()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("collector loop error")
                self._set("error", str(e))
                await asyncio.sleep(5)
            finally:
                self._after_disconnect()

    async def shutdown(self) -> None:
        if self._link is not None:
            await self._link.close()
        if self.session is not None:
            # Leave state "recording" on purpose: a quick restart resumes the same night.
            self.session.flush()
            self.session.save_meta()
        self.sleep.release()

    async def _find(self) -> Any:
        rest = self._rest_until - time.monotonic()
        if rest > 0:
            # don't reconnect right away: the strap still advertises for a moment after being let go
            self._set("scanning", "vyö lepää: ei ihokontaktia")
            await asyncio.sleep(min(5.0, rest))
            return None
        if self.link_factory is not None:
            await asyncio.sleep(1.0)
            now = time.time()
            # pretend a neighbour's strap is in range too, so locking can be tried out
            self.seen["simulated"] = {"name": "Polar H10 SIM00001", "address": "simulated", "rssi": -48, "last_seen": now}
            self.seen["sim-neighbour"] = {"name": "Polar H10 8A2C41D7", "address": "sim-neighbour", "rssi": -83, "last_seen": now}
            if self.cfg.device_address not in (None, "", "simulated"):
                await asyncio.sleep(4)
                return None
            return self.link_factory()
        device = await H10Link.find(self.cfg, self.seen)
        return H10Link(device, self.cfg) if device else None

    async def _stream(self, link: Any) -> None:
        self._set("connecting", "yhdistetään")
        self._link = link
        self._disconnected.clear()
        self._release_reason = None
        self._last_ecg_ts = None
        info = await link.open(self._on_pmd, self._on_hr, self._disconnected.set)
        self.device = {k: v for k, v in info.items() if not k.endswith("_available")}
        log.info("connected: %s", self.device)
        self.connected_since = time.monotonic()
        self.last_data = time.monotonic()
        self.last_seen = time.monotonic()
        self.hub.clear()
        self._set("streaming", "")
        self.contact = None
        self.contact_since = time.monotonic()
        # a new automatic recording starts from _on_hr once the strap reports skin contact;
        # a recording already running (reconnect, resumed after restart) continues here
        if self.session is not None:
            self._begin_connection()
        while not self._disconnected.is_set():
            try:
                await asyncio.wait_for(self._disconnected.wait(), 5.0)
            except asyncio.TimeoutError:
                pass
            self.last_seen = time.monotonic()
            if time.monotonic() - self.last_data > self.cfg.data_timeout_s:
                log.warning("no data for %.0f s, reconnecting", self.cfg.data_timeout_s)
                self._end_connection("data timeout")
                return
        self._end_connection(self._release_reason or "link lost")

    def _after_disconnect(self) -> None:
        if self.connected_since is not None:
            log.info("disconnected")
            # Strap removed or out of range: re-arm automatic recording.
            self.auto_armed = True
        self.connected_since = None
        self._link = None
        self.hub.clear()

    # ------------------------------------------------------------------ data callbacks

    def _on_pmd(self, data: bytes) -> None:
        wall, mono = time.time_ns(), time.monotonic_ns()
        self.last_data = time.monotonic()
        if self.session is not None:
            self.session.write(TAG_PMD, self.conn, data, wall, mono)
        try:
            frame = pmd.parse_frame(data)
        except ValueError as e:
            log.warning("bad PMD frame (%s): %s", e, data[:16].hex())
            return
        if frame.measurement == pmd.ECG:
            self.counts["ecg"] += len(frame.samples)
            self._arrivals.append((time.monotonic(), len(frame.samples)))
            if self._last_ecg_ts is not None and frame.sensor_ts_ns > self._last_ecg_ts:
                fs = len(frame.samples) * 1e9 / (frame.sensor_ts_ns - self._last_ecg_ts)
                if abs(fs / self.cfg.ecg_sample_rate - 1) < 0.1:
                    self._ecg_fs = 0.98 * self._ecg_fs + 0.02 * fs
            self._last_ecg_ts = frame.sensor_ts_ns
            self.hub.ecg(frame.samples, round(self._ecg_fs, 3))
        elif frame.measurement == pmd.ACC:
            self.counts["acc"] += len(frame.samples)
            self._acc_ring.append((time.monotonic(), frame.samples))
            self.hub.acc(frame.samples, *self.live_posture(frame.samples))

    def _on_hr(self, data: bytes) -> None:
        wall, mono = time.time_ns(), time.monotonic_ns()
        if self.session is not None:
            self.session.write(TAG_HR, self.conn, data, wall, mono)
        try:
            hr = pmd.parse_heart_rate(data)
        except (IndexError, ValueError):
            return
        self.counts["hr"] += 1
        on_skin = hr.contact is not False  # None = strap doesn't report contact: assume worn
        if on_skin != self.contact:
            self.contact, self.contact_since = on_skin, time.monotonic()
            log.info("skin contact %s", "on" if on_skin else "off")
            if not on_skin:
                self.auto_armed = True  # strap taken off: the next time it is worn starts a recording
            self._publish()
        self.last_bpm = hr.bpm if on_skin else None
        self.hub.heart_rate(hr.bpm, hr.rr_ms, hr.contact)
        # require steady contact: right after connecting the H10 can report contact for a single
        # notification even when it is lying on the table
        if (on_skin and self.session is None and self.cfg.auto_record and self.auto_armed and self.state == "streaming"
                and time.monotonic() - self.contact_since >= CONTACT_STEADY_S):
            self._open_session(manual=False)

    # ------------------------------------------------------------------ sessions

    def _settings(self) -> Dict[str, Any]:
        return {"ecg_sample_rate": self.cfg.ecg_sample_rate, "acc_sample_rate": self.cfg.acc_sample_rate,
                "acc_range_g": self.cfg.acc_range_g, "acc_resolution": 16}

    def _open_session(self, manual: bool) -> None:
        self.session = SessionWriter(self.cfg.sessions_dir, dict(self.device), self._settings(), manual)
        log.info("session %s started (%s)", self.session.id, "manual" if manual else "auto")
        if self.cfg.prevent_sleep == "recording":
            self.sleep.hold()
        if self.state == "streaming":
            self._begin_connection()
        self._publish()

    def _begin_connection(self) -> None:
        assert self.session is not None
        self.conn = self.session.next_conn
        self.session.connection_started(self.conn, self.device)

    def _end_connection(self, reason: str) -> None:
        if self.session is not None and self.conn >= 0:
            self.session.connection_ended(self.conn, reason)
        self._set("scanning", reason)

    def _close_session(self, reason: str) -> None:
        if self.session is None:
            return
        log.info("session %s closed: %s", self.session.id, reason)
        self.session.close(reason)
        self.session = None
        self.conn = -1
        if self.cfg.prevent_sleep == "recording":
            self.sleep.release()

    def _check_timeout(self) -> None:
        if self.session is None:
            return
        idle = time.monotonic() - self.last_seen
        if idle > self.cfg.session_timeout_min * 60:
            self._close_session(f"strap not seen for {self.cfg.session_timeout_min:g} min")
            self._publish()

    def _recover_sessions(self) -> None:
        """Resume a session interrupted by a crash/restart, close older ones."""
        now = time.time()
        for d in list_session_dirs(self.cfg.sessions_dir):
            meta = read_meta(d)
            if not meta or meta.get("state") != "recording":
                continue
            chunks = [d / c for c in meta.get("chunks", []) if (d / c).exists()]
            last_write = max((c.stat().st_mtime for c in chunks), default=0)
            if self.session is None and now - last_write < self.cfg.session_timeout_min * 60:
                self.session = SessionWriter.resume(d, meta)
                log.info("resumed session %s", meta["id"])
            else:
                meta["state"] = "closed"
                meta["end_reason"] = "interrupted (app stopped)"
                meta["ended_wall_ns"] = int(last_write * 1e9) if last_write else meta["started_wall_ns"]
                from datetime import datetime
                meta["ended_at"] = datetime.fromtimestamp(meta["ended_wall_ns"] / 1e9).astimezone().isoformat(timespec="seconds")
                write_json_atomic(d / "meta.json", meta)
                log.info("closed interrupted session %s", meta["id"])

    # ------------------------------------------------------------------ misc

    async def _housekeeping(self) -> None:
        tick = 0
        while True:
            await asyncio.sleep(1.0)
            tick += 1
            if self.session is not None and tick % 2 == 0:
                self.session.flush()
            if self.state != "streaming" and tick % 10 == 0:
                self._check_timeout()
            if (self.session is not None and self.contact is False and not self.session.meta.get("manual_start")
                    and time.monotonic() - self.contact_since > self.cfg.session_timeout_min * 60):
                # strap taken off but still connected: end the night, start again when worn
                self._close_session(f"no skin contact for {self.cfg.session_timeout_min:g} min")
                self.auto_armed = True
                self._publish()
            if (self.cfg.release_unworn_s > 0 and self.state == "streaming" and self.session is None
                    and self.contact is False and time.monotonic() - self.contact_since > self.cfg.release_unworn_s):
                # nobody wears it and nothing is being recorded: let it go so it can sleep
                log.info("strap not worn for %.0f s and not recording: letting it go to save its battery",
                         self.cfg.release_unworn_s)
                self._rest_until = time.monotonic() + self.cfg.rest_after_release_s
                self._release_reason = "vyö vapautettu: ei ihokontaktia"
                self._disconnected.set()
            if self.state == "streaming" and self._link is not None and tick % 3 == 0:
                self.rssi = await self._link.rssi()
            self._update_link()
            if tick % 300 == 0 and self._link is not None and self.state == "streaming":
                battery = await self._link.battery()
                if battery is not None:
                    self.device["battery"] = battery
            self._publish()

    def _update_link(self) -> None:
        """Bluetooth link level from data actually arriving (what gets recorded) and RSSI."""
        now = time.monotonic()
        if self.state != "streaming" or self.connected_since is None:
            self.link = {"level": "none"}
            self.rssi = None
            return
        window = min(10.0, now - self.connected_since)
        if window < 3:
            self.link = {"level": "wait", "rssi": self.rssi}
            return
        recent = [(t, n) for t, n in self._arrivals if t >= now - window]
        received = sum(n for _, n in recent)
        ratio = received / (self._ecg_fs * window)
        times = [t for t, _ in recent] + [now]
        gap = max((b - a for a, b in zip(times[:-1], times[1:])), default=window) if len(times) > 1 else window
        r = self.rssi
        if ratio >= 0.97 and gap < 1.5 and (r is None or r > -78):
            level = "good"
        elif ratio >= 0.9 and gap < 3.0 and (r is None or r > -88):
            level = "fair"
        else:
            level = "poor"
        self.link = {"level": level, "rssi": r, "ratio": round(min(ratio, 1.0), 3), "gap": round(gap, 2)}

    def _set(self, state: str, detail: str) -> None:
        if state != self.state or detail != self.detail:
            log.info("state %s %s", state, detail)
        self.state, self.detail = state, detail
        self._publish()

    def _publish(self) -> None:
        self.hub.set_status(self.status())
