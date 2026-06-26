"""AFKApp: service container + RPC method registry.

This is the heart of the backend. Services (settings, and in later phases
transcription / clarify / statistics / audio) are constructed here and exposed
to Electron through a flat method table. Keeping the table explicit makes the
backend API easy to audit and version.
"""

import platform
import sys
from typing import Any, Callable, Dict

from . import config, logutil, __version__
from .rpc import emit_event, RpcError
from .settings import SettingsStore


class AFKApp:
    def __init__(self) -> None:
        self.settings = SettingsStore()
        if not self.settings.get("logging", True):
            logutil.set_level("warn")

        # Services added in later phases (kept as None so get_info can report).
        self.transcriber = None      # Phase 2
        self.clarifier = None        # Phase 4
        self.statistics = None       # Phase 5
        self.recorder = None         # Phase 2/3

        self._methods: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._register_core()

    # ---- lifecycle ----
    def on_started(self) -> None:
        """Called once the RPC loop is live; announce readiness to Electron."""
        emit_event("ready", self.get_info({}))

    def shutdown(self) -> None:
        logutil.info("Shutting down services")
        # Later phases: release models, stop audio streams, flush stats.

    # ---- dispatch ----
    def dispatch(self, method: str, params: Dict[str, Any]) -> Any:
        fn = self._methods.get(method)
        if fn is None:
            raise RpcError(f"Unknown method: {method}", code=-32601)
        return fn(params or {})

    def register(self, name: str, fn: Callable[[Dict[str, Any]], Any]) -> None:
        self._methods[name] = fn

    # ---- core methods ----
    def _register_core(self) -> None:
        self.register("ping", lambda p: {"pong": True})
        self.register("get_info", self.get_info)
        self.register("get_settings", lambda p: self.settings.all())
        self.register("update_settings", self.update_settings)
        self.register("list_methods", lambda p: sorted(self._methods.keys()))

    def get_info(self, _params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "version": __version__,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "backend": "afk-backend",
            "models_status": self._models_status(),
            "default_model": "auto (Gemma 3 270M / Gemma 3n E2B)",
            "asr_model": config.PARAKEET_MODEL,
            "data_dir": str(config.data_dir()),
            "models_dir": str(config.models_dir()),
        }

    def _models_status(self) -> str:
        # Phase 2/4 will report real load state.
        loaded = []
        if self.transcriber is not None:
            loaded.append("asr")
        if self.clarifier is not None:
            loaded.append("clarify")
        return ", ".join(loaded) if loaded else "not loaded (Phase 2/4)"

    def update_settings(self, params: Dict[str, Any]) -> Dict[str, Any]:
        patch = params.get("patch") or params
        updated = self.settings.update(patch)
        if not updated.get("logging", True):
            logutil.set_level("warn")
        else:
            logutil.set_level("debug")
        emit_event("settings_updated", updated)
        return updated
