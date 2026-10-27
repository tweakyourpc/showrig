"""showrig diff: what changed in a film's FilmCraft project since Showrig built it.

Reads the project back, matches clips to beats by the stable id at the front of each clip name, and compares
them with the baseline in out/manifest.json. Reports per beat: deleted, moved, retimed (longer or shorter),
slipped (a new source in-point), moved to another track, relabelled, effects changed, gain changed, disabled,
media replaced, renamed, and title projects edited in EffectCraft; plus clips a person added, caption edits and
markers a person added. Writes out/diff.json. Exit code 0 either way; the report is the result.
"""
from __future__ import annotations

import json

from . import manifest, readback
from .project import Film
from .receipt import sha256


def compute(film: Film) -> dict:
    m = manifest.load(film)
    if not m:
        raise SystemExit(f"{film.root} has no out/manifest.json; build it with `showrig make` first")
    project = film.root / m["project"]["path"]
    if not project.exists():
        raise SystemExit(f"{project} is missing")
    fps = m["fps"]
    report = {"film": m["film"], "project": m["project"]["path"], "built": m["created"], "unchanged": False,
              "beats": {}, "added": [], "captions": [], "markers_added": [], "untouched": []}
    titles_edited = {b["id"] for b in m["beats"] if b.get("ecproj") and
                     sha256(film.root / b["ecproj"]["path"]) != b["ecproj"]["sha256"]}
    if sha256(project) == m["project"]["sha256"] and not titles_edited:
        report["unchanged"] = True
        report["untouched"] = [b["id"] for b in m["beats"]]
        return report
    back = readback.read(project, fps)
    by_id: dict[str, dict] = {}
    for c in sorted(back["clips"].values(), key=lambda c: (c["track"], c["start_f"])):
        if c["id"] and c["id"] not in by_id:
            by_id[c["id"]] = c
        else:  # a clip a person placed, or a copy of a beat
            report["added"].append({"name": c["name"], "track": c["track"], "start_f": c["start_f"], "dur_f": c["dur_f"],
                                    "copy_of": c["id"]})
    gone = set(m.get("deleted", []))
    for b in m["beats"]:
        c, ch = by_id.get(b["id"]), []
        if c is None:
            if b["id"] not in gone:
                ch.append({"change": "deleted"})
        else:
            if c["track"] != b["track"]:
                ch.append({"change": "track", "from": b["track"], "to": c["track"]})
            if c["start_f"] != b["start_f"]:
                ch.append({"change": "moved", "frames": c["start_f"] - b["start_f"]})
            if b["dur_f"] is not None and c["dur_f"] != b["dur_f"]:
                ch.append({"change": "retimed", "frames": c["dur_f"] - b["dur_f"]})
            if c["in_f"] != b["in_f"]:
                ch.append({"change": "slipped", "frames": c["in_f"] - b["in_f"]})
            if b.get("label") and c["label"] != b["label"]:
                ch.append({"change": "relabelled", "from": b["label"], "to": c["label"]})
            if b.get("fx") and c["fx"] != b["fx"]:
                ch.append({"change": "effects"})
            if (c["gain"] or 0) != (b.get("gain") or 0):
                ch.append({"change": "gain", "from": b.get("gain"), "to": c["gain"]})
            if not c["enabled"]:
                ch.append({"change": "disabled"})
            if b.get("item") is not None and c["item"] != b["item"]:
                ch.append({"change": "media replaced"})
            if c["name"] != b["name"]:
                ch.append({"change": "renamed", "to": c["name"]})
        if b["id"] in titles_edited:
            ch.append({"change": "title edited in EffectCraft"})
        if ch:
            report["beats"][b["id"]] = ch
        else:
            report["untouched"].append(b["id"])
    cues = readback.captions(project) or []
    for i, base in enumerate(m.get("captions", [])):
        if i >= len(cues):
            report["captions"].append({"id": base["id"], "change": "deleted"})
            continue
        cue, edits = cues[i], []
        if cue["text"] != base["text"]:
            edits.append({"change": "text", "from": base["text"], "to": cue["text"]})
        if abs(round(cue["start"] * fps) - base["start_f"]) > 1:
            edits.append({"change": "moved", "frames": round(cue["start"] * fps) - base["start_f"]})
        if edits:
            report["captions"].append({"id": base["id"], "edits": edits})
    report["captions"] += [{"id": None, "change": "added", "text": c["text"]} for c in cues[len(m.get("captions", [])):]]
    ours = list(m.get("markers", []))
    for mk in back["markers"]:
        if mk["name"] in ours:
            ours.remove(mk["name"])
        else:
            report["markers_added"].append(mk)
    return report


def describe(ch: dict, fps: int) -> str:
    def frames(n: int) -> str:
        return f"{'+' if n > 0 else ''}{n} frames ({n / fps:+.2f} s)"
    k = ch.get("change")
    if k == "moved":
        return f"moved {frames(ch['frames'])}"
    if k == "retimed":
        return f"{'longer' if ch['frames'] > 0 else 'shorter'} by {abs(ch['frames'])} frames"
    if k == "slipped":
        return f"source in-point {frames(ch['frames'])}"
    if k == "track":
        return f"moved from {ch['from']} to {ch['to']}"
    if k in ("relabelled", "gain"):
        return f"{k} {ch['from']} -> {ch['to']}"
    if k == "renamed":
        return f"renamed to {ch['to']!r}"
    return k


def show(film: Film, as_json: bool) -> int:
    r = compute(film)
    fps = (manifest.load(film) or {}).get("fps", film.fmt["fps"])
    (film.out / "diff.json").write_text(json.dumps(r, indent=1) + "\n")
    if as_json:
        print(json.dumps(r, indent=1))
        return 0
    print(f"{r['project']} against the build of {r['built']}:")
    if r["unchanged"]:
        print("  unchanged since Showrig built it")
        return 0
    for bid, changes in r["beats"].items():
        print(f"  {bid:22} " + "; ".join(describe(c, fps) for c in changes))
    for a in r["added"]:
        what = f"a copy of {a['copy_of']}" if a["copy_of"] else "added by hand"
        print(f"  {'(new clip)':22} {a['name']!r} on {a['track']} at frame {a['start_f']}, {a['dur_f']} frames: {what}")
    for c in r["captions"]:
        if c.get("edits"):
            print(f"  {c['id']:22} caption " + "; ".join(
                f"text {e['from']!r} -> {e['to']!r}" if e["change"] == "text" else describe(e, fps) for e in c["edits"]))
        else:
            print(f"  {str(c['id'] or '(new caption)'):22} caption {c['change']}" + (f": {c['text']!r}" if c.get("text") else ""))
    for mk in r["markers_added"]:
        print(f"  {'(new marker)':22} {mk['name']!r} at frame {mk['start_f']}: {(mk['comment'] or '').splitlines()[0][:60] if mk['comment'] else ''}")
    print(f"{len(r['beats'])} beats changed, {len(r['untouched'])} untouched, {len(r['added'])} clips added, "
          f"{len(r['captions'])} caption edits, {len(r['markers_added'])} markers added")
    return 0
