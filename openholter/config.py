"""Configuration. Lives in $OPENHOLTER_HOME/config.json (default ~/openholter-data)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Optional


LEGACY_HOME = "~/hearth-data"  # the project was called Hearth before 0.3


def home_dir() -> Path:
    env = os.environ.get("OPENHOLTER_HOME") or os.environ.get("HEARTH_HOME")
    return Path(env or "~/openholter-data").expanduser()


def migrate_legacy_home() -> Optional[str]:
    """Move ~/hearth-data to ~/openholter-data once, if the new folder doesn't exist yet."""
    if os.environ.get("OPENHOLTER_HOME") or os.environ.get("HEARTH_HOME"):
        return None
    old, new = Path(LEGACY_HOME).expanduser(), Path("~/openholter-data").expanduser()
    if old.is_dir() and not new.exists():
        old.rename(new)
        return f"moved {old} -> {new}"
    return None


@dataclass
class AuthConfig:
    username: str = "openholter"
    # "pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>", set with `python -m openholter set-password`. Empty = auth disabled.
    password_hash: str = ""


@dataclass
class Config:
    # Device is matched by name prefix; set `device_address` (CoreBluetooth UUID on macOS) to pin one strap.
    device_name_prefix: str = "Polar H10"
    device_address: Optional[str] = None

    ecg_sample_rate: int = 130
    acc_sample_rate: int = 50
    acc_range_g: int = 4

    # Session ends when the strap has been unreachable this long.
    session_timeout_min: float = 10.0
    # Watchdog: reconnect if connected but no PMD data arrives for this long.
    data_timeout_s: float = 15.0
    # A connected H10 keeps streaming (and draining its battery) even when nobody wears it. With no skin
    # contact and no recording for this long the strap is let go, and left alone for `rest_after_release_s`
    # so it can fall asleep; it advertises again when it is put on. 0 = never let go.
    release_unworn_s: float = 120.0
    rest_after_release_s: float = 180.0
    # "always" keeps the computer awake while the app runs (needed for auto-detecting the strap),
    # "recording" only during a session, "never" leaves sleep alone.
    prevent_sleep: str = "always"
    # Start a recording by itself when the strap is worn (steady skin contact). Off = only from the UI.
    auto_record: bool = True
    # Daily analysis of finished nights ("HH:MM", "" = only from the UI button).
    analysis_time: str = "12:00"

    host: str = "0.0.0.0"
    port: int = 8765
    auth: AuthConfig = field(default_factory=AuthConfig)

    @property
    def home(self) -> Path:
        return home_dir()

    @property
    def sessions_dir(self) -> Path:
        return self.home / "sessions"

    @property
    def logs_dir(self) -> Path:
        return self.home / "logs"

    @property
    def path(self) -> Path:
        return self.home / "config.json"

    def save(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2) + "\n")
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)


def load_config() -> Config:
    migrate_legacy_home()
    cfg = Config()
    path = cfg.path
    if path.exists():
        raw = json.loads(path.read_text())
        known = {f.name for f in fields(Config)}
        for key, value in raw.items():
            if key == "auth" and isinstance(value, dict):
                cfg.auth = AuthConfig(**{k: v for k, v in value.items() if k in {"username", "password_hash"}})
            elif key in known:
                setattr(cfg, key, value)
    else:
        cfg.save()
    for d in (cfg.sessions_dir, cfg.logs_dir):
        d.mkdir(parents=True, exist_ok=True)
    return cfg
