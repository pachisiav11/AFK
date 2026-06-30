# AFK Architecture

## Process model

AFK is two cooperating processes:

1. **Electron** — owns the window/UI, system tray, global hotkeys,
   auto-launch, and packaging. It is the parent process.
2. **Python backend** — owns audio capture, model inference, clipboard, stats,
   and settings. It is spawned as a hidden child (`windowsHide: true`) so no
   console window ever appears.

## IPC: newline-delimited JSON-RPC

All cross-process communication is plain JSON, one message per line, over the
Python process's stdin/stdout. stderr is reserved for logs.

| Direction | Shape |
|-----------|-------|
| Electron → Python (request) | `{"id": N, "method": "...", "params": {...}}` |
| Python → Electron (response) | `{"id": N, "result": ...}` or `{"id": N, "error": {...}}` |
| Python → Electron (event) | `{"event": "...", "data": {...}}` |

Requests are dispatched on a small thread pool in the backend so long-running
inference never blocks the read loop. The Electron side (`PythonBridge`)
tracks pending requests by id, applies timeouts, and auto-restarts the backend
if it crashes.

### Renderer boundary

The renderer is fully sandboxed (`contextIsolation: true`,
`nodeIntegration: false`). It can only reach the backend through the
`window.afk` object defined in `preload.js`, which forwards to the main process
over Electron IPC, which forwards to Python. Three hops, one whitelist.

## Method table

The backend exposes an explicit, auditable method table (see
`afk_backend/app.py`):

- `ping` → `{pong: true}`
- `get_info` → version, python, platform, model status, paths
- `get_settings` → full settings object
- `update_settings` → merge a patch, persist, emit `settings_updated`
- `list_methods` → introspection
- `start_recording` / `stop_recording` → push-to-talk / toggle control
- `transcribe` → run Parakeet STT on captured audio, emit result
- `clarify` → run Gemma grammar-correction on selected text, replace in place
- `cancel` → abort an in-flight recording, transcription, or clarify without pasting
- `get_statistics` → local usage metrics
- `list_microphones` → enumerate available audio input devices

## Settings & data

User data lives in Electron's `userData` directory (survives updates):

```
userData/
├── data/
│   ├── settings.json
│   └── statistics.json
├── models/        (downloaded model weights — gitignored)
└── logs/
```

The Electron side passes `AFK_DATA_DIR` to the backend so both processes agree
on locations.

## Extensibility

The method-table + service-container design means new capabilities
(translation, rewrite modes, custom prompts, additional models) are added by
registering new methods and services without touching the transport layer.
