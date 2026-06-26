"""Newline-delimited JSON-RPC server over stdin/stdout.

Each inbound line is a request: {"id": N, "method": "...", "params": {...}}
Each outbound line is either a response (has "id") or an event (has "event").

Requests are dispatched on worker threads so a slow call (model inference)
never blocks the read loop or other in-flight requests.
"""

import sys
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

from . import logutil

_write_lock = threading.Lock()


def _write_message(obj: Dict[str, Any]) -> None:
    """Write a single protocol message to stdout, atomically."""
    data = json.dumps(obj, ensure_ascii=False) + "\n"
    with _write_lock:
        sys.stdout.write(data)
        sys.stdout.flush()


def emit_event(event: str, data: Optional[Dict[str, Any]] = None) -> None:
    """Push an unsolicited event to the Electron side."""
    _write_message({"event": event, "data": data or {}})


class RpcError(Exception):
    def __init__(self, message: str, code: int = -1):
        super().__init__(message)
        self.code = code
        self.message = message


class RpcServer:
    def __init__(
        self,
        dispatch: Callable[[str, Dict[str, Any]], Any],
        on_started: Optional[Callable[[], None]] = None,
        max_workers: int = 4,
    ):
        self._dispatch = dispatch
        self._on_started = on_started
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        self._running = True

    def serve_forever(self) -> None:
        if self._on_started:
            try:
                self._on_started()
            except Exception as exc:  # pragma: no cover - defensive
                logutil.error(f"on_started failed: {exc}")

        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                logutil.warn(f"Dropping malformed line: {line[:120]}")
                continue

            method = msg.get("method")
            if method == "shutdown":
                self._respond(msg.get("id"), {"ok": True})
                break

            self._pool.submit(self._handle, msg)

        self._running = False
        self._pool.shutdown(wait=False)

    def _handle(self, msg: Dict[str, Any]) -> None:
        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}
        try:
            result = self._dispatch(method, params)
            self._respond(msg_id, result)
        except RpcError as exc:
            self._respond_error(msg_id, exc.message, exc.code)
        except Exception as exc:  # noqa: BLE001
            logutil.error(f"Error handling '{method}': {exc}")
            self._respond_error(msg_id, str(exc), -32000)

    def _respond(self, msg_id: Any, result: Any) -> None:
        if msg_id is None:
            return
        _write_message({"id": msg_id, "result": result})

    def _respond_error(self, msg_id: Any, message: str, code: int) -> None:
        if msg_id is None:
            return
        _write_message({"id": msg_id, "error": {"code": code, "message": message}})
