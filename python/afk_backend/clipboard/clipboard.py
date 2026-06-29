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

# Delays let Electron/Chromium and sandboxed text boxes observe clipboard
# changes before AFK restores or touches the clipboard again.
_CLIPBOARD_SETTLE = 0.08
_KEY_SETTLE = 0.02
_PASTE_SETTLE = 0.25


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
        time.sleep(_PASTE_SETTLE)
        if restore:
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
        return self.paste_text(text, restore=False)

    def paste_or_copy(self, text: str) -> str:
        """Paste immediately; copy only if synthetic paste fails.

        Chromium/Electron text boxes often do not expose a normal Win32 caret,
        so textbox detection is too fragile for dictation. Keep the transcript
        on the clipboard after Ctrl+V so a missed synthetic paste still has an
        immediate manual fallback.
        """
        if not text:
            return "empty"
        try:
            self.paste_text(text, restore=False)
            return "pasted"
        except Exception as exc:  # noqa: BLE001
            logutil.warn(f"paste failed; copying instead: {exc}")
            self.set_text(text)
            return "copied"


def active_text_target() -> bool:
    """Best-effort Windows check for whether the foreground focus has a caret."""
    try:
        import ctypes

        return _active_text_target_windows(ctypes)
    except Exception:
        return False


def _active_text_target_windows(ctypes_module) -> bool:
    try:
        from ctypes import wintypes

        class RECT(ctypes_module.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        class GUITHREADINFO(ctypes_module.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("hwndActive", wintypes.HWND),
                ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND),
                ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND),
                ("hwndCaret", wintypes.HWND),
                ("rcCaret", RECT),
            ]

        user32 = ctypes_module.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        thread_id = user32.GetWindowThreadProcessId(hwnd, None)
        if not thread_id:
            return False

        info = GUITHREADINFO()
        info.cbSize = ctypes_module.sizeof(GUITHREADINFO)
        if not user32.GetGUIThreadInfo(thread_id, ctypes_module.byref(info)):
            return False
        return bool(info.hwndCaret)
    except Exception:
        return False
