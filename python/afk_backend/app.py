"""AFKApp: service container + RPC method registry.

This is the heart of the backend. Services (settings, and in later phases
transcription / clarify / statistics / audio) are constructed here and exposed
to Electron through a flat method table. Keeping the table explicit makes the
backend API easy to audit and version.
"""

import os
import platform
import sys
import threading
from typing import Any, Callable, Dict

from . import config, logutil, __version__
from .rpc import emit_event, RpcError
from .settings import SettingsStore
from .audio.recorder import Recorder, process as process_audio
from .transcription.transcriber import Transcriber
from .clipboard.clipboard import Clipboard
from .hotkeys import HotkeyManager
from .clarify.engine import ClarifyEngine


class AFKApp:
    def __init__(self) -> None:
        self.settings = SettingsStore()
        if not self.settings.get("logging", True):
            logutil.set_level("warn")

        # Phase 2 services.
        self.recorder = Recorder()
        self.transcriber = Transcriber()

        # Phase 3 services.
        self.clipboard = Clipboard()
        self.hotkeys = HotkeyManager(
            {
                "ptt_start": self._hk_ptt_start,
                "ptt_stop": self._hk_ptt_stop,
                "toggle": self._hk_toggle,
                "clarify": self._hk_clarify,
            }
        )

        # Phase 4 service.
        self.clarifier = ClarifyEngine()

        # Services added in later phases.
        self.statistics = None       # Phase 5

        self._methods: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._register_core()
        self._register_audio()
        self._register_clipboard_hotkeys()
        self._register_clarify()

    # ---- lifecycle ----
    def on_started(self) -> None:
        """Called once the RPC loop is live; announce readiness to Electron."""
        emit_event("ready", self.get_info({}))
        # Warm up models in the background so the first use is fast.
        # AFK_NO_PRELOAD lets tests skip spawning model processes.
        if not os.environ.get("AFK_NO_PRELOAD"):
            self.transcriber.preload_async()
            self.clarifier.preload_short_async()
        # Arm global hotkeys from saved settings.
        try:
            self.hotkeys.set_bindings(self.settings.get("hotkeys", {}))
            self.hotkeys.start()
        except Exception as exc:  # noqa: BLE001
            logutil.error(f"Failed to start hotkeys: {exc}")

    def shutdown(self) -> None:
        logutil.info("Shutting down services")
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        try:
            if self.recorder.is_recording:
                self.recorder.stop()
        except Exception:
            pass
        try:
            self.clarifier.shutdown()
        except Exception:
            pass

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
            "default_model": "auto (Gemma 3 270M / Gemma 4 E2B)",
            "asr_model": config.PARAKEET_MODEL,
            "data_dir": str(config.data_dir()),
            "models_dir": str(config.models_dir()),
        }

    def _models_status(self) -> str:
        cs = self.clarifier.status()
        return (
            f"asr[{self.transcriber.engine}]: {self.transcriber.status}, "
            f"clarify(short): {cs['short']}, clarify(long): {cs['long']}"
        )

    def update_settings(self, params: Dict[str, Any]) -> Dict[str, Any]:
        patch = params.get("patch") or params
        updated = self.settings.update(patch)
        if not updated.get("logging", True):
            logutil.set_level("warn")
        else:
            logutil.set_level("debug")
        # Live-reload hotkey bindings if they changed.
        try:
            self.hotkeys.set_bindings(updated.get("hotkeys", {}))
        except Exception as exc:  # noqa: BLE001
            logutil.warn(f"hotkey reload failed: {exc}")
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

    # ---- clipboard + hotkeys methods (Phase 3) ----
    def _register_clipboard_hotkeys(self) -> None:
        self.register("get_clipboard", lambda p: {"text": self.clipboard.get_text()})
        self.register("set_clipboard", self._set_clipboard)
        self.register("paste_text", self._paste_text_method)
        self.register("set_hotkeys", self._set_hotkeys)
        self.register("hotkeys_status", self._hotkeys_status)

    def _set_clipboard(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self.clipboard.set_text(params.get("text", ""))
        return {"ok": True}

    def _paste_text_method(self, params: Dict[str, Any]) -> Dict[str, Any]:
        text = params.get("text", "")
        self._paste(text)
        return {"ok": True, "chars": len(text)}

    def _set_hotkeys(self, params: Dict[str, Any]) -> Dict[str, Any]:
        hk = params.get("hotkeys") or params
        updated = self.settings.update({"hotkeys": hk})
        self.hotkeys.set_bindings(updated.get("hotkeys", {}))
        emit_event("settings_updated", updated)
        return updated["hotkeys"]

    def _hotkeys_status(self, _params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "available": self.hotkeys.available(),
            "hotkeys": self.settings.get("hotkeys", {}),
        }

    # ---- shared dictation flow ----
    def _paste(self, text: str) -> None:
        """Place text on the clipboard and paste it into the focused app."""
        if not text:
            return
        try:
            self.hotkeys.set_injecting(True)
            self.clipboard.paste_text(text)
            emit_event("pasted", {"chars": len(text)})
        except Exception as exc:  # noqa: BLE001
            logutil.error(f"paste failed: {exc}")
        finally:
            self.hotkeys.set_injecting(False)

    def _start_rec_safe(self) -> None:
        try:
            if not self.recorder.is_recording:
                self.start_recording({})
        except Exception as exc:  # noqa: BLE001
            logutil.error(f"start recording failed: {exc}")

    def _stop_transcribe_paste(self) -> None:
        try:
            result = self.stop_recording({})
        except Exception as exc:  # noqa: BLE001
            logutil.error(f"stop/transcribe failed: {exc}")
            return
        text = (result or {}).get("text", "")
        if text and self.settings.get("auto_paste", True):
            self._paste(text)

    # ---- hotkey callbacks (run on the listener thread; offload heavy work) ----
    def _hk_ptt_start(self) -> None:
        threading.Thread(target=self._start_rec_safe, daemon=True).start()

    def _hk_ptt_stop(self) -> None:
        threading.Thread(target=self._stop_transcribe_paste, daemon=True).start()

    def _hk_toggle(self) -> None:
        if self.recorder.is_recording:
            threading.Thread(target=self._stop_transcribe_paste, daemon=True).start()
        else:
            threading.Thread(target=self._start_rec_safe, daemon=True).start()

    def _hk_clarify(self) -> None:
        threading.Thread(target=self._clarify_flow, daemon=True).start()

    # ---- clarify methods (Phase 4) ----
    def _register_clarify(self) -> None:
        self.register("clarify", self._clarify_method)
        self.register("clarify_status", lambda p: self.clarifier.status())

    def _clarify_method(self, params: Dict[str, Any]) -> Dict[str, Any]:
        text = params.get("text", "")
        threshold = params.get("threshold", self.settings.get("word_count_threshold"))
        return self.clarifier.clarify(text, threshold=threshold)

    def _clarify_flow(self) -> None:
        """Hotkey Clarify: take the selection (or clipboard), polish, put it back.

        1. Capture selected text (Ctrl+C). If empty, fall back to clipboard.
        2. Route by word count and clarify.
        3. Replace the selection by pasting (or update the clipboard if we used
           the clipboard fallback).
        """
        if not self.clarifier.any_available():
            logutil.warn("Clarify requested but no model available")
            emit_event("clarify_unavailable", {"reason": "No Clarify model installed"})
            return

        # Capture selection with the listener suppressed (we synthesize Ctrl+C).
        try:
            self.hotkeys.set_injecting(True)
            selection = self.clipboard.capture_selection()
        finally:
            self.hotkeys.set_injecting(False)

        had_selection = bool(selection.strip())
        text = selection.strip() or self.clipboard.get_text().strip()
        if not text:
            emit_event("clarify_done", {"text": "", "model": "none", "empty": True})
            return

        threshold = self.settings.get("word_count_threshold", config.DEFAULT_WORD_THRESHOLD)
        result = self.clarifier.clarify(text, threshold=threshold)
        out = result.get("text", "") or text

        if had_selection:
            # Replace the highlighted text in place.
            try:
                self.hotkeys.set_injecting(True)
                self.clipboard.replace_selection(out)
            finally:
                self.hotkeys.set_injecting(False)
        else:
            # No selection — just update the clipboard with the polished text.
            self.clipboard.set_text(out)

        emit_event(
            "clarify_done",
            {"text": out, "model": result.get("model"), "latency_ms": result.get("latency_ms")},
        )
