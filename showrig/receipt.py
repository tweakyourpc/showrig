"""A build receipt: what was built, from which source, on what machine, and how long each stage took.

  showrig receipt <film> [--doctor report.json] [--out receipt.json]

It records the Showrig revision, the tool versions (or a deep doctor report, when given), the plan's
shape, a SHA-256 for every output, each output's media details, the stage timings of the last full
build, and a contact sheet of the film (out/<name>-contact.jpg).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

from . import __version__, capabilities
from .project import Film

SCHEMA = 1


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def revision() -> dict:
    repo = Path(__file__).resolve().parents[1]
    def git(*args: str) -> str | None:
        try:
            r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout.strip() if r.returncode == 0 else None
    commit = git("rev-parse", "HEAD") if (repo / ".git").exists() else None
    if commit is None:
        return {"version": __version__, "commit": None, "modified": None}
    status = git("status", "--porcelain", "--untracked-files=no")
    return {"version": __version__, "commit": commit, "modified": bool(status)}


def media(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,codec_name,width,height,r_frame_rate,pix_fmt,sample_rate,channels"
                          ":format=duration,bit_rate", "-of", "json", str(path)], capture_output=True, text=True,
                         timeout=60)
    data = json.loads(out.stdout or "{}")
    return {"duration": float(data.get("format", {}).get("duration") or 0),
            "bit_rate": int(data.get("format", {}).get("bit_rate") or 0), "streams": data.get("streams", [])}


def contact_sheet(video: Path, out: Path, seconds: float) -> Path:
    step = max(1.0, seconds / 24)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
                    f"fps=1/{step:.3f},scale=384:-1,tile=6x4", "-frames:v", "1", "-q:v", "3", str(out)],
                   check=True, timeout=300)
    return out


def build(film: Film, doctor: Path | None = None) -> dict:
    plan = json.loads((film.work / "plan.json").read_text())
    outputs = sorted(p for p in film.out.iterdir() if p.is_file() and p.suffix in (".mp4", ".fcproj", ".srt")
                     and ".rendering." not in p.name and not p.name.endswith("-contact.jpg"))
    film_mp4 = film.out / f"{film.name}.mp4"
    timing = film.work / "last-build.json"
    env = json.loads(doctor.read_text()) if doctor else capabilities.report("studio", deep=False)
    rec = {
        "schema": SCHEMA, "kind": "showrig-receipt", "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "film": {"title": film.board["title"], "format": film.fmt, "quality": film.style.get("quality")},
        "source": revision(),
        "environment": {"deep": env.get("deep"), "host": env.get("host"),
                        "capabilities": {c["id"]: {k: c[k] for k in ("state", "version", "evidence")}
                                         for c in env.get("capabilities", [])}},
        "plan": {"duration": plan["duration"],
                 **{k: len(plan[k]) for k in ("video", "titles", "narration", "captions", "stage", "images") if k in plan}},
        "build": json.loads(timing.read_text()) if timing.exists() else None,
        "outputs": {p.name: {"sha256": sha256(p), "bytes": p.stat().st_size,
                             **({"media": media(p)} if p.suffix == ".mp4" else {})} for p in outputs},
    }
    if film_mp4.exists():
        rec["contact_sheet"] = contact_sheet(film_mp4, film.out / f"{film.name}-contact.jpg",
                                             plan["duration"]).name
    return rec
