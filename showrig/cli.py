"""showrig: the director's wizard and the offline production line behind it."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import __version__
from .board import markdown, normalize
from .project import Film, film_lock

STAGES = ["footage", "voice", "plan", "titles", "stage", "music", "assemble", "render"]


def make(film: Film, until: str, draft: bool, progress=None, fresh: bool = False, restore: tuple = ()) -> None:
    """Build a film under an exclusive lock, optionally reporting stage boundaries."""
    with film_lock(film.root):
        _make(film, until, draft, progress or (lambda stage: None), fresh, tuple(restore))


def _make(film: Film, until: str, draft: bool, progress, fresh: bool = False, restore: tuple = ()) -> None:
    from . import manifest, reconcile, sources
    from . import plan as planner
    from .stages import assemble, footage, music, stage3d, titles, voice

    if draft:
        film.style["quality"] = "draft"
    stop = STAGES.index(until)
    t0 = time.time()
    timing, report = {}, progress

    def mark(stage: str | None) -> None:  # time each stage, for work/last-build.json
        now = time.time()
        if timing:
            last = timing[next(reversed(timing))]
            last.setdefault("seconds", round(now - last["at"], 2))
        if stage:
            timing[stage] = {"at": now}

    def progress(stage: str) -> None:
        mark(stage)
        report(stage)
    print(f"{film.board['title']}: {film.fmt['width']}x{film.fmt['height']} at {film.fmt['fps']} fps")
    sources.gate(film, final=until == "render" and not draft)  # before any work, so a blocked film costs nothing
    prev = manifest.load(film)
    if fresh and prev and any(b.get("lock") for b in prev["beats"]):
        raise SystemExit("--fresh would discard locked beats; unlock them first (showrig unlock FILM ID)")
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
    if not fresh and reconcile.needed(film):  # the project holds a person's edits or locks: keep them
        reconcile.run(film, plan, score, restore)
    else:
        built = assemble.build(film, plan, score)
        manifest.write(film, plan, built["beats"], built["filmcraft"], assemble.PROMISE, deleted=[])
    sources.write_lock(film)
    if stop < 7:
        return
    progress("render")
    assemble.render(film)
    from . import qc
    qc.run(film)
    mark(None)
    (film.work / "last-build.json").write_text(json.dumps(
        {"seconds": round(time.time() - t0, 2), "draft": draft,
         "stages": {k: v["seconds"] for k, v in timing.items()}}, indent=1))
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


def doctor(a) -> int:
    from . import capabilities
    try:
        rep = capabilities.report(a.profile, a.deep)
    except Exception as e:  # the diagnostic itself broke: say so, and keep it apart from "missing"
        print(f"doctor failed: {type(e).__name__}: {e}")
        return 3
    text = json.dumps(rep, indent=1)
    if a.out:
        a.out.write_text(text + "\n")
    if a.json:
        print(text)
    else:
        capabilities.print_report(rep)
    return 0 if not rep["summary"]["unavailable"] else 1


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
    s.add_argument("--fresh", action="store_true",
                   help="rebuild the project from scratch, discarding hand edits (the old project goes to out/versions/)")
    s.add_argument("--restore", action="append", default=[], metavar="ID",
                   help="bring back a beat deleted by hand (repeatable)")

    s = sub.add_parser("sources", help="list every source and its licence; record a licence with 'set'")
    s.add_argument("dir", type=Path)
    s.add_argument("action", nargs="?", choices=["set"])
    s.add_argument("ref", nargs="?", help="the source's ref from the list, e.g. clip/shot1, intro/image, music")
    s.add_argument("--licence", help="e.g. CC-BY-4.0, CC0-1.0, own work, licensed from Pond5 #123")
    s.add_argument("--credit", help="attribution text, when the licence asks for one")
    s.add_argument("--url", help="where it came from")

    for name, text in (("lock", "freeze a beat or a whole scene: later builds never change it"),
                       ("unlock", "hand a locked or hand-edited beat back to Showrig")):
        s = sub.add_parser(name, help=text)
        s.add_argument("dir", type=Path)
        s.add_argument("target", help="a beat id (clip/shot1) or a scene id (clip)")

    s = sub.add_parser("diff", help="what changed in the FilmCraft project since Showrig built it")
    s.add_argument("dir", type=Path)
    s.add_argument("--json", action="store_true", help="print the report as JSON (also written to out/diff.json)")

    s = sub.add_parser("qc", help="re-transcribe the final film and check every narration line is heard; measure its style")
    s.add_argument("dir", type=Path)
    s.add_argument("--video", type=Path, help="check this file instead of out/<name>.mp4")

    s = sub.add_parser("render", help="export the FilmCraft project again, after editing it by hand")
    s.add_argument("dir", type=Path)
    s.add_argument("--out", type=Path)

    s = sub.add_parser("credits", help="post: append rolling credits to the finished cut")
    s.add_argument("dir", type=Path)
    s.add_argument("--line", action="append", default=[], metavar="ROLE=NAME")
    s.add_argument("--title", help="heading over the credits (default: the film title)")

    s = sub.add_parser("receipt", help="record what a film was built from, on what machine, with checksums")
    s.add_argument("dir", type=Path)
    s.add_argument("--doctor", type=Path, help="a `doctor --deep --json` report to record as the environment")
    s.add_argument("--out", type=Path, help="where to write it (default: out/<name>-receipt.json)")

    s = sub.add_parser("doctor", help="show which tools are installed and what each one unlocks",
                       description="Exit 0: the requested capabilities are ready (or found, without --deep); "
                                   "1: one is unavailable; 3: the check itself failed.")
    s.add_argument("--profile", choices=["core", "capture", "voice", "showcase3d", "studio", "drafting"],
                   help="check only this profile, and require all of it (default: everything, requiring core)")
    s.add_argument("--deep", action="store_true", help="prove each capability with a small real job")
    s.add_argument("--json", action="store_true", help="print the report as JSON")
    s.add_argument("--out", type=Path, help="also write the JSON report here")

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
    if a.cmd == "receipt":
        from . import receipt
        film = Film.load(a.dir)
        out = a.out or film.out / f"{film.name}-receipt.json"
        out.write_text(json.dumps(receipt.build(film, a.doctor), indent=1) + "\n")
        print(f"receipt: {out}")
        return
    if a.cmd == "doctor":
        raise SystemExit(doctor(a))
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
        make(film, a.until, a.draft, fresh=a.fresh, restore=tuple(a.restore))
    elif a.cmd == "sources":
        from . import sources
        film.board = normalize(film.board)
        if a.action == "set":
            if not (a.ref and a.licence):
                raise SystemExit("usage: showrig sources FILM set REF --licence NAME [--credit TEXT] [--url URL]")
            sources.set_licence(film, a.ref, a.licence, a.credit, a.url)
            print(f"{a.ref}: {a.licence}")
        raise SystemExit(sources.show(film))
    elif a.cmd in ("lock", "unlock"):
        from .reconcile import lock
        film.board = normalize(film.board)
        raise SystemExit(lock(film, a.target, a.cmd == "lock"))
    elif a.cmd == "qc":
        from .qc import run as qc_run
        film.board = normalize(film.board)
        report = qc_run(film, a.video.resolve() if a.video else None, gate=False)
        raise SystemExit(0 if report["speech"]["ok"] and report["style"]["ok"] else 1)
    elif a.cmd == "diff":
        from .diff import show
        raise SystemExit(show(film, a.json))
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
