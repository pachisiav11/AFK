"""Parakeet local model path detection tests."""

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "python"))

from afk_backend import config  # noqa: E402
from afk_backend.transcription.parakeet import _has_local_model_files  # noqa: E402


class TestParakeetLocalFiles(unittest.TestCase):
    def test_required_files_match_current_onnx_asr_layout(self):
        self.assertNotIn("nemo128.onnx", config.LOCAL_ASR_REQUIRED)
        self.assertIn("encoder-model.int8.onnx", config.LOCAL_ASR_REQUIRED)
        self.assertIn("decoder_joint-model.int8.onnx", config.LOCAL_ASR_REQUIRED)

    def test_complete_local_dir_does_not_need_bundled_preprocessor_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in config.LOCAL_ASR_REQUIRED:
                (root / name).write_text("", encoding="utf-8")
            self.assertTrue(_has_local_model_files(root))
            self.assertFalse((root / "nemo128.onnx").exists())


if __name__ == "__main__":
    unittest.main()
