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


def local_asr_dir() -> Path:
    """Optional pre-downloaded Parakeet model directory.

    If the user places the onnx-asr model files here, we load from disk and
    skip any network download. Checked before the Hugging Face hub.

    Search order:
      1. $AFK_ASR_DIR (explicit override)
      2. <repo>/models/parakeet-v3   (handy for development)
      3. <models_dir>/parakeet-v3    (alongside other app models)
    """
    env = os.environ.get("AFK_ASR_DIR")
    if env:
        return Path(env)
    repo_local = Path(__file__).resolve().parents[2] / "models" / "parakeet-v3"
    if repo_local.exists():
        return repo_local
    return models_dir() / "parakeet-v3"


# Files onnx-asr needs for the int8 Parakeet model loaded from a local path.
LOCAL_ASR_REQUIRED = (
    "encoder-model.int8.onnx",
    "decoder_joint-model.int8.onnx",
    "nemo128.onnx",
    "vocab.txt",
    "config.json",
)

# Official NVIDIA NeMo checkpoint filename.
NEMO_CHECKPOINT = "parakeet-tdt-0.6b-v3.nemo"


def local_nemo_path() -> Path:
    """Path to a user-provided official NVIDIA .nemo checkpoint, if any.

    Search order mirrors local_asr_dir():
      1. $AFK_NEMO_PATH (explicit override; may point at the file directly)
      2. <local_asr_dir>/parakeet-tdt-0.6b-v3.nemo
    """
    env = os.environ.get("AFK_NEMO_PATH")
    if env:
        return Path(env)
    return local_asr_dir() / NEMO_CHECKPOINT


def select_asr_engine() -> tuple[str, Path | None]:
    """Decide which ASR engine to use based on what the user has provided.

    Preference:
      * If an official .nemo checkpoint is present -> ('nemo', <path>)
      * Else -> ('onnx', None)  (local int8 files or Hugging Face download)

    An explicit $AFK_ASR_ENGINE ('nemo' | 'onnx') overrides auto-detection.
    """
    forced = os.environ.get("AFK_ASR_ENGINE", "").strip().lower()
    nemo_path = local_nemo_path()
    if forced == "nemo":
        return "nemo", nemo_path
    if forced == "onnx":
        return "onnx", None
    if nemo_path.exists() and nemo_path.is_file():
        return "nemo", nemo_path
    return "onnx", None


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
