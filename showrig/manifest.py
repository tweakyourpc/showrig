"""The film's manifest: what Showrig put in the FilmCraft project, beat by beat.

out/manifest.json is the contract between a build and whoever edits its project next. Every beat has a stable
id (stable across re-runs; it starts the clip's name in the project), its kind and class (native, editable in
EffectCraft, or compiled), its track, its frames, its source file and that file's SHA-256, and any lock. The
project file's own hash records the state Showrig left it in, so `showrig diff` can tell what a person changed.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import __version__, readback

# owner: None while a beat is Showrig's; "human" once a person (or an agent) edited it. Reconcile never changes a
# human or locked beat; `showrig unlock` hands one back.
from .project import Film
from .receipt import revision, sha256

SCHEMA = 1


def path(film: Film) -> Path:
    return film.out / "manifest.json"


def load(film: Film) -> dict | None:
    p = path(film)
    return json.loads(p.read_text()) if p.exists() else None


def rel(film: Film, p: str | None) -> str | None:
    """Paths inside the film folder are stored relative to it, so a copied film keeps its manifest."""
    if not p:
        return None
    q = Path(p)
    return q.relative_to(film.root).as_posix() if q.is_absolute() and q.is_relative_to(film.root) else str(q)


def write(film: Film, plan: dict, beats: list[dict], filmcraft: dict, promise: str,
          deleted: list[str] | None = None) -> dict:
    """Record a fresh build. Each beat's frames, label and effects are read back from the saved project, so the
    manifest describes the project as it really is, not only as it was asked for. Locks and deletions carried in
    the previous manifest are kept."""
    prev = load(film) or {}
    locks = {b["id"]: b["lock"] for b in prev.get("beats", []) if b.get("lock")}
    project = film.out / f"{film.name}.fcproj"
    back = readback.read(project, film.fmt["fps"])
    seen = back["clips"]
    hashes: dict[str, str] = {}
    out_beats = []
    for b in sorted(beats, key=lambda b: (b["track"], b["start_f"], b["id"])):
        src = b.get("path")
        if src and not Path(src).is_absolute():  # a beat carried over from an earlier manifest
            src = str(film.root / src)
        if src and src not in hashes and Path(src).exists():
            hashes[src] = sha256(Path(src))
        got = seen.get(b["clip"], {})
        ec = Path(src).with_suffix(".ecproj") if b["kind"] == "title" and src else None
        out_beats.append({"id": b["id"], "scene": b.get("scene"), "kind": b["kind"], "class": b["class"],
                          "track": b["track"], "name": got.get("name", b["name"]), "clip": b["clip"],
                          "item": b["item"], "start_f": got.get("start_f", b["start_f"]),
                          "dur_f": got.get("dur_f", b["dur_f"]), "in_f": got.get("in_f", b["in_f"]),
                          "label": got.get("label"), "fx": got.get("fx"), "gain": got.get("gain"),
                          "path": rel(film, src), "sha256": hashes.get(src) if src else None,
                          "ecproj": {"path": rel(film, str(ec)), "sha256": sha256(ec)} if ec and ec.exists() else None,
                          "lock": b.get("lock") or locks.get(b["id"]), "owner": b.get("owner")})
    data = {
        "schema": SCHEMA, "kind": "showrig-manifest", "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "film": film.board["title"], "name": film.name, "fps": film.fmt["fps"],
        "format": {k: film.fmt[k] for k in ("width", "height", "fps")}, "duration_f": max(
            (b["start_f"] + (b["dur_f"] or 0) for b in out_beats), default=0),
        "editable": promise,
        "project": {"path": rel(film, str(project)), "sha256": sha256(project) if project.exists() else None},
        "interchange": [rel(film, str(film.out / f"{film.name}.{ext}")) for ext in ("otio", "fcpxml")
                        if (film.out / f"{film.name}.{ext}").exists()],
        "srt": rel(film, str(film.out / f"{film.name}.srt")) if (film.out / f"{film.name}.srt").exists() else None,
        "filmcraft": filmcraft, "showrig": {"version": __version__, **revision()},
        "beats": out_beats,
        "captions": [{"id": c["id"], "scene": c["scene"], "text": c["text"], "start_f": c["start_f"],
                      "dur_f": c["dur_f"]} for c in plan["captions"]],
        "markers": [m["name"] for m in back["markers"]],
        "deleted": sorted(set(prev.get("deleted", []) if deleted is None else deleted)),
    }
    path(film).write_text(json.dumps(data, indent=1) + "\n")
    return data
