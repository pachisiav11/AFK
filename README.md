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
| 2 | Microphone capture + Parakeet STT pipeline | ⏳ |
| 3 | Clipboard insertion, push-to-talk, toggle recording | ⏳ |
| 4 | Clarify pipeline + automatic model routing | ⏳ |
| 5 | Statistics, settings, local storage | ⏳ |
| 6 | UI polish, performance, packaging, Windows installer | ⏳ |

## Architecture

```
Electron (UI, tray, global hotkeys, packaging)
    │  JSON-RPC over stdio (newline-delimited)
    ▼
Python backend
    ├── audio          (capture, VAD, noise suppression)
    ├── transcription  (Parakeet 0.6B v3, ONNX/CPU)
    ├── clarify        (Gemma 3 270M / Gemma 3n E2B, GGUF/CPU)
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

Requirements: **Node 18+**, **Python 3.11**.

```bash
# 1. Install Node deps
npm install

# 2. Create the Python backend venv + deps
npm run setup:python

# 3. Run in dev mode (DevTools open, verbose logging)
npm run dev
```

### Models

Models are large and are **never committed to git**. They download lazily on
first use into your user-data `models/` directory. Identifiers live in
[`python/afk_backend/config.py`](python/afk_backend/config.py).

## Building the installer

```bash
npm run dist   # produces a one-click NSIS .exe in installer/dist/
```

## License

MIT
