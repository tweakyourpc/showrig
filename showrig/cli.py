"""showrig: the director's wizard and the offline production line behind it."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import __version__, tools
from .board import markdown, normalize
from .project import Film, film_lock

STAGES = ["footage", "voice", "plan", "titles", "stage", "music", "assemble", "render"]


def make(film: Film, until: str, draft: bool, progress=None) -> None:
    """Build a film under an exclusive lock, optionally reporting stage boundaries."""
    with film_lock(film.root):
        _make(film, until, draft, progress or (lambda stage: None))


def _make(film: Film, until: str, draft: bool, progress) -> None:
    from . import plan as planner
    from .stages import assemble, footage, music, stage3d, titles, voice

    if draft:
        film.style["quality"] = "draft"
    stop = STAGES.index(until)
    t0 = time.time()
    print(f"{film.board['title']}: {film.fmt['width']}x{film.fmt['height']} at {film.fmt['fps']} fps")
    progress("footage")
    footage.build(film)
    if stop < 1:
        return
    progress("voice")
    lines = voice.build(film)
    if stop < 2:
        return
    progress("plan")
    plan = planner.build(film, lines)
    if stop < 3:
        return
    progress("titles")
    titles.build(film, plan)
    if stop < 4:
        return
    progress("stage")
    stage3d.build(film, plan)
    stage3d.backdrops(film, plan)
    if stop < 5:
        return
    progress("music")
    score = music.build(film, plan)
    if stop < 6:
        return
    progress("assemble")
    assemble.build(film, plan, score)
    if stop < 7:
        return
    progress("render")
    assemble.render(film)
    print(f"done in {time.time() - t0:.0f}s: {film.out / (film.name + '.mp4')}")


def answers(path: Path) -> dict:
    """Load an answers file, making its media paths absolute so the film folder can live anywhere."""
    data = json.loads(path.read_text())
    base = path.resolve().parent

    def fix(p: str) -> str:
        return p if "://" in p or Path(p).expanduser().is_absolute() else str(base / p)
    for scene in data.get("scenes", []):
        for shot in scene.get("shots", []):
            if shot.get("file"):
                shot["file"] = fix(shot["file"])
            if shot.get("capture"):
                shot["capture"]["url"] = fix(shot["capture"]["url"])
        if scene.get("voice"):
            scene["voice"] = [fix(v) for v in scene["voice"]]
        if (scene.get("image") or {}).get("file"):
            scene["image"]["file"] = fix(scene["image"]["file"])
    if (data.get("music") or {}).get("file"):
        data["music"]["file"] = fix(data["music"]["file"])
    return data


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="showrig", description=__doc__)
    p.add_argument("--version", action="version", version=f"showrig {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("new", help="answer the director's questions and write a storyboard")
    s.add_argument("dir", type=Path)
    s.add_argument("--answers", type=Path, help="a storyboard-shaped JSON file instead of the questions")
    s.add_argument("--force", action="store_true", help="replace an existing storyboard")

    s = sub.add_parser("draft", help="optional: let a local model suggest missing narration and taglines")
    s.add_argument("dir", type=Path)
    s.add_argument("--model", default="qwen3:8b")

    s = sub.add_parser("board", help="check a hand-edited storyboard and refresh STORYBOARD.md")
    s.add_argument("dir", type=Path)

    s = sub.add_parser("make", help="build everything the storyboard asks for, then render")
    s.add_argument("dir", type=Path)
    s.add_argument("--until", choices=STAGES, default="render", help="stop after this stage")
    s.add_argument("--draft", action="store_true", help="fast Blender renders for a first look")

    s = sub.add_parser("render", help="export the FilmCraft project again, after editing it by hand")
    s.add_argument("dir", type=Path)
    s.add_argument("--out", type=Path)

    s = sub.add_parser("credits", help="post: append rolling credits to the finished cut")
    s.add_argument("dir", type=Path)
    s.add_argument("--line", action="append", default=[], metavar="ROLE=NAME")
    s.add_argument("--title", help="heading over the credits (default: the film title)")

    sub.add_parser("doctor", help="show which tools are installed and what each one unlocks")

    s = sub.add_parser("web", help="open the offline browser wizard")
    s.add_argument("--projects", type=Path, default=Path("films"))
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, help="a port already reserved through portbroker")
    s.add_argument("--no-open", action="store_true", help="do not open a browser automatically")

    a = p.parse_args(argv)
    if a.cmd == "web":
        from .web import serve
        serve(a.projects, a.host, a.port, not a.no_open)
        return
    if a.cmd == "doctor":
        raise SystemExit(tools.doctor())
    if a.cmd == "new":
        from .wizard import create
        create(a.dir, answers(a.answers) if a.answers else None, a.force)
        return
    film = Film.load(a.dir)
    if a.cmd == "draft":
        from .draft import draft
        draft(film, a.model)
    elif a.cmd == "board":
        film.board = normalize(film.board)
        film.save()
        (film.root / "STORYBOARD.md").write_text(markdown(film.board))
        print(f"storyboard ok: {len(film.board['scenes'])} scenes; {film.root / 'STORYBOARD.md'}")
    elif a.cmd == "make":
        film.board = normalize(film.board)
        make(film, a.until, a.draft)
    elif a.cmd == "render":
        from .stages.assemble import render
        render(film, a.out.resolve() if a.out else None)
    elif a.cmd == "credits":
        from .post import credits
        bad = [x for x in a.line if "=" not in x]
        if bad:
            raise SystemExit(f"credit lines are ROLE=NAME: {bad}")
        credits(film, [x.split("=", 1) for x in a.line], a.title)


if __name__ == "__main__":
    main()
