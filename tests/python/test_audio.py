"""Phase 2 audio DSP tests — no model, no microphone required."""

import sys
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "python"))

from afk_backend.audio.recorder import _resample, _trim_silence, process  # noqa: E402


class TestDsp(unittest.TestCase):
    def test_resample_length(self):
        x = np.linspace(-1, 1, 48000, dtype=np.float32)
        y = _resample(x, 48000, 16000)
        self.assertEqual(len(y), 16000)
        self.assertEqual(y.dtype, np.float32)

    def test_resample_noop(self):
        x = np.zeros(100, dtype=np.float32)
        self.assertIs(_resample(x, 16000, 16000), x)

    def test_trim_silence_removes_lead_trail(self):
        sr = 16000
        speech = (np.random.randn(sr).astype(np.float32)) * 0.5
        clip = np.concatenate([np.zeros(sr, np.float32), speech, np.zeros(sr, np.float32)])
        trimmed = _trim_silence(clip, sr)
        self.assertLess(len(trimmed), len(clip))
        self.assertGreater(len(trimmed), 0)

    def test_trim_all_silence_keeps_audio(self):
        x = np.zeros(8000, dtype=np.float32)
        self.assertEqual(len(_trim_silence(x, 16000)), len(x))

    def test_process_auto_gain_normalizes(self):
        sr = 16000
        quiet = (np.random.randn(sr).astype(np.float32)) * 0.05
        out = process(quiet, sr, noise_suppression=False, silence_trim=False, auto_gain=True)
        self.assertGreater(float(np.max(np.abs(out))), float(np.max(np.abs(quiet))))
        self.assertLessEqual(float(np.max(np.abs(out))), 1.0)

    def test_process_empty(self):
        out = process(np.zeros(0, dtype=np.float32))
        self.assertEqual(len(out), 0)


if __name__ == "__main__":
    unittest.main()
