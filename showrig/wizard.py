"""The director's wizard: questions in, storyboard out.

Every answer lands in showrig.json, which is also what `--answers FILE` accepts, so a wizard
session and a hand-written storyboard are the same thing.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import tools
from .board import FORMATS, PALETTE, markdown, normalize
from .project import probe

VOICES = {"af_heart": "warm, American (female)", "af_bella": "bright, American (female)",
          "am_michael": "calm, American (male)", "bf_emma": "clear, British (female)",
          "bm_george": "rich, British (male)"}
MOODS = {"bright": "uplifting synth, 96 BPM", "calm": "slow pads, 72 BPM", "drive": "energetic, 120 BPM"}


def ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    reply = input(f"{prompt}{hint}: ").strip()
    return reply or default


def yes(prompt: str, default: bool = True) -> bool:
    reply = input(f"{prompt} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    return default if not reply else reply.startswith("y")


def choose(prompt: str, options: dict[str, str], default: str) -> str:
    print(f"\n{prompt}")
    keys = list(options)
    for i, k in enumerate(keys, 1):
        print(f"  {i}. {k:12} {options[k]}")
    while True:
        reply = input(f"choice [{keys.index(default) + 1}]: ").strip()
        if not reply:
            return default
        if reply.isdigit() and 1 <= int(reply) <= len(keys):
            return keys[int(reply) - 1]
        if reply in options:
            return reply
        print("  pick a number from the list")


def lines(prompt: str) -> list[str]:
    print(f"{prompt} (one sentence per line, empty line to finish)")
    out = []
    while (line := input("  > ").strip()):
        out.append(line)
    return out


def ask_media(prompt: str, root: Path, fmt: dict) -> str | None:
    """A file path, checked and described: resolution, frame rate, length, and any fit problem."""
    while True:
        raw = ask(prompt)
        if not raw:
            return None
        path = Path(raw).expanduser()
        path = path if path.is_absolute() else root / path
        if not path.exists():
            print(f"  not found: {path}")
            continue
        info = probe(path)
        if info["width"]:
            print(f"  {info['width']}x{info['height']} at {info['fps']} fps, {info['duration']:.1f}s")
            if abs(info["width"] / info["height"] - fmt["width"] / fmt["height"]) > 0.02:
                print("  different shape from the film: it will be fitted over a blurred fill")
            if info["width"] < fmt["width"] * 0.66:
                print("  low resolution for this format: it will look soft when scaled up")
        else:
            print(f"  audio, {info['duration']:.1f}s")
        return str(path)


def ask_capture() -> dict | None:
    url = ask("  page URL or file path to record (blank to skip)")
    if not url:
        return None
    if "://" not in url:
        url = Path(url).expanduser().resolve().as_uri()
    print("  actions, one per line, empty to finish:")
    print("    wait 2 | scroll 1200 4 (pixels, seconds) | type <css selector> <text> | click <css selector>")
    actions = []
    while (a := input("    > ").strip()):
        actions.append(a)
    return {"url": url, "scale": float(ask("  page zoom (1.25 makes small UIs readable)", "1.25")),
            "actions": actions or ["wait 1", "scroll 1400 6", "wait 1"]}


def interview(root: Path) -> dict:
    print("\nShowrig: the director's questions. Press Enter to take the suggestion in brackets.\n")
    a: dict = {"title": ask("Film title", "My showreel")}
    a["kind"] = choose("What kind of film?", {
        "showreel": "several projects, one after another",
        "demo": "one product, feature by feature",
        "explainer": "an idea, step by step",
        "trailer": "short and punchy announcement"}, "showreel")
    a["format"] = choose("Picture format?", {k: f"{v['width']}x{v['height']} at {v['fps']} fps"
                                            for k, v in FORMATS.items()}, "1080p")
    landscape = FORMATS[a["format"]]["width"] > FORMATS[a["format"]]["height"]

    print("\nThe look")
    style = {"accent": ask("Accent colour (hex)", "#46d9b0")}
    style["titles"] = choose("Title cards (EffectCraft)", {"rise": "titles rise out of a blur",
                                                          "typewriter": "titles type on like a terminal",
                                                          "none": "no title cards"}, "rise")
    style["transitions"] = choose("Transitions", {"cinematic": "zoom into footage, dissolves between scenes",
                                                  "simple": "cross dissolves", "cuts": "straight cuts"}, "cinematic")
    style["pushIn"] = 6 if yes("Slow zoom-in on every footage shot?") else 0
    style["showcase3d"] = landscape and bool(tools.blender()) and yes(
        "3D showcase in Blender (glowing floating screens for the intro, each segment and the outro)?")
    style["quality"] = "draft" if yes("Draft quality first (faster Blender renders)?", False) else "final"
    a["style"] = style

    print("\nSound")
    has_tts = bool(tools.tts_python())
    source = choose("Voiceover", {"tts": "generate it offline with Kokoro" + ("" if has_tts else " (not installed)"),
                                  "files": "I have my own recordings (one WAV per line)",
                                  "none": "no voiceover"}, "tts" if has_tts else "files")
    a["voice"] = {"source": source}
    if source == "tts":
        a["voice"]["voice"] = choose("Voice", VOICES, "af_heart")
        say = ask("Words to pronounce differently, as word=spoken form, comma separated (blank for none)")
        a["voice"]["say"] = dict(p.split("=", 1) for p in say.split(",") if "=" in p)
    music = choose("Music", {"procedural": "a score generated to fit the cut",
                             "file": "my own track (ducked under the voice)", "none": "no music"}, "procedural")
    a["music"] = {"source": music}
    if music == "procedural":
        a["music"]["mood"] = choose("Mood", MOODS, "bright")
    elif music == "file":
        a["music"]["file"] = ask_media("Music file", root, FORMATS[a["format"]])
    a["captions"] = {"mode": choose("Captions", {"burn": "burned into the picture and saved as SRT",
                                                 "srt": "SRT file only", "none": "no captions"}, "burn")}

    print("\nThe story. First the opening.")
    scenes = [{"kind": "intro", "id": "intro", "title": ask("Opening title", a["title"]),
               "tagline": ask("Opening tagline")}]
    scenes[0]["lines"] = lines("Opening narration") if source != "none" else []
    fmt = FORMATS[a["format"]]
    n = 0
    while yes(f"\nAdd {'a' if n == 0 else 'another'} segment?", n == 0):
        n += 1
        seg = {"kind": "segment", "title": ask("  Segment title", f"Project {n}"), "tagline": ask("  Tagline"),
               "subtitle": ask("  Small line under it, such as a URL (blank for none)"),
               "color": ask("  Colour (hex)", PALETTE[(n - 1) % len(PALETTE)]), "shots": []}
        while True:
            kind = choose("  Add footage", {"file": "a clip I recorded", "capture": "record a web page now",
                                            "done": "no more footage"}, "file" if not seg["shots"] else "done")
            if kind == "done":
                break
            if kind == "file":
                path = ask_media("  Clip path", root, fmt)
                if path:
                    seg["shots"].append({"file": path, "in": float(ask("  Start at second", "0")),
                                         "weight": float(ask("  Share of screen time (1 = normal)", "1"))})
            elif (cap := ask_capture()):
                seg["shots"].append({"capture": cap, "weight": 1.0})
        if not seg["shots"]:
            print("  a segment needs footage; skipped")
            n -= 1
            continue
        seg["lines"] = lines("  Narration") if source != "none" else []
        if source == "files":
            seg["voice"] = [ask_media(f"  Recording for line {i}", root, fmt) for i in range(1, len(seg["lines"]) + 1)]
        seg["note"] = ask("  On-screen note, such as 'demo data' (blank for none)")
        scenes.append(seg)
    while yes("\nAdd a title card (chapter, quote, call to action)?", False):
        card = {"kind": "card", "title": ask("  Card title"), "tagline": ask("  Card tagline")}
        card["lines"] = lines("  Narration") if source != "none" else []
        scenes.insert(len(scenes) if not yes("  Put it before the last segment?", False) else -1, card)
    outro = {"kind": "outro", "id": "outro", "title": ask("\nClosing title", a["title"]),
             "tagline": ask("Closing tagline")}
    outro["lines"] = lines("Closing narration") if source != "none" else []
    scenes.append(outro)
    if source == "files":
        for s in (scenes[0], outro):
            s["voice"] = [ask_media(f"Recording for {s['kind']} line {i}", root, fmt)
                          for i in range(1, len(s["lines"]) + 1)]
    a["scenes"] = scenes

    if yes("\nRolling credits at the end? (you can add them later with `showrig credits`)", False):
        roles = []
        while (role := ask("  Role (blank to finish)")):
            roles.append([role, ask("  Name")])
        a["credits"] = {"enabled": True, "lines": roles}
    return a


def create(root: Path, answers: dict | None, force: bool = False) -> None:
    root = root.resolve()
    target = root / "showrig.json"
    if target.exists() and not force:
        raise SystemExit(f"{target} exists; edit it, or pass --force to start over")
    root.mkdir(parents=True, exist_ok=True)
    (root / "assets").mkdir(exist_ok=True)
    answers = answers if answers is not None else interview(root)
    answers.setdefault("provenance", {"gate": "strict"})  # new films: an unlicensed supplied source blocks the final render
    answers.setdefault("qc", {"asr": "fail", "minRecall": 0.8})  # new films: a narration word lost in the mix fails
    board = normalize(answers)
    target.write_text(json.dumps(board, indent=2) + "\n")
    (root / "STORYBOARD.md").write_text(markdown(board))
    print(f"\nstoryboard: {target}\nread it:    {root / 'STORYBOARD.md'}")
    if shutil.which("ollama") and any(not s["lines"] for s in board["scenes"]):
        print("some scenes have no narration: `showrig draft` can suggest lines with a local model")
    print(f"then:       showrig make {root}")
