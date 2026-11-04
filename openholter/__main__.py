"""Command line: python -m openholter <command>."""
from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import logging.handlers
import os
import signal
import sys
import time
from pathlib import Path

from .config import load_config


def setup_logging(cfg, verbose: bool = False) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fh = logging.handlers.RotatingFileHandler(cfg.logs_dir / "openholter.log", maxBytes=5_000_000, backupCount=5)
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if not (os.environ.get("OPENHOLTER_NO_STDERR") or os.environ.get("HEARTH_NO_STDERR")):  # under launchd the rotating file is enough
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    logging.getLogger("bleak").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


async def _run(cfg, simulate: bool) -> None:
    import uvicorn

    from .collector import Collector
    from .live import LiveHub
    from .server import create_app

    # Analysis workers are spawned processes that read the cwd; make it one we always own.
    os.chdir(cfg.home)
    hub = LiveHub()
    factory = None
    if simulate:
        from .simulator import SimLink, SyntheticBody
        body = SyntheticBody(seed=int(time.time()) % 1000, night=False)
        factory = lambda: SimLink(body, cfg.acc_sample_rate)
    collector = Collector(cfg, hub, link_factory=factory)
    if simulate:
        collector.sim_body = body
        collector.sleep.hold = lambda: None  # don't keep a development machine awake (config untouched)
    from .analysis import Analyzer
    analyzer = Analyzer(cfg, collector)
    app = create_app(cfg, collector, hub, analyzer)
    server = uvicorn.Server(uvicorn.Config(app, host=cfg.host, port=cfg.port, log_config=None, ws="websockets"))
    server.install_signal_handlers = lambda: None  # handled below
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    tasks = [loop.create_task(collector.run()), loop.create_task(server.serve()), loop.create_task(analyzer.run())]
    logging.getLogger("openholter").info("OpenHolter on http://%s:%s %s", cfg.host, cfg.port, "(simulator)" if simulate else "")
    await stop.wait()
    server.should_exit = True
    await collector.shutdown()
    analyzer.shutdown()
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def _probe(cfg, seconds: float) -> None:
    """Stage 1: connect, print what the strap supports and stream ECG to the console."""
    from . import pmd
    from .collector import H10Link

    print(f"Etsitään laitetta '{cfg.device_name_prefix}'… (pue vyö ja kostuta elektrodit)")
    seen: dict = {}
    dev = await H10Link.find(cfg, seen, timeout=20)
    if not dev:
        print("Laitetta ei löytynyt.")
        return
    print(f"Löytyi: {dev.name}  {dev.address}")
    link = H10Link(dev, cfg)
    stats = {"ecg": 0, "acc": 0, "frames": 0}
    t_start = time.monotonic()

    def on_pmd(data: bytes) -> None:
        f = pmd.parse_frame(data)
        stats["frames"] += 1
        name = pmd.MEASUREMENT_NAMES[f.measurement]
        stats[name] = stats.get(name, 0) + len(f.samples)
        if f.measurement == pmd.ECG:
            v = f.samples
            print(f"ECG ts={f.sensor_ts_ns} n={len(v):3d} µV min={v.min():6d} max={v.max():6d}  {v[:6].tolist()}")
        else:
            print(f"ACC ts={f.sensor_ts_ns} n={len(f.samples):3d} mG mean={f.samples.mean(axis=0).round(0).tolist()}")

    def on_hr(data: bytes) -> None:
        hr = pmd.parse_heart_rate(data)
        print(f"HR  {hr.bpm} bpm  RR={[round(r) for r in hr.rr_ms]} ms  contact={hr.contact}")

    try:
        info = await link.open(on_pmd, on_hr, lambda: print("Yhteys katkesi"))
        for k, v in info.items():
            print(f"  {k}: {v}")
        await asyncio.sleep(seconds)
    finally:
        await link.close()
    el = time.monotonic() - t_start
    print(f"\n{el:.1f} s: ECG {stats['ecg']} näytettä ({stats['ecg'] / max(seconds, 1):.1f}/s), "
          f"ACC {stats['acc']} ({stats['acc'] / max(seconds, 1):.1f}/s), {stats['frames']} kehystä")


def _doctor(cfg) -> None:
    print(f"OpenHolter home:      {cfg.home}")
    print(f"Python:           {sys.version.split()[0]}")
    print(f"sys.executable:   {sys.executable}")
    print(f"real executable:  {os.path.realpath(sys.executable)}")
    base = getattr(sys, "_base_executable", None)
    if base:
        print(f"base executable:  {os.path.realpath(base)}")
    app = os.path.realpath(sys.executable)
    # python.org: …/Python.framework/Versions/X/, Apple's developer tools: …/Python3.framework/Versions/X/
    fw = app.split("/bin/")[0] if ".framework/Versions/" in app else None
    if fw and os.path.isdir(f"{fw}/Resources/Python.app"):
        print(f"Python.app:       {fw}/Resources/Python.app  <- Bluetooth-oikeus kirjautuu tälle")
    try:
        from CoreBluetooth import CBManager  # type: ignore
        states = {0: "ei vielä kysytty", 1: "rajoitettu", 2: "EVÄTTY", 3: "sallittu"}
        print(f"Bluetooth-oikeus: {states.get(int(CBManager.authorization()), '?')}")
    except Exception as e:
        print(f"Bluetooth-oikeus: ei voitu tarkistaa ({e})")
    print(f"Basic auth:       {'päällä' if cfg.auth.password_hash else 'POIS (aja set-password)'}")


def main() -> None:
    p = argparse.ArgumentParser(prog="openholter", description="EKG-tallennin Polar H10:lle")
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="keräin + web-käyttöliittymä (oletus)")
    r.add_argument("--simulate", action="store_true", help="käytä simuloitua H10:tä")
    r.add_argument("--port", type=int)
    r.add_argument("-v", "--verbose", action="store_true")
    pr = sub.add_parser("probe", help="vaihe 1: yhdistä ja tulosta EKG konsoliin")
    pr.add_argument("--seconds", type=float, default=20)
    sn = sub.add_parser("simulate-night", help="kirjoita simuloitu tallenne istunnoksi")
    sn.add_argument("--hours", type=float, default=7.5)
    sn.add_argument("--days-ago", type=int, default=1)
    sn.add_argument("--seed", type=int, default=11)
    sub.add_parser("set-password", help="aseta käyttöliittymän salasana (basic auth)")
    sub.add_parser("doctor", help="tarkista ympäristö ja Bluetooth-oikeus")
    va = sub.add_parser("validate", help="validoi lyöntianalyysi MIT-BIH- ja/tai INCART-tietokantaa vasten")
    va.add_argument("--mitdb", type=Path, help="puretun MIT-BIH Arrhythmia Database -kansion polku")
    va.add_argument("--incartdb", type=Path, help="puretun St Petersburg INCART -tietokannan kansio (jossa I01.hea …)")
    va.add_argument("--out", type=Path, default=Path("docs/validation"))
    args = p.parse_args()
    if args.cmd == "validate":
        from .analysis import ANALYSIS_VERSION
        from .validation import validate
        if not args.mitdb and not args.incartdb:
            p.error("anna --mitdb ja/tai --incartdb")
        for kind, db in (("mitdb", args.mitdb), ("incartdb", args.incartdb)):
            if db:
                validate(db, args.out, kind)
                print(f"Tulokset: {args.out / f'{kind}-v{ANALYSIS_VERSION}-results.json'}")
        return
    cfg = load_config()
    cmd = args.cmd or "run"

    if cmd == "run":
        if args.port:
            cfg.port = args.port
        setup_logging(cfg, args.verbose)
        asyncio.run(_run(cfg, args.simulate))
    elif cmd == "probe":
        asyncio.run(_probe(cfg, args.seconds))
    elif cmd == "simulate-night":
        from datetime import datetime, timedelta

        from .simulator import generate_night
        start = (datetime.now() - timedelta(days=args.days_ago)).replace(hour=23, minute=8 + args.seed % 40, second=0, microsecond=0)
        d = generate_night(cfg.sessions_dir, args.hours, start, args.seed,
                           progress=lambda f: print(f"\r{f * 100:5.1f} %", end="", flush=True))
        print(f"\nKirjoitettu {d}")
    elif cmd == "set-password":
        from .server import hash_password
        user = input(f"Käyttäjätunnus [{cfg.auth.username}]: ").strip() or cfg.auth.username
        pw = getpass.getpass("Salasana (tyhjä = poista käytöstä): ")
        if pw and pw != getpass.getpass("Uudelleen: "):
            sys.exit("Salasanat eivät täsmää.")
        cfg.auth.username = user
        cfg.auth.password_hash = hash_password(pw) if pw else ""
        cfg.save()
        print("Tallennettu. Käynnistä palvelu uudelleen.")
    elif cmd == "doctor":
        _doctor(cfg)


if __name__ == "__main__":
    main()
