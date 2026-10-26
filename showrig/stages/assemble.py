"""Assembly: build the editable FilmCraft project from the plan, then render it through FilmCraft.

Tracks: V1 picture, V2 title cards, V3 on-screen notes and images, A1 voice, A2 music, C1 captions.
A rebuild never overwrites by surprise: the previous project moves to out/versions/ first.
"""
from __future__ import annotations

import json
import shutil
import time

from .. import tools
from ..project import Film, run

TICKS = 254016000000  # FilmCraft time base, per second


class FilmCraft:
    def __init__(self, film: Film, project):
        self.film, self.project = film, project
        self.cli = tools.filmcraft()
        if not self.cli:
            raise SystemExit("assembly needs the FilmCraft CLI (set FILMCRAFT_CLI)")

    def ticks(self, seconds: float) -> int:
        """Snap to whole frames."""
        fps = self.film.fmt["fps"]
        return round(seconds * fps) * TICKS // fps

    def __call__(self, label: str, commands: list[dict], create: bool = False) -> list:
        """Run FilmCraft commands as one script; keep the script and its receipt; fail on any rejection."""
        script = self.film.log(f"fc-{label}.jsonl")
        script.write_text("".join(json.dumps(c) + "\n" for c in commands))
        opts = ["--save-as", self.project] if create else ["--project", self.project, "--save"]
        res = run([self.cli, "--compact", *opts, "run", script], self.film.log(f"fc-{label}.log"))
        rows = [json.loads(line) for line in res.stdout.splitlines() if line.startswith("{")]
        if len(rows) != len(commands) or not all(r.get("ok") for r in rows):
            bad = next((r for r in rows if not r.get("ok")), res.stderr[-800:])
            raise SystemExit(f"FilmCraft rejected {label}: {bad}")
        return [r["result"] for r in rows]


def cmd(cid: str, **params) -> dict:
    return {"id": cid, "params": params}


def project_path(film: Film):
    return film.out / f"{film.name}.fcproj"


def build(film: Film, plan: dict, music: str | None) -> None:
    film.out.mkdir(exist_ok=True)
    project = project_path(film)
    if project.exists():
        keep = film.out / "versions" / f"{film.name}-{time.strftime('%Y%m%d-%H%M%S')}.fcproj"
        keep.parent.mkdir(exist_ok=True)
        shutil.move(project, keep)
        print(f"  previous project kept as {keep.relative_to(film.root)}")
    fc = FilmCraft(film, project)
    w, h, fps = film.fmt["width"], film.fmt["height"], film.fmt["fps"]
    fc("01-create", [cmd("file.newProject", name=film.board["title"]),
                     cmd("file.newSequence", name=film.board["title"], width=w, height=h, fps=fps,
                         sampleRate=48000, video=3, audio=2)], create=True)
    images = plan.get("images", [])
    paths = sorted({c["path"] for c in plan["video"]} | {c["path"] for c in plan["titles"]} |
                   {n["path"] for n in plan["narration"]} | {i["path"] for i in images} | ({music} if music else set()))
    items = dict(zip(paths, fc("02-import", [cmd("file.import", paths=paths)])[0]["items"]))

    edits, kinds = [], []
    for c in plan["video"]:
        edits.append(cmd("timeline.place", item=items[c["path"]], track="V1", seconds=c["start"],
                         sourceIn=fc.ticks(c["in"]), duration=fc.ticks(c["duration"]), audio=False, insert=False))
        kinds.append(("v1", c))
    for c in plan["titles"]:
        edits.append(cmd("timeline.place", item=items[c["path"]], track="V2", seconds=c["start"],
                         duration=fc.ticks(c["duration"]), audio=False, insert=False))
        kinds.append(("v2", c))
    for n in plan["narration"]:
        edits.append(cmd("timeline.place", item=items[n["path"]], track="A1", seconds=n["start"], video=False,
                         insert=False))
        kinds.append(("a1", n))
    if music:
        edits.append(cmd("timeline.place", item=items[music], track="A2", seconds=0, video=False, insert=False))
        kinds.append(("a2", None))
    for i in images:
        edits.append(cmd("timeline.place", item=items[i["path"]], track="V3", seconds=i["start"],
                         duration=fc.ticks(i["duration"]), audio=False, insert=False))
        kinds.append(("v3", i))
    placed = fc("03-place", edits)
    v1 = [(res["clips"][0], c) for (kind, c), res in zip(kinds, placed) if kind == "v1"]

    push, style = film.style["pushIn"], film.style["transitions"]
    motion, prev = [], None
    for clip, c in v1:
        if c["push"]:  # keyframe times are sequence times
            motion.append(cmd("effects.setParam", clip=clip, effect="motion", param="scale", value=100,
                              time=fc.ticks(c["start"]), keyframe=True))
            motion.append(cmd("effects.setParam", clip=clip, effect="motion", param="scale", value=100 + push,
                              time=fc.ticks(c["start"] + c["duration"]), keyframe=True))
        if prev is not None and style != "cuts":
            if style == "simple":
                effect, frames = "Cross Dissolve", 14
            elif c["kind"] == "footage" and prev["kind"] == "stage":
                effect, frames = "Cross Zoom", 20
            elif c["kind"] == "footage":
                effect, frames = "Cross Dissolve", 14
            else:
                effect, frames = "Film Dissolve", 24
            motion.append(cmd("sequence.applyVideoTransition", clip=clip, effect=effect,
                              frames=round(frames * fps / 60), edge="in"))
        prev = c
    # Images sit left of their title: a fade in and out and a slow push, all editable keyframes.
    size = 0.46 * h / 520 * 100  # the image's face is 520 px across in its 660 px frame
    for clip, i in [(res["clips"][0], i) for (kind, i), res in zip(kinds, placed) if kind == "v3"]:
        a, b = i["start"], i["start"] + i["duration"]
        motion += [cmd("effects.setParam", clip=clip, effect="motion", param="position", value=[round(w * .25), round(h / 2)]),
                   cmd("effects.setParam", clip=clip, effect="motion", param="scale", value=round(size, 2),
                       time=fc.ticks(a), keyframe=True),
                   cmd("effects.setParam", clip=clip, effect="motion", param="scale", value=round(size * 1.04, 2),
                       time=fc.ticks(b), keyframe=True)]
        motion += [cmd("effects.setParam", clip=clip, effect="opacity", param="opacity", value=v, time=fc.ticks(at),
                       keyframe=True) for at, v in ((a, 0), (a + .6, 100), (b - .5, 100), (b, 0))]
        motion.append(cmd("clip.rename", clip=clip, name=f"Image: {i['scene']}"))
    if motion:
        fc("04-motion-transitions", motion)

    mix = [cmd("timeline.setTrack", track="A1", name="Voice")]
    if music:
        clip = [r for (kind, _), r in zip(kinds, placed) if kind == "a2"][0]["clips"][0]
        mix += [cmd("timeline.setTrack", track="A2", volumeDb=film.board["music"]["volumeDb"], name="Music"),
                cmd("clip.rename", clip=clip, name="Music")]
    fc("05-mix", mix)

    scale = min(w / 1920, h / 1080)
    for i, note in enumerate(plan["notes"]):
        made = fc(f"06-note-{i}", [cmd("graphics.newText", text=note["text"], position=[w - 50 * scale, 64 * scale],
                                       size=round(26 * scale), font="Inter", seconds=note["duration"], track=2,
                                       time=fc.ticks(note["start"]), newClip=True)])[0]
        fc(f"06-note-{i}-style", [cmd("graphics.set", clip=made["clip"], layer=0,
                                      props={"align": "right", "fill_color": "#e8eef5", "background": True,
                                             "shadow": True, "opacity": 88}),
                                  cmd("clip.rename", clip=made["clip"], name="Note: " + note["text"])])

    if film.board["captions"]["mode"] != "none" and plan["captions"]:
        caps = [cmd("captions.newTrack", format="Subtitle", name="Captions", language="en"),
                cmd("captions.setStyle", track="C1", font="Inter", size=round(34 * min(1, w / h)), color="#ffffff",
                    background=True, backgroundColor="#000000b0", align="center", anchor="bottom", margin=0.035,
                    outline=3, outlineColor="#000000")]
        caps += [cmd("captions.add", track="C1", text=c["text"], seconds=c["start"],
                     durationSeconds=round(c["duration"] - 2 / fps, 3)) for c in plan["captions"]]
        fc("07-captions", caps)
        fc("08-export-srt", [cmd("captions.export", path=str(film.out / f"{film.name}.srt"), track="C1")])
    print(f"  FilmCraft project: {project.relative_to(film.root)}")


def render(film: Film, out=None) -> None:
    project = project_path(film)
    if not project.exists():
        raise SystemExit(f"{project} not found; run `showrig make` first")
    out = out or film.out / f"{film.name}.mp4"
    pixels = film.fmt["width"] * film.fmt["height"] * film.fmt["fps"]
    settings = {"hardwareEncoding": "auto", "burnCaptions": film.board["captions"]["mode"] == "burn",
                "bitrateKbps": max(8000, round(24000 * pixels / (1920 * 1080 * 60))), "bitrateMode": "vbr1Pass",
                "effects": {"loudness": {"enabled": True, "target_lufs": -16.0, "true_peak_dbtp": -1.0}}}
    t0 = time.time()
    temporary = out.with_name(out.stem + ".rendering.mp4")
    run([tools.filmcraft(), "--project", project, "export", temporary, "--format", "h264", "--settings",
         json.dumps(settings)], film.log("render.log"))
    from ..project import probe
    info = probe(temporary)
    if not info["width"] or info["duration"] <= 0:
        raise SystemExit("The renderer did not produce a valid video.")
    temporary.replace(out)
    print(f"  rendered {out.relative_to(film.root) if out.is_relative_to(film.root) else out} "
          f"in {time.time() - t0:.0f}s")
