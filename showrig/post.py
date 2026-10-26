"""Post-production modules that work on the finished FilmCraft project in place, so any hand edits
made in FilmCraft survive. Each one also records itself in the storyboard, so a full `make`
later produces the same film.
"""
from __future__ import annotations

import json

import numpy as np
from scipy.io import wavfile

from . import tools
from .plan import CREDIT_SECS
from .project import Film, run
from .stages import music as music_stage
from .stages import stage3d, titles
from .stages.assemble import TICKS, FilmCraft, cmd, project_path


def credits(film: Film, lines: list[list[str]], title: str | None) -> None:
    """Append rolling credits, over a backdrop and a short music tail, to the end of the cut."""
    project = project_path(film)
    if not project.exists():
        raise SystemExit(f"{project} not found; run `showrig make` first")
    c = film.board["credits"]
    c["lines"] = c["lines"] + [list(x) for x in lines]
    if title:
        c["title"] = title
    if not c["lines"]:
        raise SystemExit("no credits to add: pass --line 'Role=Name'")
    seq = json.loads(run([tools.filmcraft(), "--project", project, "inspect", "sequence"]).stdout)
    already = [clip for track in seq["video"] for clip in track.get("clips", [])
               if "credits" in json.dumps(clip).lower()]
    if already:
        raise SystemExit("this cut already has credits; edit them in FilmCraft or rebuild with `showrig make`")
    end = seq["duration"] / TICKS
    dur = round(3.0 + CREDIT_SECS * len(c["lines"]), 3)
    plan = {"backdrops": [{"scene": "credits", "seconds": dur + 0.5}],
            "titles": [{"scene": "credits", "layout": "credits", "start": end, "duration": dur}]}
    stage3d.backdrops(film, plan)
    titles.build(film, plan)
    bg = str(film.work / "backdrops/credits.mp4")
    roll = str(film.work / "titles/credits.mov")
    paths = [bg, roll]
    tail = None
    if film.board["music"]["source"] != "none":
        tail = str(film.work / "music-credits.wav")
        audio = music_stage.score(dur, film.board["music"].get("mood", "bright")) \
            if film.board["music"]["source"] == "procedural" else music_stage.decode(film.asset(film.board["music"]["file"]), dur)
        t = np.arange(len(audio)) / music_stage.RATE
        audio = audio * (np.minimum(t / 1.0, 1) * np.clip((dur - t) / 2.5, 0, 1))[:, None]
        audio = audio / (np.max(np.abs(audio)) or 1) * 0.5
        wavfile.write(tail, music_stage.RATE, (audio * 32767).astype(np.int16))
        paths.append(tail)
    fc = FilmCraft(film, project)
    items = dict(zip(paths, fc("post-credits-import", [cmd("file.import", paths=paths)])[0]["items"]))
    edits = [cmd("timeline.place", item=items[bg], track="V1", seconds=end, duration=fc.ticks(dur), audio=False,
                 insert=False),
             cmd("timeline.place", item=items[roll], track="V2", seconds=end, duration=fc.ticks(dur), audio=False,
                 insert=False)]
    if tail:
        edits.append(cmd("timeline.place", item=items[tail], track="A2", seconds=end, video=False, insert=False))
    placed = fc("post-credits-place", edits)
    fc("post-credits-finish", [cmd("sequence.applyVideoTransition", clip=placed[0]["clips"][0],
                                   effect="Film Dissolve", frames=round(24 * film.fmt["fps"] / 60), edge="in"),
                               cmd("clip.rename", clip=placed[1]["clips"][0], name="Credits")])
    c["enabled"] = True
    film.save()
    print(f"  credits: {len(c['lines'])} lines, {dur:.1f}s, appended at {end:.1f}s; `showrig render` to export")
