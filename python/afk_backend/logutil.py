"""Logging helpers.

Critical invariant: NOTHING may be written to stdout except JSON-RPC
protocol messages. All logging therefore goes to stderr.
"""

import sys
import threading
import time

_lock = threading.Lock()
_LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}
_min_level = 10


def set_level(level: str) -> None:
    global _min_level
    _min_level = _LEVELS.get(level, 10)


def _emit(level: str, msg: str) -> None:
    if _LEVELS.get(level, 20) < _min_level:
        return
    ts = time.strftime("%H:%M:%S")
    line = f"{ts} [{level.upper()}] {msg}\n"
    with _lock:
        try:
            sys.stderr.write(line)
            sys.stderr.flush()
        except Exception:
            pass


def debug(msg: str) -> None:
    _emit("debug", msg)


def info(msg: str) -> None:
    _emit("info", msg)


def warn(msg: str) -> None:
    _emit("warn", msg)


def error(msg: str) -> None:
    _emit("error", msg)
