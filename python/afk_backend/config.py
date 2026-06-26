"""Filesystem paths and shared constants for the AFK backend.

The Electron side passes AFK_DATA_DIR so both processes agree on where
user data lives. When run standalone (tests, dev), we fall back to a local
.afk-data directory.
"""

import os
from pathlib import Path


def data_dir() -> Path:
    env = os.environ.get("AFK_DATA_DIR")
    if env:
        p = Path(env)
    else:
        p = Path(__file__).resolve().parents[2] / ".afk-data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def models_dir() -> Path:
    # Allow override; otherwise sit next to data dir's parent (userData/models).
    env = os.environ.get("AFK_MODELS_DIR")
    if env:
        p = Path(env)
    else:
        p = data_dir().parent / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def settings_path() -> Path:
    return data_dir() / "settings.json"


def stats_path() -> Path:
    return data_dir() / "statistics.json"


# ---- Model identifiers (used from Phase 2/4 onward) ----
PARAKEET_MODEL = "nemo-parakeet-tdt-0.6b-v3"
GEMMA_SHORT_MODEL = "gemma-3-270m-it"
GEMMA_LONG_MODEL = "gemma-3n-e2b-it"

# Default word-count threshold for short vs. long clarification model.
DEFAULT_WORD_THRESHOLD = 60

# Typing speed assumption for "time saved" stats (words per minute).
TYPING_WPM = 40
