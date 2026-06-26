"""Official NVIDIA Parakeet 0.6B v3 via the NeMo toolkit (CPU).

Used when the user has placed the official `parakeet-tdt-0.6b-v3.nemo`
checkpoint on disk (see config.select_asr_engine). Heavier than the ONNX
path — NeMo import alone is ~40s and the model restore adds more — so loading
happens once, lazily, on a background thread.

We transcribe by writing the conditioned waveform to a temp 16 kHz wav and
handing the path to NeMo, which is the most version-robust input form.
"""

import os
import tempfile
import threading
import time
from typing import Optional

import numpy as np

from .. import config, logutil

TARGET_SR = 16000


class NemoParakeet:
    """Parakeet 0.6B v3 via NVIDIA NeMo (official checkpoint, CPU)."""

    def __init__(self, nemo_path=None):
        self.nemo_path = str(nemo_path or config.local_nemo_path())
        self._model = None
        self._lock = threading.Lock()
        self._loading = False
        self._load_error: Optional[str] = None

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

    def ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            self._loading = True
            self._load_error = None
            try:
                import warnings

                warnings.filterwarnings("ignore")
                # Use all CPU cores for inference.
                try:
                    import torch

                    torch.set_num_threads(max(1, os.cpu_count() or 1))
                except Exception:
                    pass

                import nemo.collections.asr as nemo_asr  # heavy import (~40s)

                try:
                    from nemo.utils import logging as nemo_logging

                    nemo_logging.setLevel("ERROR")
                except Exception:
                    pass

                if not os.path.isfile(self.nemo_path):
                    raise FileNotFoundError(f".nemo checkpoint not found: {self.nemo_path}")

                t0 = time.time()
                logutil.info(f"Restoring NeMo model from '{self.nemo_path}' (CPU)…")
                self._model = nemo_asr.models.ASRModel.restore_from(
                    self.nemo_path, map_location="cpu"
                )
                self._model.eval()
                logutil.info(f"NeMo model ready in {time.time() - t0:.1f}s")
            except Exception as exc:  # noqa: BLE001
                self._load_error = str(exc)
                logutil.error(f"Failed to load NeMo model: {exc}")
                raise
            finally:
                self._loading = False

    def preload_async(self) -> None:
        def _run():
            try:
                self.ensure_loaded()
            except Exception:
                pass

        threading.Thread(target=_run, name="nemo-preload", daemon=True).start()

    def transcribe(self, audio: np.ndarray, sample_rate: int = TARGET_SR) -> dict:
        if audio is None or len(audio) == 0:
            return {"text": "", "latency_ms": 0, "audio_seconds": 0.0}

        self.ensure_loaded()
        audio = np.asarray(audio, dtype=np.float32)

        # NeMo's Parakeet expects 16 kHz; resample defensively if needed.
        if sample_rate != TARGET_SR:
            from ..audio.recorder import _resample

            audio = _resample(audio, sample_rate, TARGET_SR)
            sample_rate = TARGET_SR

        t0 = time.time()
        tmp = None
        try:
            import soundfile as sf

            fd, tmp = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            sf.write(tmp, audio, sample_rate, subtype="PCM_16")
            out = self._model.transcribe([tmp], batch_size=1, verbose=False)
            text = _extract_text(out)
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass

        latency_ms = int((time.time() - t0) * 1000)
        audio_seconds = len(audio) / float(sample_rate)
        logutil.debug(
            f"[nemo] Transcribed {audio_seconds:.1f}s in {latency_ms}ms -> {len(text.split())} words"
        )
        return {
            "text": (text or "").strip(),
            "latency_ms": latency_ms,
            "audio_seconds": round(audio_seconds, 2),
        }


def _extract_text(out) -> str:
    """Normalise NeMo transcribe() output across versions.

    May be: a string, a Hypothesis (has .text), or (nested) lists of those.
    """
    if out is None:
        return ""
    if isinstance(out, str):
        return out
    if hasattr(out, "text"):
        return out.text
    if isinstance(out, (list, tuple)):
        if not out:
            return ""
        # RNNT/TDT may return (best_hyps, all_hyps); take the first list.
        first = out[0]
        if isinstance(first, (list, tuple)):
            return _extract_text(first)
        return _extract_text(first)
    return str(out)
