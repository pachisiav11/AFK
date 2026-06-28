"""Transcriber facade.

Presents a single stable interface to the rest of the backend while choosing
the underlying ASR engine at load time:

  * 'nemo' — official NVIDIA Parakeet .nemo checkpoint (if the user provided one)
  * 'onnx' — Parakeet 0.6B v3 via onnx-asr (default; light + fast on CPU)

The choice is made by config.select_asr_engine(), which prefers a local .nemo
checkpoint when present and otherwise falls back to ONNX. This keeps the rest
of the app (app.py, UI) completely engine-agnostic.
"""

import re
import threading
from typing import Optional

import numpy as np

from .. import config, logutil
from .parakeet import OnnxParakeet

TARGET_SR = 16000


class Transcriber:
    def __init__(self) -> None:
        self._backend = None
        self._engine: Optional[str] = None
        self._lock = threading.Lock()
        self._loading = False
        self._load_error: Optional[str] = None

    # ---- engine selection ----
    def _select_backend(self):
        engine, nemo_path = config.select_asr_engine()
        if engine == "nemo":
            from .nemo_backend import NemoParakeet

            logutil.info(f"ASR engine: NeMo (official checkpoint: {nemo_path})")
            return "nemo", NemoParakeet(nemo_path)
        logutil.info("ASR engine: onnx-asr (Parakeet 0.6B v3, int8/CPU)")
        return "onnx", OnnxParakeet()

    # ---- state ----
    @property
    def engine(self) -> str:
        return self._engine or config.select_asr_engine()[0]

    @property
    def is_loaded(self) -> bool:
        return self._backend is not None and self._backend.is_loaded

    @property
    def status(self) -> str:
        if self._backend is not None:
            return self._backend.status
        if self._loading:
            return "loading"
        if self._load_error:
            return f"error: {self._load_error}"
        return "not loaded"

    # ---- loading ----
    def ensure_loaded(self) -> None:
        if self._backend is not None and self._backend.is_loaded:
            return
        with self._lock:
            if self._backend is None:
                self._engine, self._backend = self._select_backend()
            self._loading = True
            self._load_error = None
            try:
                self._backend.ensure_loaded()
            except Exception as exc:  # noqa: BLE001
                self._load_error = str(exc)
                raise
            finally:
                self._loading = False

    def preload_async(self) -> None:
        def _run():
            try:
                self.ensure_loaded()
            except Exception:
                pass

        threading.Thread(target=_run, name="asr-preload", daemon=True).start()

    # ---- inference ----
    def transcribe(self, audio: np.ndarray, sample_rate: int = TARGET_SR) -> dict:
        if audio is None or len(audio) == 0:
            return {"text": "", "latency_ms": 0, "audio_seconds": 0.0}
        self.ensure_loaded()
        result = self._backend.transcribe(audio, sample_rate=sample_rate)
        result["text"] = clean_transcript(result.get("text", ""))
        result["engine"] = self._engine
        return result


CHAT_TOKEN_RE = re.compile(r"<\|im_(?:start|end)\|>|<\|endoftext\|>", re.IGNORECASE)
CHAT_ROLE_RE = re.compile(
    r"^\s*(?:system|assistant|user)\s*(?:input)?\s*:?\s*",
    re.IGNORECASE,
)


def clean_transcript(text: str) -> str:
    """Remove model prompt/control-token leakage from ASR output."""
    raw = str(text or "").strip()
    if not raw:
        return ""

    if CHAT_TOKEN_RE.search(raw):
        first = CHAT_TOKEN_RE.split(raw, maxsplit=1)[0].strip()
        if first:
            return _normalize_transcript(first)
        raw = CHAT_TOKEN_RE.sub("\n", raw)

    cleaned_lines = []
    for line in re.split(r"[\r\n]+", raw):
        candidate = CHAT_ROLE_RE.sub("", line).strip()
        if candidate:
            cleaned_lines.append(candidate)

    return _normalize_transcript(" ".join(cleaned_lines))


def _normalize_transcript(text: str) -> str:
    text = CHAT_TOKEN_RE.sub("", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text
