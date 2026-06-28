"""Transcription text cleanup tests."""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "python"))

from afk_backend.transcription.transcriber import clean_transcript  # noqa: E402


class TestTranscriptCleanup(unittest.TestCase):
    def test_removes_chat_template_leak_after_real_transcript(self):
        leaked = (
            "Yeah.<|im_end|> <|im_start|>user Input: Yeah.<|im_end|> "
            "<|im_start|>assistant Yeah.<|im_end|> <|im_start|>user Input: Yeah."
            "<|im_end|> <|im_start|>assistant"
        )
        self.assertEqual(clean_transcript(leaked), "Yeah.")

    def test_keeps_normal_dictation(self):
        self.assertEqual(
            clean_transcript("Send this to Keshav after the build finishes."),
            "Send this to Keshav after the build finishes.",
        )

    def test_removes_leading_roles_when_no_plain_prefix_exists(self):
        leaked = "<|im_start|>assistant Hello there.<|im_end|>"
        self.assertEqual(clean_transcript(leaked), "Hello there.")


if __name__ == "__main__":
    unittest.main()
