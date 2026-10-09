"""Run sandbox jobs in short-lived, resource-limited child processes.

Each job starts a fresh interpreter in isolated mode (``-I -S -B``) with an
empty environment, so nothing from the server process (environment
variables, open connections, memory) is visible to submitted SQL. A
semaphore caps how many workers run at once, and a hard timeout kills a
worker that overruns its own deadline.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

WORKER_PATH = Path(__file__).with_name("worker.py")
MAX_OUTPUT_BYTES = 16_000_000
KILL_GRACE_SECONDS = 2.0


class SandboxBusy(RuntimeError):
    """Raised when every sandbox slot stays busy for longer than the queue timeout."""


def failure(kind: str, message: str) -> dict:
    return {"ok": False, "error": {"type": kind, "message": message, "code": None}}


def _describe_signal(returncode: int) -> str:
    try:
        name = signal.Signals(-returncode).name
    except ValueError:
        name = f"signal {-returncode}"
    if name in ("SIGXCPU", "SIGKILL"):
        return f"The query used too much CPU time or memory and the sandbox stopped it ({name})."
    return f"The sandbox process stopped unexpectedly ({name})."


class SandboxRunner:
    def __init__(
        self,
        *,
        max_concurrency: int = 4,
        queue_timeout: float = 10.0,
        python: str | None = None,
    ) -> None:
        self._slots = threading.BoundedSemaphore(max(1, max_concurrency))
        self.queue_timeout = queue_timeout
        self.python = python or sys.executable

    def run(self, job: dict, *, timeout_ms: int) -> dict:
        job = dict(job)
        job["limits"] = {**job.get("limits", {}), "timeout_ms": timeout_ms}
        payload = json.dumps(job, separators=(",", ":")).encode()
        if not self._slots.acquire(timeout=self.queue_timeout):
            raise SandboxBusy("Every sandbox slot is busy. Try again in a moment.")
        try:
            proc = subprocess.run(
                [self.python, "-I", "-S", "-B", str(WORKER_PATH)],
                input=payload,
                capture_output=True,
                timeout=timeout_ms / 1000 + KILL_GRACE_SECONDS,
                cwd="/",
                env={"LC_ALL": "C.UTF-8", "PATH": os.defpath},
                check=False,
            )
        except subprocess.TimeoutExpired:
            return failure("Timeout", f"The sandbox did not finish within {timeout_ms} ms and was stopped.")
        finally:
            self._slots.release()
        if proc.returncode < 0:
            return failure("ResourceLimit", _describe_signal(proc.returncode))
        if proc.returncode != 0 or not proc.stdout:
            detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or ["no output"]
            return failure("SandboxError", f"The sandbox failed: {detail[0]}")
        if len(proc.stdout) > MAX_OUTPUT_BYTES:
            return failure("SandboxError", "The sandbox produced more output than allowed.")
        try:
            return json.loads(proc.stdout)
        except ValueError:
            return failure("SandboxError", "The sandbox returned malformed output.")
