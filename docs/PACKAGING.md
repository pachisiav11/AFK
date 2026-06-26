# Packaging AFK

AFK ships as a one-click **NSIS** installer built with `electron-builder`.

```bash
npm run dist     # -> installer/dist/AFK Setup <version>.exe
npm run pack     # -> installer/dist/win-unpacked/ (unpacked, for debugging)
```

Config lives in the `build` field of [`package.json`](../package.json).

## What the installer contains

| Component | Bundled? | Location in install |
|-----------|----------|---------------------|
| Electron runtime + UI | ✅ | `resources/app.asar` |
| Python backend **source** | ✅ | `resources/python/` |
| llama.cpp `llama-server` (AVX2 CPU build) | ✅ | `resources/vendor/llama.cpp/` |
| App icons | ✅ | bundled |
| Python interpreter + ML deps (torch, NeMo, onnx…) | ❌ provisioned | see below |
| Model weights (Parakeet, Gemma) | ❌ downloaded | user-data `models/` |

The icons are generated from a script (no binary blobs in git):

```bash
python/.venv/Scripts/python scripts/make_icons.py
```

## Why models and ML deps aren't bundled

The full inference stack (PyTorch + NeMo + onnxruntime) is ~3 GB, and the
models are another ~6 GB. Shipping those inside the installer would make it
enormous. Like most local-AI desktop apps, AFK provisions them separately:

- **Models** download (or are placed) into the user-data `models/` directory:
  `models/parakeet-v3/` (ASR) and `models/clarify/` (Gemma GGUF). They are
  resolved at runtime by [`config.py`](../python/afk_backend/config.py) and are
  **never committed to git**.
- **Python deps** install into `python/.venv` via `npm run setup:python`.

### Path resolution (dev vs. packaged)

`config.py` and `python-locator.js` check, in order:

1. Environment overrides (`AFK_DATA_DIR`, `AFK_MODELS_DIR`, `AFK_ASR_DIR`,
   `AFK_CLARIFY_DIR`, `AFK_LLAMA_SERVER`, `AFK_RESOURCES`).
2. The repo's `models/` and `vendor/` (development).
3. The packaged `resources/` and the OS user-data dir (production).

Electron passes `AFK_RESOURCES = process.resourcesPath` so the backend finds the
bundled `llama-server` when packaged.

## Producing a fully self-contained installer

To ship an installer that runs with **zero prerequisites** on the target
machine, bundle the Python runtime as well. Two supported approaches:

1. **Bundle the venv** — add `python/.venv` to `extraResources` (drop the
   `!.venv/**` filter). Simplest, but the installer grows by the size of the
   dependency set (multi-GB with PyTorch). The locator already prefers
   `resources/python/.venv` when present.
2. **Embeddable Python + first-run install** — ship a trimmed embeddable
   CPython and run `setup-python` on first launch. Smaller installer, requires
   network on first run.

Without either, the packaged app falls back to a system Python 3.11/3.12
(see `python-locator.js`) — fine for developer machines, not for end users.

## No console windows

Every child process (the Python backend and each `llama-server`) is spawned
with `windowsHide` / `CREATE_NO_WINDOW`, so no terminal ever appears — a hard
requirement from the project spec.
