"""Timing: turn the storyboard, the voice lengths and the footage into a frame-exact edit plan.

Each scene is as long as its narration needs, never shorter than its pictures want. The plan says
what every later stage must make (Blender shots of known length, title cards, backdrops) and
where everything sits on the timeline.
"""
from __future__ import annotations

import json
import textwrap

from .project import Film, probe
from .stages.footage import shot_path
from .studio import scene_seconds

GAP = 0.45            # pause between narration lines
EST = 4.5             # establishing 3D shot on screen
EST_IN = 0.25         # its source in-point, leaving handles for transitions
MIN_FOOTAGE = 8.0
OPEN = {"intro": 9.6, "outro": 6.6}       # the 3D opening and closing shots' minimum length
TITLE = {"intro": 5.0, "outro": 6.0, "segment": 4.5}
CREDIT_SECS = 0.9     # screen time per credit line


def caption_chunks(text: str, start: float, length: float) -> list[dict]:
    """Split a line into readable caption cues, timed by character share."""
    parts = textwrap.wrap(text, width=58, break_long_words=True, break_on_hyphens=False)
    if not parts:
        return []
    total = sum(len(p) for p in parts)
    cues, t = [], start
    for p in parts:
        d = length * len(p) / total
        cues.append({"text": p, "start": round(t, 3), "duration": round(d, 3)})
        t += d
    return cues


def identify(plan: dict, fps: int) -> None:
    """Give every entry a stable beat ID and whole-frame timing, in place.

    An ID is the scene's id and the entry's role (``clip/shot2``, ``clip/title``, ``intro/voice1``); it depends
    only on the storyboard, never on timing, so it survives re-runs and names the clip in the FilmCraft project.
    Frames are the plan's time base: each entry gets ``start_f`` and ``dur_f`` (``in_f`` for a source in-point),
    rounded from its edges so neighbours stay contiguous, and its seconds are re-derived from those frames.
    FilmCraft ticks are made from frames only at the boundary (stages/assemble.py).
    """
    def snap(e: dict) -> None:
        start = round(e["start"] * fps)
        e["start_f"], e["start"] = start, round(start / fps, 6)
        if "duration" in e:
            e["dur_f"] = max(1, round((e["start"] + e["duration"]) * fps) - start)
            e["duration"] = round(e["dur_f"] / fps, 6)
        if "in" in e:
            e["in_f"] = round(e["in"] * fps)

    counts: dict[tuple, int] = {}

    def nth(scene: str, role: str) -> int:
        counts[scene, role] = counts.get((scene, role), 0) + 1
        return counts[scene, role]

    roles = {"stage": "stage", "backdrop": "backdrop"}
    for e in plan["video"]:
        e["id"] = f"{e['scene']}/shot{e['shot']}" if e["kind"] == "footage" else f"{e['scene']}/{roles[e['kind']]}"
    for e in plan["titles"]:
        e["id"] = f"{e['scene']}/title"
    for e in plan["narration"]:
        e["line"] = e.get("id")  # the voice stage's own line id, e.g. clip-01
        e["id"] = f"{e['scene']}/voice{nth(e['scene'], 'voice')}"
    for e in plan["captions"]:
        e["id"] = f"{e['scene']}/cap{nth(e['scene'], 'cap')}"
    for e in plan["notes"]:
        e["id"] = f"{e['scene']}/note"
    for e in plan["images"]:
        e["id"] = f"{e['scene']}/image"
    for key in ("video", "titles", "narration", "captions", "notes", "images"):
        for e in plan[key]:
            snap(e)
    ids = [e["id"] for key in ("video", "titles", "narration", "captions", "notes", "images") for e in plan[key]]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise SystemExit(f"two plan entries share an id: {dupes}; give each scene a unique id")


def hero(film: Film, scene: dict) -> dict:
    """The shot that plays on this segment's 3D screen."""
    i = scene.get("hero", 0)
    shot = scene["shots"][i]
    return {"video": str(shot_path(film, scene["id"], i)), "color": scene["color"], "offset": shot["in"] + 1.0}


def build(film: Film, voice: list[dict]) -> dict:
    three_d = film.style["showcase3d"]
    by_scene: dict[str, list[dict]] = {}
    for item in voice:
        by_scene.setdefault(item["scene"], []).append(item)
    segments = [s for s in film.scenes("segment") if s.get("showcase", True)]  # the ones on the 3D stage
    three_d = three_d and bool(segments)
    panels = [hero(film, s) for s in segments]
    video, titles, narration, captions, notes, stage, backdrops, images = [], [], [], [], [], [], [], []
    credits = film.board["credits"]
    rolled = False

    def roll(t: float) -> float:
        """Rolling credits over a backdrop from t; returns where they end."""
        if not (credits["enabled"] and credits["lines"]):
            return t
        dur = round(3.0 + credits.get("secondsPerLine", CREDIT_SECS) * len(credits["lines"]), 3)
        video.append({"kind": "backdrop", "scene": "credits", "start": t, "in": 0.0, "duration": dur, "push": False})
        backdrops.append({"scene": "credits", "seconds": dur + 0.5})
        titles.append({"scene": "credits", "layout": "credits", "start": t, "duration": dur})
        return t + dur

    t = 0.0
    for scene in film.board["scenes"]:
        sid, kind = scene["id"], scene["kind"]
        if kind == "credits":
            t, rolled = roll(t), True
            continue
        gap = scene.get("gap", GAP)
        at = t + (0.5 if kind == "intro" else 0.8)
        for item in by_scene.get(sid, []):
            if item["path"]:
                narration.append({**item, "start": round(at, 3)})
            captions += [{**c, "scene": sid} for c in caption_chunks(item["text"], at, item["duration"])]
            at += item["duration"] + gap
        speech_end = at - gap if by_scene.get(sid) else t
        content_timing = film.board.get("timing") == "content"
        content_duration = scene_seconds(scene, max(0, speech_end - t - .8)) if content_timing else 0
        requested_duration = max(content_duration, scene.get("duration") or 0)

        if kind in ("intro", "outro"):
            dur = round(max(OPEN[kind] if three_d else (3.0 if content_timing else 5.0), speech_end + 0.6 - t, requested_duration), 3)
            source = "stage" if three_d and panels else "backdrop"
            video.append({"kind": source, "scene": sid, "start": t, "in": 0.0, "duration": dur, "push": False})
            (stage if source == "stage" else backdrops).append({"scene": sid, "shot": kind, "seconds": dur + 0.5})
            title_at = 4.4 if kind == "intro" and source == "stage" else 0.5
            titles.append({"scene": sid, "layout": "center", "start": t + title_at,
                           "duration": dur - title_at if content_timing else min(TITLE[kind], dur - title_at)})
            if scene.get("image"):
                images.append({"scene": sid, "path": str(film.asset(scene["image"]["file"])),
                               "start": t + title_at, "duration": dur - title_at})
            t += dur
        elif kind == "card":
            dur = round(max(3.0 if content_timing else 4.0, speech_end + 0.8 - t, requested_duration), 3)
            video.append({"kind": "backdrop", "scene": sid, "start": t, "in": 0.0, "duration": dur, "push": False})
            backdrops.append({"scene": sid, "seconds": dur + 0.5})
            titles.append({"scene": sid, "layout": "center", "start": t + 0.3, "duration": dur - 0.6})
            if scene.get("image"):
                images.append({"scene": sid, "path": str(film.asset(scene["image"]["file"])),
                               "start": t + 0.3, "duration": dur - 0.6})
            t += dur
        else:
            foot_start = t
            if three_d and scene in segments:
                video.append({"kind": "stage", "scene": sid, "start": t, "in": EST_IN, "duration": EST, "push": False})
                focus = segments.index(scene)
                stage.append({"scene": sid, "shot": "establishing", "focus": focus, "seconds": EST + EST_IN + 0.5})
                foot_start = t + EST
            titles.append({"scene": sid, "layout": "lower", "start": t + 0.3, "duration": TITLE["segment"]})
            end = max(speech_end + 0.9, foot_start + (3.0 if content_timing else MIN_FOOTAGE), t + requested_duration)
            if content_timing:  # the lower third stays up for the scene, or as long as style.titleHold says
                titles[-1]["duration"] = min(end - t - .6, film.style.get("titleHold") or end)
            span = end - foot_start
            shots = [(shot_path(film, sid, i), s["in"], s["weight"]) for i, s in enumerate(scene["shots"])]
            avail = [max(0, probe(p)["duration"] - src_in - 0.3) for p, src_in, _ in shots]
            if any(a <= 0 for a in avail):
                raise SystemExit(f"{sid}: a clip starts beyond its end; choose an earlier start time")
            weight = sum(w for *_, w in shots)
            lengths = [min(a, span * w / weight) for a, (_, _, w) in zip(avail, shots)]
            short = span - sum(lengths)
            for i in range(len(shots)):  # give any shortfall to shots with room to spare
                extra = min(short, avail[i] - lengths[i])
                lengths[i] += extra
                short -= extra
            if short > 0.05:
                from .stages.footage import extend_clip
                path, src_in, weight = shots[-1]
                lengths[-1] += short
                shots[-1] = (extend_clip(film, path, src_in + lengths[-1] + .5), src_in, weight)
            ft = foot_start
            for n, ((path, src_in, _), d) in enumerate(zip(shots, lengths), 1):
                video.append({"kind": "footage", "scene": sid, "shot": n, "path": str(path), "start": round(ft, 4),
                              "in": src_in, "duration": round(d, 4), "push": film.style["pushIn"] > 0,
                              "capture": bool(scene["shots"][n - 1].get("capture"))})
                ft += d
            if scene.get("note"):
                notes.append({"scene": sid, "text": scene["note"], "start": foot_start + 0.3,
                              "duration": ft - foot_start - 0.6})
            t = ft

    if not rolled:
        t = roll(t)

    for clip in video:  # stage and backdrop clips are rendered later, to these names
        if clip["kind"] == "stage":
            clip["path"] = str(film.work / "stage" / f"{clip['scene']}.mp4")
        elif clip["kind"] == "backdrop":
            clip["path"] = str(film.work / "backdrops" / f"{clip['scene']}.mp4")
    for title in titles:
        title["path"] = str(film.work / "titles" / f"{title['scene']}.mov")
    plan = {"duration": round(t, 3), "video": video, "titles": titles if film.style["titles"] != "none" else
            [x for x in titles if x["layout"] == "credits"], "narration": narration, "captions": captions,
            "notes": notes, "stage": stage, "panels": panels, "backdrops": backdrops, "images": images}
    identify(plan, film.fmt["fps"])
    (film.work / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    print(f"  plan: {t:.1f}s, {len(video)} picture clips, {len(narration)} voice lines, {len(captions)} captions")
    return plan
