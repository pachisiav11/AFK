"""Thin manager for an official llama.cpp `llama-server` subprocess.

We talk to it over its local OpenAI-compatible HTTP API. This avoids the
llama-cpp-python wheels (which require AVX-512 and crash on CPUs without it);
the upstream binary ships per-microarch CPU backends and picks the right one
(AVX2) at runtime.

No third-party HTTP dependency — uses urllib from the stdlib. The server
process is launched hidden (no console window) per the app's UX requirement.
"""

import json
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import List, Optional

from .. import config, logutil

_HEALTH_TIMEOUT_S = 90


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _no_window_kwargs() -> dict:
    if sys.platform == "win32":
        # CREATE_NO_WINDOW: never flash a console window.
        return {"creationflags": 0x08000000}
    return {}


class LlamaServer:
    def __init__(self, model_path: str, n_ctx: int = 4096, n_threads: Optional[int] = None):
        self.model_path = str(model_path)
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.port: Optional[int] = None
        self.proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        with self._lock:
            if self.is_alive():
                return
            exe = config.llama_server_path()
            if not Path(exe).exists():
                raise FileNotFoundError(f"llama-server not found at {exe}")
            if not Path(self.model_path).exists():
                raise FileNotFoundError(f"model not found: {self.model_path}")

            self.port = _free_port()
            import os

            args = [
                str(exe),
                "-m", self.model_path,
                "--host", "127.0.0.1",
                "--port", str(self.port),
                "-c", str(self.n_ctx),
                "-t", str(self.n_threads or max(1, os.cpu_count() or 1)),
                "--no-webui",
                "--jinja",  # use the model's real chat template (Gemma)
            ]
            logutil.info(f"Starting llama-server on :{self.port} for {Path(self.model_path).name}")
            self.proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **_no_window_kwargs(),
            )
            self._wait_healthy()

    def _wait_healthy(self) -> None:
        deadline = time.time() + _HEALTH_TIMEOUT_S
        url = f"{self.base_url}/health"
        while time.time() < deadline:
            if not self.is_alive():
                raise RuntimeError("llama-server exited during startup")
            try:
                with urllib.request.urlopen(url, timeout=2) as r:
                    if r.status == 200 and b'"ok"' in r.read():
                        logutil.info(f"llama-server :{self.port} healthy")
                        return
            except Exception:
                pass
            time.sleep(1.0)
        raise TimeoutError("llama-server did not become healthy in time")

    def chat(self, messages: List[dict], temperature: float = 0.0, max_tokens: int = 512) -> str:
        payload = json.dumps(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
                # Disable reasoning so models like Gemma 4 output the answer
                # directly instead of spending the budget "thinking". Harmless
                # for templates that don't use this kwarg (Gemma 3 270M).
                "chat_template_kwargs": {"enable_thinking": False},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        return (data["choices"][0]["message"]["content"] or "").strip()

    def stop(self) -> None:
        with self._lock:
            if self.proc is not None:
                try:
                    self.proc.terminate()
                    try:
                        self.proc.wait(timeout=5)
                    except Exception:
                        self.proc.kill()
                except Exception:
                    pass
                self.proc = None
