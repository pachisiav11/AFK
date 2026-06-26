"""JSON-backed settings store with sane defaults and atomic writes.

Settings are intentionally simple (a flat-ish dict) so the renderer can read
and patch them over RPC without a schema migration system. Unknown keys from
the user file are preserved; missing keys are filled from defaults.
"""

import json
import os
import tempfile
import threading
from copy import deepcopy
from typing import Any, Dict

from .. import config, logutil

DEFAULT_SETTINGS: Dict[str, Any] = {
    "microphone": None,            # device name; None = system default
    "theme": "dark",
    "startup_on_login": False,
    "launch_minimized": False,
    "auto_paste": True,
    "auto_clarify": True,
    "word_count_threshold": config.DEFAULT_WORD_THRESHOLD,
    "logging": True,
    "developer_mode": False,
    "hotkeys": {
        "push_to_talk": "Ctrl+Space",       # held to record
        "toggle": "Ctrl+Shift+Space",        # toggle recording
        "clarify": "Ctrl+Shift+C",           # clarify selection/clipboard
    },
    "noise_suppression": True,
    "auto_gain": True,
    "silence_trim": True,
}


class SettingsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._path = config.settings_path()
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        data = deepcopy(DEFAULT_SETTINGS)
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    user = json.load(fh)
                data = _deep_merge(data, user)
            except Exception as exc:  # noqa: BLE001
                logutil.warn(f"Failed to read settings, using defaults: {exc}")
        return data

    def all(self) -> Dict[str, Any]:
        with self._lock:
            return deepcopy(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return deepcopy(self._data.get(key, default))

    def update(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._data = _deep_merge(self._data, patch)
            self._save()
            return deepcopy(self._data)

    def _save(self) -> None:
        try:
            fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self._path)
        except Exception as exc:  # noqa: BLE001
            logutil.error(f"Failed to save settings: {exc}")


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out
