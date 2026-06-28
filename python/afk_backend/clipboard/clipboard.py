"""Clipboard integration and synthetic paste.

Provides the primitives the dictation and Clarify flows need:
  * read/write the clipboard (unicode-safe)
  * synthetic paste (Ctrl+V) into the focused application
  * capture the current selection (Ctrl+C) for Clarify
  * replace the current selection with new text

We deliberately preserve and restore the user's clipboard around
selection-capture so dictation never clobbers what they had copied.
"""

import threading
import time
import uuid
from typing import Optional

try:
    import pyperclip
except Exception as exc:  # pragma: no cover
    pyperclip = None
    _PYPERCLIP_ERR = exc
else:
    _PYPERCLIP_ERR = None

try:
    from pynput.keyboard import Controller, Key
except Exception as exc:  # pragma: no cover
    Controller = None
    Key = None
    _PYNPUT_ERR = exc
else:
    _PYNPUT_ERR = None

from .. import logutil

# Small delays let the target app observe clipboard changes / key events.
_CLIPBOARD_SETTLE = 0.04
_KEY_SETTLE = 0.02


class Clipboard:
    def __init__(self) -> None:
        self._kb = Controller() if Controller else None
        self._lock = threading.Lock()

    # ---- raw clipboard ----
    def get_text(self) -> str:
        if pyperclip is None:
            raise RuntimeError(f"pyperclip unavailable: {_PYPERCLIP_ERR}")
        try:
            return pyperclip.paste() or ""
        except Exception as exc:  # noqa: BLE001
            logutil.warn(f"clipboard read failed: {exc}")
            return ""

    def set_text(self, text: str) -> None:
        if pyperclip is None:
            raise RuntimeError(f"pyperclip unavailable: {_PYPERCLIP_ERR}")
        pyperclip.copy(text if text is not None else "")

    # ---- synthetic key events ----
    def _tap_combo(self, modifier, letter: str) -> None:
        if self._kb is None:
            raise RuntimeError(f"pynput unavailable: {_PYNPUT_ERR}")
        with self._lock:
            self._kb.press(modifier)
            self._kb.press(letter)
            time.sleep(_KEY_SETTLE)
            self._kb.release(letter)
            self._kb.release(modifier)

    def paste(self) -> None:
        """Send Ctrl+V to the focused window."""
        self._tap_combo(Key.ctrl, "v")

    def _copy(self) -> None:
        self._tap_combo(Key.ctrl, "c")

    # ---- high-level flows ----
    def paste_text(self, text: str, restore: bool = False) -> bool:
        """Put `text` on the clipboard and paste it. Optionally restore prior."""
        if not text:
            return False
        prior = self.get_text() if restore else None
        self.set_text(text)
        time.sleep(_CLIPBOARD_SETTLE)
        self.paste()
        if restore:
            time.sleep(_CLIPBOARD_SETTLE)
            try:
                self.set_text(prior or "")
            except Exception:
                pass
        return True

    def capture_selection(self) -> str:
        """Copy the current selection and return it, restoring the clipboard.

        Returns '' if nothing is selected (clipboard unchanged by the copy).
        """
        prior = self.get_text()
        sentinel = f"__AFK_NO_SELECTION_{uuid.uuid4().hex}__"
        try:
            self.set_text(sentinel)
            time.sleep(_CLIPBOARD_SETTLE)
            self._copy()
            time.sleep(_CLIPBOARD_SETTLE)
            selected = self.get_text()
        finally:
            # Restore the user's original clipboard contents.
            try:
                self.set_text(prior)
            except Exception:
                pass
        return "" if selected == sentinel else selected

    def replace_selection(self, text: str) -> bool:
        """Replace the currently selected text by pasting over it."""
        return self.paste_text(text, restore=True)
