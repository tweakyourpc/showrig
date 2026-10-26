"""A Showrig film folder: the storyboard, the user's assets, generated work and outputs.

    my-film/
      showrig.json      the storyboard (written by the wizard, safe to hand-edit)
      STORYBOARD.md     a readable copy for sign-off
      assets/           your clips, voice files and music
      work/             everything Showrig generates; any of it can be deleted and rebuilt
      out/              <slug>.fcproj, <slug>.mp4, <slug>.srt
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import fcntl
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

SCHEMA = 1


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "film"


def probe(path: Path) -> dict:
    """Width, height, fps and duration of a media file (audio-only files have no width)."""
    out = subprocess.check_output(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe,data", "-show_entries",
                                   "stream=codec_type,codec_name,width,height,r_frame_rate:format=duration,format_name",
                                   "-of", "json", str(path)], text=True, timeout=30)
    data = json.loads(out)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    num, _, den = video.get("r_frame_rate", "0/1").partition("/")
    duration = float(data.get("format", {}).get("duration") or 0)
    return {"width": video.get("width"), "height": video.get("height"),
            "fps": round(int(num) / int(den or 1), 3) if video else None,
            "duration": duration, "still": bool(video and not duration),
            "audio": any(s.get("codec_type") == "audio" for s in data.get("streams", []))}


@contextmanager
def film_lock(root: Path):
    """Prevent concurrent producers from deleting or replacing each other's work."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".render.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("This film is already rendering. Wait for it or cancel that render.")
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


@dataclass
class Film:
    root: Path
    board: dict

    @classmethod
    def load(cls, root: Path) -> Film:
        root = root.resolve()
        path = root / "showrig.json"
        if not path.exists():
            raise SystemExit(f"{path} not found; run `showrig new {root}` first")
        board = json.loads(path.read_text())
        if board.get("showrig") != SCHEMA:
            raise SystemExit(f"{path}: unsupported storyboard version {board.get('showrig')}")
        return cls(root, board)

    def save(self) -> None:
        (self.root / "showrig.json").write_text(json.dumps(self.board, indent=2) + "\n")

    # Layout -----------------------------------------------------------------------------
    @property
    def work(self) -> Path:
        return self.root / "work"

    @property
    def out(self) -> Path:
        return self.root / "out"

    @property
    def name(self) -> str:
        return slug(self.board["title"])

    @property
    def fmt(self) -> dict:
        return self.board["format"]

    @property
    def style(self) -> dict:
        return self.board["style"]

    def asset(self, rel: str) -> Path:
        """User paths are relative to the film folder unless absolute."""
        p = Path(rel).expanduser()
        return p if p.is_absolute() else self.root / p

    def scenes(self, *kinds: str) -> list[dict]:
        return [s for s in self.board["scenes"] if not kinds or s["kind"] in kinds]

    # Incremental builds ----------------------------------------------------------------
    def fingerprint(self, *parts) -> str:
        """Hash JSON-able inputs; file paths contribute their size and mtime."""
        def norm(x):
            if isinstance(x, Path):
                st = x.stat() if x.exists() else None
                return [str(x), st.st_size if st else None, st.st_mtime_ns if st else None]
            if isinstance(x, dict):
                return {k: norm(v) for k, v in sorted(x.items())}
            if isinstance(x, (list, tuple)):
                return [norm(v) for v in x]
            return x
        return hashlib.sha256(json.dumps(norm(parts), sort_keys=True).encode()).hexdigest()[:16]

    def fresh(self, output: Path, key: str) -> bool:
        stamp = self.work / ".stamps" / (output.relative_to(self.root).as_posix().replace("/", "__") + ".key")
        return output.exists() and stamp.exists() and stamp.read_text() == key

    def stamp(self, output: Path, key: str) -> None:
        stamp = self.work / ".stamps" / (output.relative_to(self.root).as_posix().replace("/", "__") + ".key")
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(key)

    def log(self, name: str) -> Path:
        p = self.work / "logs" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


def run(cmd: list, log: Path | None = None, **kw) -> subprocess.CompletedProcess:
    """Run a tool, keep its output in the film's log folder, and fail loudly with the tail of it."""
    if Path(str(cmd[0])).name == "ffmpeg":
        cmd = [cmd[0], "-protocol_whitelist", "file,pipe,data", *cmd[1:]]
    res = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    if log:
        log.write_text(f"$ {' '.join(map(str, cmd))}\n{res.stdout}\n{res.stderr}")
    if res.returncode:
        tail = (res.stderr or res.stdout)[-1500:]
        raise SystemExit(f"{Path(str(cmd[0])).name} failed ({res.returncode}){f', see {log}' if log else ''}:\n{tail}")
    return res
