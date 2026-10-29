"""The storyboard: defaults, validation and a readable sign-off copy.

Scene kinds:
  intro    the 3D arc of every segment's screen (or a plain background) under a centred title
  segment  an establishing 3D shot, then the footage, with a lower-third title and narration
  card     a centred title over the background: chapters, quotes, calls to action
  outro    the camera pulls back from a wall of screens under a centred title
  credits  where the rolling credits go (by default they close the film)

Intro, card and outro scenes may carry an image ({"file": ...}), placed on the FilmCraft timeline beside
the title, and a titlePlace of "center" or "low". Any scene may set gap: the pause between its lines. A
segment with showcase: false stays off the 3D stage: no screen in the arc or the wall, no establishing shot.
"""
from __future__ import annotations

import copy
import re

from .project import SCHEMA

PALETTE = ["#3fd6e0", "#ff5fae", "#8b5cf6", "#6ea8ff", "#f5a524", "#46d9b0", "#ff7a59", "#c3e88d"]
FORMATS = {
    "1080p": {"width": 1920, "height": 1080, "fps": 60},
    "1080p30": {"width": 1920, "height": 1080, "fps": 30},
    "4k": {"width": 3840, "height": 2160, "fps": 30},
    "vertical": {"width": 1080, "height": 1920, "fps": 60},
    "square": {"width": 1080, "height": 1080, "fps": 60},
}
KINDS = ("intro", "segment", "card", "outro", "credits")

DEFAULTS = {
    "showrig": SCHEMA,
    "title": "Untitled film",
    "kind": "showreel",
    "format": FORMATS["1080p"],
    "style": {
        "accent": "#46d9b0",
        "background": "#070b14",
        "titles": "rise",            # rise | typewriter | none
        "transitions": "cinematic",  # cinematic | simple | cuts
        "pushIn": 6,                 # percent zoom across each footage shot; 0 for none
        "showcase3d": True,          # Blender stage for intro, establishing shots and outro
        "stage": "auto",             # auto | screens | fullbleed | desk | paper | orbit (see studio.STAGES)
        "quality": "final",          # final | draft (Blender at half size, fewer samples)
        "titleHold": None,           # seconds a segment's lower third stays up; None for the whole scene
    },
    "voice": {"source": "tts", "engine": "kokoro", "voice": "af_heart", "speed": 1.0, "say": {}},
    "music": {"source": "procedural", "mood": "bright", "file": None, "volumeDb": -9.0},
    "captions": {"mode": "burn"},    # burn | srt | none
    "scenes": [],
    "credits": {"enabled": False, "lines": []},
}


def merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def normalize(answers: dict, draft: bool = False) -> dict:
    """Fill defaults, give every scene an id and colour, and check the result."""
    board = merge(DEFAULTS, answers)
    if isinstance(board["format"], str):
        board["format"] = FORMATS[board["format"]]
    seen, problems = set(), []
    for i, scene in enumerate(board["scenes"]):
        scene.setdefault("kind", "segment")
        scene.setdefault("title", f"Scene {i + 1}")
        scene.setdefault("tagline", "")
        scene.setdefault("lines", [])
        default = scene["kind"] if scene["kind"] in ("intro", "outro", "credits") else \
            re.sub(r"[^a-z0-9]+", "-", scene["title"].lower()).strip("-")[:24] or f"s{i}"
        sid = scene.setdefault("id", default)
        if not isinstance(sid, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", sid):
            raise SystemExit("scene IDs must contain only letters, numbers, underscores, or hyphens")
        if sid in seen:
            sid = scene["id"] = f"{sid}-{i}"
        seen.add(sid)
        if scene["kind"] not in KINDS:
            problems.append(f"{sid}: unknown kind {scene['kind']!r}")
        if scene["kind"] == "segment":
            scene.setdefault("color", PALETTE[len([s for s in board["scenes"][:i] if s.get("kind") == "segment"])
                                              % len(PALETTE)])
            if not scene.get("shots"):
                problems.append(f"{sid}: a segment needs at least one shot")
            for shot in scene.get("shots", []):
                if not (shot.get("file") or shot.get("capture")):
                    problems.append(f"{sid}: every shot needs a file or a capture")
                shot.setdefault("in", 0.0)
                shot.setdefault("weight", 1.0)
                shot.setdefault("fit", "fit")
        if scene.get("image") and (scene["kind"] not in ("intro", "card", "outro") or not scene["image"].get("file")):
            problems.append(f"{sid}: an image needs a file, on an intro, card or outro scene")
        if scene.get("titlePlace", "center") not in ("center", "low"):
            problems.append(f"{sid}: titlePlace is center or low")
        if not draft and board["voice"]["source"] == "files" and scene["lines"]:
            if len(scene.get("voice", [])) != len(scene["lines"]):
                problems.append(f"{sid}: voice source is files, so give one voice file per line")
    from .studio import STAGE_IDS  # deferred: studio imports this module for normalize
    stage = board["style"].get("stage") or "auto"
    if stage in STAGE_IDS:
        board["style"]["stage"] = stage
        board["style"]["showcase3d"] = stage != "fullbleed"
    elif stage == "auto":
        board["style"]["stage"] = "auto"
    else:
        problems.append(f"stage must be auto or one of: {', '.join(STAGE_IDS)}")
    if board["style"]["showcase3d"] and board["format"]["width"] < board["format"]["height"]:
        problems.append("the 3D showcase is framed for landscape; turn it off for vertical films")
    if problems:
        raise SystemExit("storyboard problems:\n  " + "\n  ".join(problems))
    return board


def markdown(board: dict) -> str:
    """The storyboard as a document to read and sign off before anything renders."""
    f, st = board["format"], board["style"]
    out = [f"# {board['title']}", "",
           f"{board['kind'].capitalize()}, {f['width']}x{f['height']} at {f['fps']} fps. "
           f"Titles: {st['titles']}. Transitions: {st['transitions']}. "
           f"Push-in: {st['pushIn']}%. 3D showcase: {'on' if st['showcase3d'] else 'off'}.",
           f"Voice: {board['voice']['source']}"
           + (f" ({board['voice']['engine']} {board['voice']['voice']})" if board['voice']['source'] == 'tts' else "")
           + f". Music: {board['music']['source']}"
           + (f" ({board['music']['mood']})" if board['music']['source'] == 'procedural' else "")
           + f". Captions: {board['captions']['mode']}.", ""]
    for n, s in enumerate(board["scenes"], 1):
        out.append(f"## {n}. {s['title']}  ·  {s['kind']}")
        if s.get("tagline"):
            out.append(f"*{s['tagline']}*" + (f"  ·  `{s['subtitle']}`" if s.get("subtitle") else ""))
        out.append("")
        for shot in s.get("shots", []):
            src = shot.get("file") or f"capture of {shot['capture']['url']}"
            out.append(f"- Shot: {src} (from {shot['in']}s, weight {shot['weight']})")
        for line in s.get("lines", []):
            out.append(f"> {line}")
        if s.get("note"):
            out.append(f"\nOn-screen note: {s['note']}")
        out.append("")
    if board["credits"]["enabled"]:
        out.append("## Credits\n")
        out += [f"- {line[0]}" if len(line) == 1 else f"- {line[0]}: {line[1]}" for line in board["credits"]["lines"]]
    return "\n".join(out) + "\n"
