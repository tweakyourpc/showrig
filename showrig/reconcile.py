"""Reconcile: re-run a film without destroying what a person did to its FilmCraft project.

`showrig make` reconciles when the project was edited since Showrig built it, or holds locked beats. Starting from
the edited project (a copy goes to out/versions/ first), every beat is decided:

  yours        a beat a person changed (moved, trimmed, relabelled, re-graded, ...) is kept as it is, now and on
               every later run; if the storyboard also changed it, a CONFLICT marker says what Showrig wanted
  locked       `showrig lock` froze it: kept, with its media frozen in out/locked/
  deleted      a beat a person deleted stays deleted (`make --restore ID` brings it back)
  refreshed    an untouched beat whose content changed (a re-voiced line, a new title) at the same frames
  retimed      an untouched beat whose frames changed is placed again, if no clip of yours is in the way
  added        a beat new to the storyboard, placed where it fits
  removed      a beat the storyboard no longer has, unless it is yours
  conflict     anything that would overlap a clip of yours: not applied, a magenta CONFLICT marker instead

out/reconcile-report.json lists every decision. `showrig unlock ID|SCENE` hands a beat back to Showrig.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from . import diff, manifest, readback
from .project import Film
from .receipt import sha256
from .stages import assemble
from .stages.assemble import cmd

CONFLICT_COLOR = "Magenta"


def needed(film: Film) -> bool:
    """Reconcile instead of rebuilding when the project carries a person's work or a lock."""
    m = manifest.load(film)
    if not m or not (film.root / m["project"]["path"]).exists():
        return False
    if any(b.get("lock") or b.get("owner") == "human" for b in m["beats"]) or m.get("deleted"):
        return True
    return not diff.compute(film)["unchanged"]


def _span(b: dict) -> tuple[int, int]:
    return b["start_f"], b["start_f"] + max(1, b.get("dur_f") or 1)


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def run(film: Film, plan: dict, music: str | None, restore: tuple[str, ...] = ()) -> dict:
    m = manifest.load(film)
    project = film.root / m["project"]["path"]
    report_diff = diff.compute(film)
    fc = assemble.FilmCraft(film, project)
    caps = assemble.check_capabilities(fc.cli)
    ft = assemble.frames_to_ticks(film)
    keep = film.out / "versions" / f"{film.name}-{time.strftime('%Y%m%d-%H%M%S')}.fcproj"
    keep.parent.mkdir(exist_ok=True)
    shutil.copy2(project, keep)

    back = readback.read(project, film.fmt["fps"])
    cur: dict[str, dict] = {}
    foreign: list[dict] = []
    for c in sorted(back["clips"].values(), key=lambda c: (c["track"], c["start_f"])):
        if c["id"] and c["id"] not in cur:
            cur[c["id"]] = c
        else:
            foreign.append(c)  # placed by a person, or a copy of a beat: always in the way
    old = {b["id"]: b for b in m["beats"]}
    new = {b["id"]: b for b in assemble.intended(film, plan, music)}
    new_notes = {n["id"]: n for n in plan["notes"]}
    touched = set(report_diff["beats"])
    deleted = (set(m.get("deleted", [])) | {i for i, ch in report_diff["beats"].items()
                                            if any(c["change"] == "deleted" for c in ch)}) - set(restore)
    human = ({i for i in touched if i not in deleted} | {i for i, b in old.items() if b.get("owner") == "human"}) - set(restore)
    locked = {i for i, b in old.items() if b.get("lock")}

    decisions: list[dict] = []
    conflicts: list[dict] = []
    final: dict[str, dict] = {}
    clear: list[int] = []
    moving: dict[str, dict] = {}   # untouched beats that need new frames, or are new: placed if they fit
    refresh_path: list[tuple[dict, str]] = []

    def decide(bid: str, what: str, **more) -> None:
        decisions.append({"id": bid, "decision": what, **more})

    def rel(p: str | None) -> str | None:
        return manifest.rel(film, p)

    def same_content(o: dict, n: dict) -> bool:
        return rel(n["path"]) == o.get("path") and (o.get("sha256") is None or sha256(Path(n["path"])) == o["sha256"])

    def same_frames(o: dict, n: dict) -> bool:
        if o["track"] != n["track"] or o["start_f"] != n["start_f"]:
            return False
        if n["track"].startswith("A"):  # sound plays its whole file: a new length means placing it again
            return o.get("dur_f") is None or n.get("dur_f") is None or abs(o["dur_f"] - n["dur_f"]) <= 1
        return o["dur_f"] == n["dur_f"] and o["in_f"] == n["in_f"]

    for bid in sorted(set(old) | set(new) | set(new_notes)):
        o, n, c = old.get(bid), new.get(bid) or new_notes.get(bid), cur.get(bid)
        if bid in deleted:
            decide(bid, "deleted", note="stays deleted; `make --restore " + bid + "` brings it back")
            continue
        if bid in (human | locked) and c is not None:
            final[bid] = {**o, "clip": c["clip"], "owner": "human" if bid in human else o.get("owner")}
            who = "locked" if bid in locked else "yours"
            if n is not None and bid in new and not (same_frames(o, new[bid]) and same_content(o, new[bid])):
                conflicts.append({"id": bid, "at": c["start_f"], "track": c["track"],
                                  "why": f"{who}: kept; the storyboard now wants it at frame {new[bid]['start_f']} "
                                         f"for {new[bid]['dur_f'] or 'its whole'} frames"
                                         + ("" if same_content(o, new[bid]) else " with new content")})
            decide(bid, who)
            continue
        if n is None:  # gone from the storyboard
            if c is not None:
                clear.append(c["clip"])
            decide(bid, "removed")
            continue
        if bid in new_notes:  # graphics: re-made when anything about them changed
            if o and c and o["start_f"] == n["start_f"] and o["dur_f"] == n["dur_f"] and o.get("name", "").endswith(n["text"]):
                final[bid] = {**o, "clip": c["clip"]}
                continue
            if c is not None:
                clear.append(c["clip"])
            moving[bid] = {"id": bid, "scene": n["scene"], "kind": "note", "class": assemble.CLASSES["note"],
                           "track": "V3", "path": None, "start_f": n["start_f"], "dur_f": n["dur_f"], "in_f": 0,
                           "_entry": n, "_note": True}
            continue
        if o is None or c is None:
            moving[bid] = n
            continue
        if same_frames(o, n):
            if same_content(o, n):
                final[bid] = {**o, "clip": c["clip"]}
            else:
                if rel(n["path"]) != o.get("path"):
                    refresh_path.append(({**o, "clip": c["clip"]}, n["path"]))
                final[bid] = {**o, "clip": c["clip"], "path": n["path"]}
                decide(bid, "refreshed")
            continue
        moving[bid] = {**n, "_old_clip": c["clip"]}

    # Place what moves only where nothing that stays is in the way; a beat that cannot move stays where it was
    # and blocks too. Repeat until nothing changes.
    def blockers() -> dict[str, list[tuple[int, int]]]:
        spans: dict[str, list[tuple[int, int]]] = {}
        for b in final.values():
            if b["clip"] is not None and b["id"] in cur:
                spans.setdefault(cur[b["id"]]["track"], []).append(_span(cur[b["id"]]))
        for c in foreign:
            spans.setdefault(c["track"], []).append(_span(c))
        return spans

    while True:
        spans, stuck = blockers(), []
        for bid, n in moving.items():
            if any(_overlaps(_span(n), s) for s in spans.get(n["track"], [])):
                stuck.append(bid)
        if not stuck:
            break
        for bid in stuck:
            n = moving.pop(bid)
            if bid in cur:  # an existing beat stays at its old place
                final[bid] = {**old[bid], "clip": cur[bid]["clip"]}
            conflicts.append({"id": bid, "at": n["start_f"], "track": n["track"],
                              "why": f"not {'moved' if bid in cur else 'placed'}: frames {_span(n)[0]}-{_span(n)[1]} "
                                     f"on {n['track']} would overlap your edit"})
            decide(bid, "conflict")
    clear += [n.pop("_old_clip") for n in moving.values() if "_old_clip" in n]

    if clear:
        fc("r1-clear", [cmd("edit.clear", clips=sorted(set(clear)))])
    media = [n for n in moving.values() if not n.get("_note")]
    paths = sorted({n["path"] for n in media} | {p for _, p in refresh_path})
    items = dict(zip(paths, fc("r2-import", [cmd("file.import", paths=paths)])[0]["items"])) if paths else {}
    if refresh_path:
        # replaceFromBin renames a clip after its new media: put the beat id back in the same script
        fc("r3-refresh", [c for b, p in refresh_path for c in (
            cmd("clip.replaceFromBin", clips=[b["clip"]], item=items[p], keepSourceIn=True),
            cmd("clip.rename", clip=b["clip"], name=b["name"]))])
        for b, p in refresh_path:
            final[b["id"]]["item"] = items[p]
    placed = fc("r4-place", assemble.place_cmds(media, items, ft)) if media else []
    for n, res in zip(media, placed):
        n["clip"], n["item"] = res["clips"][0], items[n["path"]]
        decide(n["id"], "retimed" if n["id"] in old else "added")
    picture = sorted([b for b in new.values() if b["track"] == "V1"], key=lambda b: b["start_f"])
    motion = assemble.motion_cmds(film, media, picture, ft)
    notes = assemble.make_notes(film, fc, [n["_entry"] for n in moving.values() if n.get("_note")], ft)
    for nb in notes:
        decide(nb["id"], "retimed" if nb["id"] in old else "added")
    fresh = media + notes
    if motion or fresh:
        fc("r5-motion-names", motion + assemble.name_cmds(film, fresh))
    for b in fresh:
        b.pop("_entry", None)
        b.pop("_note", None)
        final[b["id"]] = b

    caption_note = _captions(film, fc, plan, m, report_diff, conflicts)
    if conflicts:
        fc("r6-conflicts", [cmd("markers.add", target="program", time=ft(c["at"]), name=f"CONFLICT {c['id']}",
                                comment=c["why"], color=CONFLICT_COLOR, durationFrames=1) for c in conflicts])
    assemble.interchange(film, fc)

    beats = []
    for b in final.values():
        b = dict(b)
        b.setdefault("name", b.get("name") or b["id"])
        beats.append(b)
    manifest.write(film, plan, beats, caps, assemble.PROMISE, deleted=sorted(deleted))
    report = {"film": film.board["title"], "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "backup": manifest.rel(film, str(keep)), "decisions": decisions, "conflicts": conflicts,
              "captions": caption_note, "added_by_hand": [{"name": c["name"], "track": c["track"],
                                                          "start_f": c["start_f"]} for c in foreign]}
    (film.out / "reconcile-report.json").write_text(json.dumps(report, indent=1) + "\n")
    counts: dict[str, int] = {}
    for d in decisions:
        counts[d["decision"]] = counts.get(d["decision"], 0) + 1
    kept_same = len([b for b in final if b not in {d["id"] for d in decisions}])
    print(f"  reconciled {project.relative_to(film.root)}: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
          + f", {kept_same} unchanged; {len(conflicts)} conflicts; captions {caption_note}")
    for c in conflicts:
        print(f"    CONFLICT {c['id']}: {c['why']}")
    return report


def _captions(film: Film, fc: assemble.FilmCraft, plan: dict, m: dict, d: dict, conflicts: list) -> str:
    """Rebuild the caption track when the storyboard changed it and nobody edited it; otherwise keep it."""
    fps = film.fmt["fps"]
    want = [(c["text"], c["start_f"], c["dur_f"]) for c in plan["captions"]]
    had = [(c["text"], c["start_f"], c["dur_f"]) for c in m.get("captions", [])]
    if want == had:
        return "unchanged"
    if d["captions"]:
        conflicts.append({"id": "captions", "at": 0, "track": "C1",
                          "why": "the storyboard changed the captions; your caption edits are kept"})
        return "kept (yours)"
    if film.board["captions"]["mode"] == "none" or not plan["captions"]:
        fc("r7-captions", [cmd("captions.deleteTrack", track="C1")])
        return "removed"
    fc("r7-captions", [cmd("captions.deleteTrack", track="C1"), *assemble.caption_cmds(film, plan)])
    fc("r8-export-srt", [cmd("captions.export", path=str(film.out / f"{film.name}.srt"), track="C1")])
    return f"rebuilt ({len(plan['captions'])} cues, {fps} fps)"


def lock(film: Film, target: str, on: bool) -> int:
    """Lock (or unlock) a beat or every beat of a scene. A locked beat's media is copied to out/locked/ and the
    clip points at the copy, so regenerating the original cannot change it. Unlocking also hands a beat a person
    edited back to Showrig: the next `make` may regenerate it."""
    m = manifest.load(film)
    if not m:
        raise SystemExit("no out/manifest.json; build the film first")
    scope = [b for b in m["beats"] if b["id"] == target or b.get("scene") == target]
    if not scope:
        raise SystemExit(f"no beat or scene {target!r}; ids are in out/manifest.json and at the start of clip names")
    project = film.root / m["project"]["path"]
    fc = assemble.FilmCraft(film, project)
    clips = {c["id"]: c for c in readback.read(project, m["fps"])["clips"].values() if c["id"]}
    changed = []
    for b in scope:
        if on and not b.get("lock"):
            info = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            src = film.root / b["path"] if b.get("path") else None
            if src and src.exists() and b["id"] in clips:
                dest = film.out / "locked" / (b["id"].replace("/", "__") + src.suffix)
                dest.parent.mkdir(exist_ok=True)
                shutil.copy2(src, dest)
                item = fc(f"lock-{b['id'].replace('/', '_')}", [cmd("file.import", paths=[str(dest)])])[0]["items"][0]
                clip = clips[b["id"]]["clip"]  # replaceFromBin renames the clip after the copy: rename it back
                fc(f"lock-{b['id'].replace('/', '_')}-swap", [cmd("clip.replaceFromBin", clips=[clip], item=item,
                                                                    keepSourceIn=True),
                                                                cmd("clip.rename", clip=clip, name=b["name"])])
                b["path"], b["item"], b["sha256"] = manifest.rel(film, str(dest)), item, sha256(dest)
                info["media"] = b["path"]
            b["lock"] = info
            changed.append(b["id"])
        elif not on and (b.get("lock") or b.get("owner")):
            b["lock"], b["owner"] = None, None
            changed.append(b["id"])
    m["project"]["sha256"] = sha256(project)  # the swap is Showrig's own doing, not a person's edit
    manifest.path(film).write_text(json.dumps(m, indent=1) + "\n")
    print(f"{'locked' if on else 'unlocked'}: {', '.join(changed) or 'nothing to change'}")
    return 0
