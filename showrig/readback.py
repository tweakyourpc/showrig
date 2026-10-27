"""Read a FilmCraft project back: every clip with its beat id, track, frames, label and an effects fingerprint.

Used twice: right after a build, to record in the manifest the state Showrig left the project in, and later by
`showrig diff` / reconcile, to see what a person (or an agent) changed since.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from . import tools

TICKS = 254016000000
ID = re.compile(r"^(music|[A-Za-z0-9_-]+/[a-z]+[0-9]*)$")


def beat_id(name: str) -> str | None:
    """The stable id at the front of a clip name ("clip/shot1 · clip.mp4"), or None for a clip a person added."""
    head = (name or "").split(" · ", 1)[0].strip()
    return head if ID.match(head) else None


def fingerprint(effects) -> str:
    return hashlib.sha256(json.dumps(effects, sort_keys=True).encode()).hexdigest()[:16]


def _cli(project: Path, *args: str) -> str:
    cli = tools.filmcraft()
    if not cli:
        raise SystemExit("reading the project needs the FilmCraft CLI (set FILMCRAFT_CLI)")
    r = subprocess.run([cli, "--project", str(project), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"FilmCraft could not read {project.name}: {r.stderr.strip()[-300:]}")
    return r.stdout


def read(project: Path, fps: int) -> dict:
    """Clips keyed by FilmCraft clip id, plus markers, from `filmcraft-cli inspect sequence`."""
    seq = json.loads(_cli(project, "inspect", "sequence"))
    per_frame = TICKS // fps
    clips = {}
    for kind, prefix in (("video", "V"), ("audio", "A")):
        for n, track in enumerate(seq[kind], 1):
            for it in track["items"]:
                clips[it["clip"]] = {
                    "clip": it["clip"], "id": beat_id(it.get("name", "")), "name": it.get("name", ""),
                    "track": f"{prefix}{n}", "track_name": track.get("name"), "item": it.get("item"),
                    "start_f": it["startFrame"], "dur_f": it["endFrame"] - it["startFrame"],
                    "in_f": round(it.get("sourceIn", 0) / per_frame), "label": it.get("label"),
                    "enabled": it.get("enabled", True), "gain": it.get("gainDb", 0.0), "speed": it.get("speed", 1.0),
                    "fx": fingerprint(it.get("effects", [])),
                }
    markers = [{"name": m.get("name"), "start_f": round(m.get("start", 0) / per_frame), "comment": m.get("comment"),
                "color": m.get("color")} for m in seq.get("markers", [])]
    return {"clips": clips, "markers": markers}


def captions(project: Path) -> list[dict] | None:
    """The caption track as cues (text, start and end in seconds), via a temporary SRT export; None if none."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "c.srt"
        cli = tools.filmcraft()
        r = subprocess.run([cli, "--project", str(project), "exec", "captions.export",
                            json.dumps({"path": str(out), "track": "C1"})], capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            return None
        return parse_srt(out.read_text())


def parse_srt(text: str) -> list[dict]:
    def secs(t: str) -> float:
        h, m, rest = t.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(rest)
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        if len(lines) >= 3 and "-->" in lines[1]:
            a, b = (x.strip() for x in lines[1].split("-->"))
            cues.append({"text": " ".join(lines[2:]).strip(), "start": round(secs(a), 3), "end": round(secs(b), 3)})
    return cues
