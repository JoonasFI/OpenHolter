"""Keep the computer awake while recording (or while the app runs).

- macOS:   caffeinate(8) -i -s, tied to our PID so it exits if we die
- Windows: SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) held by a small
           dedicated thread (the flag is per thread and the HTTP handlers run on a pool)
- Linux:   systemd-inhibit --what=sleep:idle around a process that exits with ours
The display may still turn off; only system sleep is blocked.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
from typing import Optional

log = logging.getLogger(__name__)

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


class SleepGuard:
    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    @property
    def active(self) -> bool:
        if self._thread is not None:
            return self._thread.is_alive()
        return self._proc is not None and self._proc.poll() is None

    @property
    def supported(self) -> bool:
        if sys.platform == "darwin":
            return shutil.which("caffeinate") is not None
        if sys.platform == "win32":
            return True
        return shutil.which("systemd-inhibit") is not None

    def hold(self) -> None:
        if self.active:
            return
        if sys.platform == "win32":
            self._hold_windows()
        elif sys.platform == "darwin":
            self._spawn(["caffeinate", "-i", "-s", "-w", str(os.getpid())], "caffeinate")
        else:
            # `tail --pid` ends when we do, which releases the inhibitor lock
            self._spawn(["systemd-inhibit", "--what=sleep:idle", "--who=OpenHolter", "--why=Recording ECG", "--mode=block",
                         "tail", f"--pid={os.getpid()}", "-f", "/dev/null"], "systemd-inhibit")

    def _spawn(self, cmd: list, name: str) -> None:
        exe = shutil.which(cmd[0])
        if not exe:
            log.warning("%s not found; system sleep is not prevented", name)
            return
        self._proc = subprocess.Popen([exe, *cmd[1:]])
        log.info("sleep prevention on (%s pid %s)", name, self._proc.pid)

    def _hold_windows(self) -> None:
        import ctypes

        self._stop.clear()

        def keep_awake() -> None:
            k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            k32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
            self._stop.wait()
            k32.SetThreadExecutionState(ES_CONTINUOUS)

        self._thread = threading.Thread(target=keep_awake, name="sleep-guard", daemon=True)
        self._thread.start()
        log.info("sleep prevention on (SetThreadExecutionState)")

    def release(self) -> None:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=2)
            self._thread = None
            log.info("sleep prevention off")
        if self._proc is not None:
            self._proc.terminate()
            self._proc = None
            log.info("sleep prevention off")
