"""AFKApp: service container + RPC method registry.

This is the heart of the backend. Services (settings, and in later phases
transcription / clarify / statistics / audio) are constructed here and exposed
to Electron through a flat method table. Keeping the table explicit makes the
backend API easy to audit and version.
"""

import platform
import sys
import threading
from typing import Any, Callable, Dict

from . import config, logutil, __version__
from .rpc import emit_event, RpcError
from .settings import SettingsStore
from .audio.recorder import Recorder, process as process_audio
from .transcription.transcriber import Transcriber


class AFKApp:
    def __init__(self) -> None:
        self.settings = SettingsStore()
        if not self.settings.get("logging", True):
            logutil.set_level("warn")

        # Phase 2 services.
        self.recorder = Recorder()
        self.transcriber = Transcriber()

        # Services added in later phases.
        self.clarifier = None        # Phase 4
        self.statistics = None       # Phase 5

        self._methods: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._register_core()
        self._register_audio()

    # ---- lifecycle ----
    def on_started(self) -> None:
        """Called once the RPC loop is live; announce readiness to Electron."""
        emit_event("ready", self.get_info({}))
        # Warm up the ASR model in the background so the first dictation is fast.
        # (Downloads weights on first ever run; subsequent runs are instant.)
        self.transcriber.preload_async()

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
        parts = [f"asr[{self.transcriber.engine}]: {self.transcriber.status}"]
        if self.clarifier is not None:
            parts.append("clarify: loaded")
        else:
            parts.append("clarify: not loaded (Phase 4)")
        return ", ".join(parts)

    def update_settings(self, params: Dict[str, Any]) -> Dict[str, Any]:
        patch = params.get("patch") or params
        updated = self.settings.update(patch)
        if not updated.get("logging", True):
            logutil.set_level("warn")
        else:
            logutil.set_level("debug")
        emit_event("settings_updated", updated)
        return updated

    # ---- audio / transcription methods (Phase 2) ----
    def _register_audio(self) -> None:
        self.register("list_microphones", lambda p: {"devices": Recorder.list_devices()})
        self.register(
            "asr_status",
            lambda p: {"status": self.transcriber.status, "engine": self.transcriber.engine},
        )
        self.register("load_asr", self._load_asr)
        self.register("start_recording", self.start_recording)
        self.register("stop_recording", self.stop_recording)
        self.register("transcribe", self.transcribe)

    def _load_asr(self, _params: Dict[str, Any]) -> Dict[str, Any]:
        # Trigger a (possibly long) load/download synchronously and report.
        try:
            self.transcriber.ensure_loaded()
            return {"status": self.transcriber.status}
        except Exception as exc:  # noqa: BLE001
            raise RpcError(f"ASR load failed: {exc}")

    def start_recording(self, params: Dict[str, Any]) -> Dict[str, Any]:
        device = params.get("device", self.settings.get("microphone"))
        self.recorder.start(device=device)
        emit_event("recording_started", {"device": device})
        return {"recording": True}

    def stop_recording(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Stop recording, condition the audio, transcribe, and return text."""
        captured = self.recorder.stop()
        emit_event("recording_stopped", {"duration": captured["duration"]})

        audio = captured["audio"]
        if audio is None or len(audio) == 0:
            emit_event("transcription", {"text": ""})
            return {"text": "", "duration": captured["duration"], "latency_ms": 0}

        s = self.settings.all()
        audio = process_audio(
            audio,
            sr=captured["sr"],
            noise_suppression=s.get("noise_suppression", True),
            auto_gain=s.get("auto_gain", True),
            silence_trim=s.get("silence_trim", True),
        )

        result = self.transcriber.transcribe(audio, sample_rate=captured["sr"])
        result["duration"] = round(captured["duration"], 2)
        emit_event("transcription", {"text": result["text"], "latency_ms": result["latency_ms"]})
        return result

    def transcribe(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Transcribe a wav file path (used for tests / file import)."""
        path = params.get("path")
        if not path:
            raise RpcError("transcribe requires a 'path'")
        self.transcriber.ensure_loaded()
        import numpy as np
        import soundfile as sf

        audio, sr = sf.read(path, dtype="float32", always_2d=False)
        if getattr(audio, "ndim", 1) > 1:
            audio = audio.mean(axis=1).astype(np.float32)
        return self.transcriber.transcribe(audio, sample_rate=int(sr))
