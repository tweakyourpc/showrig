"""Persistent render jobs with process-group cancellation and exclusive ownership."""
from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path


def write_json(path: Path, data: dict) -> None:
    """Atomically replace a JSON document without exposing partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n")
    temp.replace(path)


class Jobs:
    """Own at most one renderer across processes sharing a project library."""

    def __init__(self, projects: Path):
        self.root = projects / ".jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.guard = threading.RLock()
        self.process = None
        self.active = None
        self.cancelled = False
        self.lock = None

    def read(self, job_id: str) -> dict:
        """Read durable status, including interrupted jobs from previous sessions."""
        if not job_id.isalnum() or len(job_id) != 32:
            raise FileNotFoundError("Unknown render job.")
        data = json.loads((self.root / f"{job_id}.json").read_text())
        if data["status"] in ("starting", "running") and data.get("pid"):
            try:
                os.kill(data["pid"], 0)
            except ProcessLookupError:
                data.update(status="interrupted", error="The renderer stopped. Your previous export is safe; render again.")
        data["elapsed"] = round((data.get("finished") or time.time()) - data["started"], 1)
        return data

    def latest(self, project: str) -> dict | None:
        """Find the latest job belonging to a film."""
        for path in sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            data = self.read(path.stem)
            if data["project"] == project:
                return data
        return None

    def start(self, project: Path, mode: str) -> dict:
        """Start a worker while retaining the library-wide render lock."""
        with self.guard:
            if self.process is not None:
                raise ValueError("A film is already rendering. Wait for it or cancel it first.")
            lock = (self.root / "render.lock").open("a")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock.close()
                raise ValueError("Another Showrig instance is rendering. Wait for it to finish.")
            job_id = uuid.uuid4().hex
            status = {"id": job_id, "project": project.name, "mode": mode, "status": "starting",
                      "stage": "Preparing", "started": time.time(), "completedStages": 0, "totalStages": 8}
            path = self.root / f"{job_id}.json"
            write_json(path, status)
            env = {**os.environ, "PYTHONUNBUFFERED": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
            env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent) + os.pathsep + env.get("PYTHONPATH", "")
            try:
                with (self.root / f"{job_id}.log").open("w") as log:
                    process = subprocess.Popen([sys.executable, "-m", "showrig.worker", str(project), str(path), mode],
                                               stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
            except OSError:
                lock.close()
                raise
            self.lock, self.process, self.active, self.cancelled = lock, process, job_id, False
            threading.Thread(target=self._watch, args=(process, job_id), daemon=True).start()
            return status

    def _watch(self, process: subprocess.Popen, job_id: str) -> None:
        """Reap the process and finalize failure or cancellation status."""
        code = process.wait()
        with self.guard:
            path = self.root / f"{job_id}.json"
            data = json.loads(path.read_text())
            if self.cancelled:
                data.update(status="cancelled", stage="Cancelled", finished=time.time())
            elif code and data["status"] not in ("failed", "succeeded"):
                data.update(status="failed", error="The renderer stopped. Open the render log for details.", finished=time.time())
            write_json(path, data)
            self.process = self.active = None
            self.lock.close()
            self.lock = None

    def cancel(self, job_id: str) -> dict:
        """Stop the worker and every media process it launched."""
        with self.guard:
            if self.active != job_id or self.process is None:
                return self.read(job_id)
            self.cancelled = True
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            process = self.process
            threading.Thread(target=self._kill_later, args=(process,), daemon=True).start()
            return {**self.read(job_id), "status": "cancelling"}

    @staticmethod
    def _kill_later(process: subprocess.Popen) -> None:
        """Bound cancellation even when an external renderer ignores SIGTERM."""
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def close(self) -> None:
        """Cancel owned work when the web service shuts down."""
        if self.active:
            self.cancel(self.active)
