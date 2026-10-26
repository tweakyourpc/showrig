"""Data-driven wizard templates, validation, and content-based timing."""
from __future__ import annotations

import copy
import math
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

from .board import normalize
from .project import probe

TEMPLATES = [
    {"id": "demo", "name": "Product demo", "description": "Show how it works, one useful feature at a time.",
     "prompts": ["Introduce your product", "Show the main feature", "Give people a next step"]},
    {"id": "showreel", "name": "Showcase", "description": "Give your work a considered, memorable introduction.",
     "prompts": ["Introduce your work", "Highlight a project", "Finish with your name or website"]},
    {"id": "trailer", "name": "Announcement", "description": "Make one clear announcement and invite people in.",
     "prompts": ["What is new?", "Why does it matter?", "When, where, or what next?"]},
    {"id": "explainer", "name": "Quick explainer", "description": "Turn a small idea into a clear visual story.",
     "prompts": ["Introduce the idea", "Explain the key point", "Leave one useful takeaway"]},
]
LOOKS = [
    {"id": "clean", "name": "Clean", "description": "Quiet typography. Soft colour. Room to breathe.",
     "accent": "#46d9b0", "background": "#111c26", "titles": "rise", "transitions": "simple", "pushIn": 3},
    {"id": "cinematic", "name": "Cinematic", "description": "Deep midnight, warm highlights, deliberate movement.",
     "accent": "#e9b779", "background": "#14101d", "titles": "rise", "transitions": "cinematic", "pushIn": 5},
    {"id": "terminal", "name": "Terminal", "description": "Monospace lettering with a precise type-on rhythm.",
     "accent": "#a5e88c", "background": "#0b1714", "titles": "typewriter", "transitions": "cuts", "pushIn": 0},
]


def new_board(title: str, template: str) -> dict:
    """Create a usable blank storyboard without inventing the user's content."""
    if template not in {x["id"] for x in TEMPLATES}:
        raise ValueError("Choose a supported template.")
    look = LOOKS[0]
    return normalize({
        "title": title.strip() or "Untitled film", "kind": template,
        "format": {"width": 1920, "height": 1080, "fps": 30},
        "style": {**{k: look[k] for k in ("accent", "background", "titles", "transitions", "pushIn")},
                  "design": look["id"], "showcase3d": False},
        "timing": "content", "voice": {"source": "none"},
        "music": {"source": "procedural", "mood": "calm", "volumeDb": -12},
        "scenes": [{"id": "intro", "kind": "intro", "title": title.strip(), "tagline": "", "lines": []},
                   {"id": "point", "kind": "card", "title": "", "tagline": "", "lines": []},
                   {"id": "outro", "kind": "outro", "title": "", "tagline": "", "lines": []}],
    })


def reading_seconds(scene: dict) -> float:
    """Allow a quiet beat plus comfortable reading time for visible text."""
    text = " ".join(str(scene.get(k, "")) for k in ("title", "tagline", "subtitle"))
    return max(3.0, len(text.split()) / 2.8 + 1.4)


def scene_seconds(scene: dict, voice_seconds: float = 0) -> float:
    """Explicit timing can add room but never truncate speech or readable text."""
    return round(max(reading_seconds(scene), voice_seconds + 1.5, scene.get("duration") or 0), 3)


def estimate(board: dict, root: Path | None = None) -> dict:
    """Estimate the same scene boundaries used by the content timing planner."""
    scenes = []
    for scene in board["scenes"]:
        lengths = [max(1.6, len(line) / 15) for line in scene.get("lines", [])]
        if board["voice"]["source"] == "files" and root:
            for i, path in enumerate(scene.get("voice", [])):
                if i < len(lengths) and path:
                    try:
                        lengths[i] = probe(root / path)["duration"]
                    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                        pass
        speech = sum(lengths) + max(0, len(lengths) - 1) * scene.get("gap", .45)
        duration = scene_seconds(scene, speech)
        if scene["kind"] == "credits":
            c = board["credits"]
            duration = 3.0 + c.get("secondsPerLine", .9) * len(c["lines"]) if c["enabled"] and c["lines"] else 0
        if board["style"]["showcase3d"]:
            duration = max(duration, {"intro": 9.6, "outro": 6.6, "segment": 7.5}.get(scene["kind"], 0))
        scenes.append({"id": scene["id"], "seconds": round(duration, 1)})
    return {"seconds": round(sum(s["seconds"] for s in scenes), 1), "scenes": scenes,
            "approximate": board["voice"]["source"] == "tts" or board.get("timing") != "content"}


def validate(data: dict, root: Path, allowed: list[Path], render: bool = False) -> dict:
    """Validate the browser boundary before paths or values reach external tools."""
    def fail(message: str) -> None:
        raise ValueError(message)

    def text(value, name: str, limit: int = 500) -> None:
        if not isinstance(value, str) or len(value) > limit:
            fail(f"{name} must be text of at most {limit} characters.")

    def number(value, name: str, low: float, high: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            fail(f"{name} must be between {low:g} and {high:g}.")

    def choice(value, name: str, values) -> None:
        if value not in values:
            fail(f"Choose a supported {name}.")

    if not isinstance(data, dict):
        fail("A storyboard must be an object.")
    for key in ("style", "voice", "music", "captions", "credits"):
        if key in data and not isinstance(data[key], dict):
            fail(f"{key} must be an object.")
    if not isinstance(data.get("scenes"), list) or not 1 <= len(data["scenes"]) <= 40:
        fail("Use between 1 and 40 scenes.")
    for scene in data["scenes"]:
        if not isinstance(scene, dict):
            fail("Each scene must be an object.")
        for key in ("title", "tagline", "subtitle", "note"):
            text(scene.get(key, ""), key, 160 if key == "title" else 600)
        if "id" in scene and (not isinstance(scene["id"], str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", scene["id"])):
            fail("Scene IDs must contain only letters, numbers, underscores, or hyphens.")
        if not isinstance(scene.get("lines", []), list) or len(scene.get("lines", [])) > 30:
            fail("Use at most 30 narration lines per scene.")
        for line in scene.get("lines", []):
            text(line, "Narration", 2000)
            if not line.strip():
                fail("Remove empty narration lines.")
        if scene.get("duration") is not None:
            number(scene["duration"], "Scene duration", 1, 180)
        if not isinstance(scene.get("shots", []), list) or len(scene.get("shots", [])) > 20:
            fail("Use at most 20 shots per scene.")
        for shot in scene.get("shots", []):
            if not isinstance(shot, dict):
                fail("Each shot must be an object.")
            number(shot.get("in", 0), "Clip start", 0, 86400)
            number(shot.get("weight", 1), "Shot weight", .01, 100)
            if shot.get("capture"):
                cap = shot["capture"]
                if not isinstance(cap, dict):
                    fail("Capture must be an object.")
                text(cap.get("url"), "Capture path", 4096)
                if urlparse(cap["url"]).scheme not in ("", "file"):
                    fail("Offline captures must use a local HTML file. Upload a recording for an online page.")
                number(cap.get("scale", 1), "Capture scale", .5, 3)
                if not isinstance(cap.get("actions", []), list) or len(cap.get("actions", [])) > 100:
                    fail("Use at most 100 capture actions.")
                for action in cap.get("actions", []):
                    text(action, "Capture action", 1000)
                    if action.strip().split(" ")[0] not in ("wait", "scroll", "type", "click", "press"):
                        fail("Offline captures support wait, scroll, type, click, and press.")
        if not isinstance(scene.get("voice", []), list):
            fail("Voice recordings must be a list.")
        if render and not (scene.get("title", "").strip() or scene.get("tagline", "").strip() or scene.get("shots")):
            fail("Give every scene a heading, some text, or media; remove unused scenes.")
    try:
        board = normalize(copy.deepcopy(data), draft=not render)
    except (SystemExit, KeyError, TypeError, AttributeError) as exc:
        fail(str(exc))
    text(board["title"], "Film title", 120)
    choice(board.get("showrig"), "storyboard version", (1,))
    choice(board.get("kind"), "film type", tuple(t["id"] for t in TEMPLATES))
    if not board["title"].strip():
        fail("Give the film a title.")
    choice(board["voice"]["source"], "voice source", ("none", "tts", "files"))
    choice(board["music"]["source"], "music source", ("none", "procedural", "file"))
    choice(board["music"]["mood"], "music mood", ("calm", "bright", "drive"))
    choice(board["captions"]["mode"], "caption mode", ("none", "burn", "srt"))
    choice(board["style"]["titles"], "title style", ("rise", "typewriter", "none"))
    choice(board["style"]["transitions"], "transition", ("simple", "cinematic", "cuts"))
    choice(board["style"].get("design", "clean"), "design", tuple(x["id"] for x in LOOKS))
    choice(board["voice"].get("voice"), "voice", ("af_heart", "af_bella", "am_michael", "bf_emma", "bm_george"))
    number(board["voice"]["speed"], "Speech speed", .5, 2)
    if not isinstance(board["voice"].get("say"), dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in board["voice"]["say"].items()):
        fail("Pronunciation replacements must map words to spoken text.")
    credits = board["credits"]
    if not isinstance(credits.get("enabled"), bool) or not isinstance(credits.get("lines"), list):
        fail("Credits need an enabled flag and a list of role/name pairs.")
    if len(credits["lines"]) > 100:
        fail("Use at most 100 credit lines.")
    for line in credits["lines"]:
        if not isinstance(line, list) or len(line) not in (1, 2) or any(not isinstance(v, str) or len(v) > 160 for v in line):
            fail("Each credit must be a short heading, or a role and a name.")
    for scene in board["scenes"]:
        if "hero" in scene:
            number(scene["hero"], "Featured shot", 0, max(0, len(scene.get("shots", [])) - 1))
            if not isinstance(scene["hero"], int):
                fail("The featured shot must be an integer.")
    number(board["style"]["pushIn"], "Camera movement", 0, 15)
    number(board["music"]["volumeDb"], "Music volume", -60, 0)
    if not isinstance(board["style"]["showcase3d"], bool):
        fail("3D showcase must be on or off.")
    for color in [board["style"]["accent"], board["style"]["background"]] + [s["color"] for s in board["scenes"] if "color" in s]:
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            fail("Use six-digit hex colours.")
    fmt = board["format"]
    if not isinstance(fmt, dict):
        fail("Choose a picture format.")
    for key in ("width", "height"):
        number(fmt.get(key), key, 240, 3840)
        if not isinstance(fmt[key], int) or fmt[key] % 2:
            fail("Picture dimensions must be even integers.")
    choice(fmt.get("fps"), "frame rate", (24, 25, 30, 50, 60))
    if board["style"]["showcase3d"] and fmt["width"] <= fmt["height"]:
        fail("Use landscape format for the 3D showcase.")
    for _, value in media_references(board):
        text(value, "Media path", 4096)
        path = resolve_media(root, value)
        if not any(path.is_relative_to(base.resolve()) for base in allowed):
            fail(f"Media is outside this studio: {Path(value).name}. Upload a replacement.")
        if render and not path.is_file():
            fail(f"Missing media: {Path(value).name}. Upload a replacement.")
    if render and board["music"]["source"] == "file" and not board["music"].get("file"):
        fail("Upload your music track or choose another music option.")
    if render and board["voice"]["source"] == "files":
        for scene in board["scenes"]:
            if len(scene.get("voice", [])) != len(scene["lines"]) or any(not p for p in scene.get("voice", [])):
                fail("Attach one audio recording for each narration line.")
    return board


def resolve_media(root: Path, value: str) -> Path:
    """Resolve legacy file URLs and project-relative media consistently."""
    parsed = urlparse(value)
    if parsed.scheme and parsed.scheme != "file":
        raise ValueError("Media must be a local file.")
    path = Path(unquote(parsed.path) if parsed.scheme == "file" else value).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def media_references(board: dict):
    """Yield mutable owners and keys for all external media references."""
    for scene in board["scenes"]:
        for shot in scene.get("shots", []):
            if shot.get("file"):
                yield (shot, "file"), shot["file"]
            if shot.get("capture"):
                yield (shot["capture"], "url"), shot["capture"]["url"]
        for i, value in enumerate(scene.get("voice", [])):
            if value:
                yield (scene["voice"], i), value
    if board["music"].get("file"):
        yield (board["music"], "file"), board["music"]["file"]
