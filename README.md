# AFK

**Privacy-first, fully-local AI speech-to-text for Windows.**

AFK turns your voice into polished text without ever sending audio to the cloud.
Hold a hotkey, speak, release — your words are transcribed locally with
[Parakeet 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) and
optionally cleaned up by a local Gemma model before being pasted into whatever
app you're using.

> Everything runs on your machine. No accounts, no API keys, no telemetry.

---

## Status

This repository is built **phase by phase**. Current state:

| Phase | Scope | Status |
|------|-------|--------|
| 1 | Project setup, Electron shell, Python backend, IPC, installer | ✅ |
| 2 | Microphone capture + Parakeet STT pipeline | ✅ |
| 3 | Clipboard insertion, push-to-talk, toggle recording | ✅ |
| 4 | Clarify pipeline + automatic model routing | ✅ |
| 5 | Statistics, settings, local storage | ✅ |
| 6 | UI polish, performance, packaging, Windows installer | ✅ |

## Architecture

```
Electron (UI, tray, global hotkeys, packaging)
    │  JSON-RPC over stdio (newline-delimited)
    ▼
Python backend
    ├── audio          (capture, VAD, noise suppression)
    ├── transcription  (Parakeet 0.6B v3, ONNX/CPU)
    ├── clarify        (Gemma 3 270M / Gemma 4 E2B, GGUF/CPU)
    ├── clipboard      (selection replacement, paste)
    ├── statistics     (local usage metrics)
    └── settings       (JSON-backed preferences)
```

The Electron `main` process spawns the Python backend as a hidden child
process and talks to it over newline-delimited JSON-RPC on stdin/stdout
(see [`electron/python-bridge.js`](electron/python-bridge.js) and
[`python/afk_backend/rpc.py`](python/afk_backend/rpc.py)). The renderer only
ever touches the whitelisted `window.afk` bridge from
[`electron/preload.js`](electron/preload.js).

## Development

Requirements: **Node 18+**, **Python 3.11 or 3.12**.

```bash
# 1. Install Node deps
npm install

# 2. Create the Python backend venv + deps
npm run setup:python

# 3. Optional: install local grammar-correction models + llama-server
npm run setup:clarify

# 4. Run in dev mode (DevTools open, verbose logging)
npm run dev
```

### Speech-to-text engines

AFK supports two interchangeable Parakeet 0.6B v3 backends, auto-selected at
load time (see [`config.select_asr_engine`](python/afk_backend/config.py)):

| Engine | When used | Notes |
|--------|-----------|-------|
| **ONNX** (default) | no `.nemo` present | `onnx-asr`, int8, ~2 GB RAM, lightest |
| **NeMo** (official) | a `.nemo` checkpoint is present | NVIDIA NeMo + PyTorch, official weights |

To use the official NVIDIA checkpoint, drop
`parakeet-tdt-0.6b-v3.nemo` into `models/parakeet-v3/` and install the toolkit:

```bash
python/.venv/Scripts/python -m pip install "nemo_toolkit[asr]"
```

For the ONNX engine, the int8 files download lazily from Hugging Face on first
use (or place them in `models/parakeet-v3/`). Override paths with
`AFK_NEMO_PATH`, `AFK_ASR_DIR`, or force an engine with `AFK_ASR_ENGINE`.

### Clarify / Grammar Correction

AFK's grammar-correction commands use two local GGUF models served by the
official `llama.cpp` `llama-server` binary:

| Purpose | Source | File |
|---------|--------|------|
| Short corrections | `ggml-org/gemma-3-270m-GGUF` | `gemma-3-270m-Q8_0.gguf` |
| Long corrections | `ggml-org/gemma-4-E2B-it-GGUF` | `gemma-4-E2B-it-Q8_0.gguf` |
| Runtime | `ggml-org/llama.cpp` GitHub releases | Windows CPU x64 `llama-server.exe` |

Recommended Windows install:

```powershell
npm run setup:python
npm run setup:clarify
```

Manual equivalent:

```powershell
New-Item -ItemType Directory -Force -Path ".\models\clarify" | Out-Null
New-Item -ItemType Directory -Force -Path ".\vendor\llama.cpp" | Out-Null

.\python\.venv\Scripts\python.exe -m pip install -U huggingface_hub
.\python\.venv\Scripts\huggingface-cli.exe download ggml-org/gemma-3-270m-GGUF gemma-3-270m-Q8_0.gguf --local-dir ".\models\clarify"
.\python\.venv\Scripts\huggingface-cli.exe download ggml-org/gemma-4-E2B-it-GGUF gemma-4-E2B-it-Q8_0.gguf --local-dir ".\models\clarify"
```

Then download the latest Windows CPU x64 `llama.cpp` release from
`https://github.com/ggml-org/llama.cpp/releases`, extract it, and copy
`llama-server.exe` to `vendor\llama.cpp\llama-server.exe`.

### Models

Models are large and are **never committed to git** (see `.gitignore`). They
live in `models/` or your user-data directory.

## Building the installer

```bash
python/.venv/Scripts/python scripts/make_icons.py   # generate app icons
npm run dist                                         # one-click NSIS .exe in installer/dist/
```

The installer bundles the Electron app, the Python backend source, and the
AVX2 `llama-server` binary. Model weights and the Python ML dependencies are
provisioned separately (they total ~9 GB) — see
[docs/PACKAGING.md](docs/PACKAGING.md) for the full bundling strategy, including
how to produce a fully self-contained installer.

## Hotkeys (defaults — all remappable in Settings)

| Action | Default | Behaviour |
|--------|---------|-----------|
| Push-to-talk | `Ctrl+Space` (hold) | Hold to record, release to transcribe + paste |
| Toggle recording | `Ctrl+Shift+Space` | Press to start/stop; auto-clarifies before paste |
| Clarify | `Ctrl+Alt+K` | Polish selected text (or clipboard) in place |

> The spec's `Ctrl+Fn` combos aren't usable — the `Fn` key is handled in
> keyboard firmware and isn't visible to software — so AFK ships reliable,
> fully-remappable defaults instead.

## License

MIT
