"""Phase 3 clipboard command tests without touching the real OS clipboard."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "python"))

import afk_backend.clipboard.clipboard as clipmod  # noqa: E402


class FakeClipboard(clipmod.Clipboard):
    def __init__(self, prior="old", copied=None):
        self.values = [prior]
        self.copied = copied

    def get_text(self):
        return self.values[-1]

    def set_text(self, text):
        self.values.append(text)

    def _copy(self):
        if self.copied is not None:
            self.values.append(self.copied)


class TestClipboardSelection(unittest.TestCase):
    @patch.object(clipmod.time, "sleep", lambda _s: None)
    def test_capture_selection_returns_empty_when_copy_does_not_change_clipboard(self):
        cb = FakeClipboard(prior="clipboard text", copied=None)
        self.assertEqual(cb.capture_selection(), "")
        self.assertEqual(cb.get_text(), "clipboard text")

    @patch.object(clipmod.time, "sleep", lambda _s: None)
    def test_capture_selection_returns_selected_text_and_restores_prior_clipboard(self):
        cb = FakeClipboard(prior="clipboard text", copied="selected text")
        self.assertEqual(cb.capture_selection(), "selected text")
        self.assertEqual(cb.get_text(), "clipboard text")


if __name__ == "__main__":
    unittest.main()
