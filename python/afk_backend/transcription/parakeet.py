"""Parakeet 0.6B v3 speech recognition (ONNX, CPU).

Wraps `onnx-asr` with the multilingual Parakeet TDT 0.6B v3 model. The int8
quantized variant needs ~2 GB RAM (vs ~6 GB fp32), keeping us well within the
16 GB target while running fully on CPU.

Model weights download lazily from Hugging Face on first use into AFK's
models directory (never committed to git). Loading is done on a background
thread so the UI stays responsive.
"""

import os
import threading
import time
from typing import Optional

import numpy as np

from .. import config, logutil

# Route the Hugging Face cache into AFK's models dir BEFORE onnx_asr imports it.
os.environ.setdefault("HF_HOME", str(config.models_dir()))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

TARGET_SR = 16000


class OnnxParakeet:
    """Parakeet 0.6B v3 via onnx-asr (default engine; fast on CPU)."""

    def __init__(self, model_name: str = config.PARAKEET_MODEL, quantization: str = "int8"):
        self.model_name = model_name
        self.quantization = quantization
        self._model = None
        self._lock = threading.Lock()
        self._loading = False
        self._load_error: Optional[str] = None

    # ---- state ----
    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def status(self) -> str:
        if self._model is not None:
            return "loaded"
        if self._loading:
            return "loading"
        if self._load_error:
            return f"error: {self._load_error}"
        return "not loaded"

    # ---- loading ----
    def ensure_loaded(self) -> None:
        """Block until the model is loaded (or raise). Idempotent + thread-safe."""
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            self._loading = True
            self._load_error = None
            try:
                import onnx_asr  # imported lazily; heavy

                t0 = time.time()
                local_dir = config.local_asr_dir()
                use_local = _has_local_model_files(local_dir)
                if use_local:
                    logutil.info(
                        f"Loading ASR model from local dir '{local_dir}' "
                        f"({self.quantization}, CPU)…"
                    )
                    self._model = onnx_asr.load_model(
                        self.model_name,
                        str(local_dir),
                        quantization=self.quantization,
                        providers=["CPUExecutionProvider"],
                    )
                else:
                    logutil.info(
                        f"Loading ASR model '{self.model_name}' from Hugging Face "
                        f"({self.quantization}, CPU)…"
                    )
                    self._model = onnx_asr.load_model(
                        self.model_name,
                        quantization=self.quantization,
                        providers=["CPUExecutionProvider"],
                    )
                logutil.info(f"ASR model ready in {time.time() - t0:.1f}s")
            except Exception as exc:  # noqa: BLE001
                self._load_error = str(exc)
                logutil.error(f"Failed to load ASR model: {exc}")
                raise
            finally:
                self._loading = False

    def preload_async(self) -> None:
        """Kick off model loading in the background; ignore errors here."""
        def _run():
            try:
                self.ensure_loaded()
            except Exception:
                pass

        threading.Thread(target=_run, name="asr-preload", daemon=True).start()

    # ---- inference ----
    def transcribe(self, audio: np.ndarray, sample_rate: int = TARGET_SR) -> dict:
        """Transcribe a float32 mono waveform. Returns text + timing."""
        if audio is None or len(audio) == 0:
            return {"text": "", "latency_ms": 0, "audio_seconds": 0.0}

        self.ensure_loaded()
        audio = np.asarray(audio, dtype=np.float32)

        t0 = time.time()
        result = self._model.recognize(audio, sample_rate=sample_rate)
        text = result if isinstance(result, str) else getattr(result, "text", str(result))
        latency_ms = int((time.time() - t0) * 1000)
        audio_seconds = len(audio) / float(sample_rate)
        logutil.debug(
            f"Transcribed {audio_seconds:.1f}s audio in {latency_ms}ms -> {len(text.split())} words"
        )
        return {
            "text": (text or "").strip(),
            "latency_ms": latency_ms,
            "audio_seconds": round(audio_seconds, 2),
        }


def _has_local_model_files(local_dir) -> bool:
    """Return true when a local onnx-asr Parakeet folder is complete enough."""
    return local_dir.exists() and all((local_dir / f).exists() for f in config.LOCAL_ASR_REQUIRED)
