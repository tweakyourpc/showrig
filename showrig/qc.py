"""Quality gates on the finished film.

  showrig qc FILM [--video FILE]

Speech: the final MP4 is transcribed again and every narration line is looked for in what was heard, in order.
A line whose words come back below the minimum recall (the music masked a word, a voice clip was trimmed, the
synthesiser mangled a name) is heard again on its own stretch of the film, since a long transcript can drift; if it
is still short, it fails. Lines whose voice beat a person deleted are not expected. The transcriber is
SHOWRIG_ASR (a command with {in}, {out} and {lang}), else `whisper-ctranslate2` on the CPU; with none, the check is
skipped and says so.

Style: shot lengths, cuts per minute, caption reading speed and loudness, measured from the manifest and the MP4,
and compared with "style": {"targets": {...}} when the storyboard has targets: the start of measured style packs.

Storyboard: "qc": {"asr": "fail" | "warn" | "off", "minRecall": 0.8}. New films fail; older films warn.
Writes out/qc-report.json and out/style-report.json.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import statistics
import subprocess
import tempfile
from pathlib import Path

from . import manifest
from .project import Film
from .stages.voice import spoken


NUMBERS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
           "seventeen eighteen nineteen twenty").split()


def words(text: str) -> list[str]:
    """Lower-case words for comparing speech; digits and letters are split ("7zip" -> "seven", "zip") and small
    numbers spelled out, because a transcriber writes "7-Zip" where the narration says "seven zip". "dot" is
    dropped and spelled-out letters joined ("p c" -> "pc"), because it writes "github.com" and "PC" where the
    voice says "github dot com" and "p c"."""
    out: list[str] = []
    spelling = False  # the last word is a run of spelled-out letters
    for w in re.findall(r"[a-z]+|[0-9]+", text.lower().replace("'", "")):
        w = NUMBERS[int(w)] if w.isdigit() and int(w) < len(NUMBERS) else w
        if w == "dot":
            continue
        letter = len(w) == 1 and w not in "ai"
        if letter and spelling:
            out[-1] += w
        else:
            out.append(w)
        spelling = letter
    return out


def asr(audio: Path, out: Path, lang: str = "en") -> tuple[str, str] | None:
    """Transcribe; returns (text, how) or None when no transcriber is installed."""
    out.mkdir(parents=True, exist_ok=True)
    template = os.environ.get("SHOWRIG_ASR")
    if template:
        cmd = [part.format(**{"in": str(audio), "out": str(out), "lang": lang}) for part in template.split()]
    elif shutil.which("whisper-ctranslate2"):
        cmd = ["whisper-ctranslate2", str(audio), "--model", "small", "--language", lang, "--device", "cpu",
               "--compute_type", "int8", "--output_dir", str(out), "--output_format", "txt", "--verbose", "False"]
    else:
        return None
    r = subprocess.run(cmd, capture_output=True, text=True)
    txt = out / (audio.stem + ".txt")
    if r.returncode != 0 or not txt.exists():
        raise SystemExit(f"the transcriber failed ({' '.join(cmd[:1])}): {(r.stderr or r.stdout).strip()[-300:]}")
    return txt.read_text(), " ".join(cmd[:1])


def speech(film: Film, video: Path) -> dict:
    """Align what was heard against the narration lines that should be there."""
    m = manifest.load(film) or {}
    policy = {"asr": "warn", "minRecall": 0.8, **(film.board.get("qc") or {})}
    if policy["asr"] == "off":
        return {"ok": True, "skipped": "qc.asr is off for this film"}
    deleted = set(m.get("deleted", []))
    beats = {b["id"]: b for b in m.get("beats", [])}
    lines, n = [], {}
    for scene in film.scenes():
        for text in scene.get("lines", []):
            n[scene["id"]] = n.get(scene["id"], 0) + 1
            bid = f"{scene['id']}/voice{n[scene['id']]}"
            if bid not in deleted and film.board["voice"]["source"] != "none":
                lines.append({"id": bid, "text": text, "words": words(spoken(film, text))})
    if not lines:
        return {"ok": True, "skipped": "no narration"}
    with tempfile.TemporaryDirectory() as tmp:
        heard = asr(video, Path(tmp))
    if heard is None:
        return {"ok": True, "skipped": "no transcriber installed (whisper-ctranslate2 or SHOWRIG_ASR)"}
    text, how = heard
    got = words(text)
    want = [w for line in lines for w in line["words"]]
    owner = [i for i, line in enumerate(lines) for _ in line["words"]]
    hit = [False] * len(want)
    for block in difflib.SequenceMatcher(None, want, got, autojunk=False).get_matching_blocks():
        for k in range(block.a, block.a + block.size):
            hit[k] = True
    joined = "".join(got)
    out_lines, ok = [], True
    for i, line in enumerate(lines):
        idx = [k for k, o in enumerate(owner) if o == i]
        recall = sum(hit[k] for k in idx) / len(idx) if idx else 1.0
        missing = [want[k] for k in idx if not hit[k]]
        passed = recall >= policy["minRecall"]
        if not passed and "".join(line["words"]) in joined:  # heard, but spelled joined up ("Moonstarer", "OpenStreetMap")
            passed, missing = True, []
        entry = {"id": line["id"], "text": line["text"], "recall": round(recall, 3), "missing": missing, "ok": passed}
        if not passed:  # a long transcript can drift near the end: listen again to just this line's stretch
            alone = relisten(film, video, beats.get(line["id"]), line["words"])
            if alone is not None:
                entry["alone"] = {"recall": round(alone[0], 3), "heard": alone[1]}
                if alone[0] >= policy["minRecall"]:
                    entry["ok"] = passed = True
        ok &= passed
        out_lines.append(entry)
    return {"ok": ok, "policy": policy["asr"], "minRecall": policy["minRecall"], "transcriber": how,
            "heard": text.strip(), "lines": out_lines}


def relisten(film: Film, video: Path, beat: dict | None, want: list[str]) -> tuple[float, str] | None:
    """Transcribe only a voice beat's stretch of the film (with half a second either side); returns the line's
    recall in it and what was heard, or None when the beat has no frames in the manifest."""
    if not beat or beat.get("start_f") is None or not beat.get("dur_f"):
        return None
    fps = film.fmt["fps"]
    start, dur = max(0.0, beat["start_f"] / fps - 0.5), beat["dur_f"] / fps + 1.0
    with tempfile.TemporaryDirectory() as tmp:
        clip = Path(tmp) / "line.wav"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(video),
                            "-vn", "-ac", "1", "-ar", "16000", str(clip)], capture_output=True, text=True)
        if r.returncode:
            return None
        heard = asr(clip, Path(tmp) / "asr")
    if heard is None:
        return None
    got = words(heard[0])
    hits = sum(b.size for b in difflib.SequenceMatcher(None, want, got, autojunk=False).get_matching_blocks())
    if "".join(want) in "".join(got):
        hits = len(want)
    return (hits / len(want) if want else 1.0), heard[0].strip()


def loudness(video: Path) -> float | None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-map", "0:a?", "-af", "ebur128",
                        "-f", "null", "-"], capture_output=True, text=True)
    found = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(found[-1]) if found else None


def style(film: Film, video: Path) -> dict:
    m = manifest.load(film) or {}
    fps = m.get("fps", film.fmt["fps"])
    shots = sorted((b for b in m.get("beats", []) if b["track"] == "V1" and b.get("dur_f")), key=lambda b: b["start_f"])
    lengths = [b["dur_f"] / fps for b in shots]
    duration = (m.get("duration_f") or 0) / fps
    cps = [len(c["text"]) / (c["dur_f"] / fps) for c in m.get("captions", []) if c.get("dur_f")]
    measured = {
        "duration": round(duration, 2), "shots": len(lengths),
        "medianShot": round(statistics.median(lengths), 2) if lengths else None,
        "shortestShot": round(min(lengths), 2) if lengths else None, "longestShot": round(max(lengths), 2) if lengths else None,
        "cutsPerMinute": round(60 * max(0, len(lengths) - 1) / duration, 1) if duration else None,
        "captionCharsPerSecond": round(max(cps), 1) if cps else None, "lufs": loudness(video),
    }
    targets = (film.board.get("style") or {}).get("targets") or {}
    checks = {}
    for key, rng in targets.items():
        v = measured.get(key)
        if isinstance(rng, list) and len(rng) == 2 and v is not None:
            checks[key] = {"value": v, "target": rng, "ok": rng[0] <= v <= rng[1]}
    return {"measured": measured, "targets": checks, "ok": all(c["ok"] for c in checks.values())}


def run(film: Film, video: Path | None = None, gate: bool = True) -> dict:
    video = video or film.out / f"{film.name}.mp4"
    if not video.exists():
        raise SystemExit(f"{video} not found; render the film first")
    sp = speech(film, video)
    st = style(film, video)
    report = {"film": film.board["title"], "video": video.name, "speech": sp, "style": st}
    (film.out / "qc-report.json").write_text(json.dumps(report, indent=1) + "\n")
    (film.out / "style-report.json").write_text(json.dumps(st, indent=1) + "\n")
    if "skipped" in sp:
        print(f"  qc speech: skipped ({sp['skipped']})")
    else:
        bad = [line for line in sp["lines"] if not line["ok"]]
        print(f"  qc speech ({sp['transcriber']}): {len(sp['lines']) - len(bad)}/{len(sp['lines'])} lines heard")
        for line in bad:
            print(f"    MISSING in {line['id']}: {' '.join(line['missing'])}  (recall {line['recall']:.0%} of {line['text']!r})")
        for line in sp["lines"]:
            if line["ok"] and "alone" in line:
                print(f"    {line['id']}: heard on a second listen ({line['alone']['recall']:.0%})")
    ms = st["measured"]
    print(f"  qc style: {ms['shots']} shots, median {ms['medianShot']} s, {ms['cutsPerMinute']} cuts/min, "
          f"{ms['lufs']} LUFS" + "".join(f"; {k} {c['value']} {'ok' if c['ok'] else 'outside'} {c['target']}"
                                          for k, c in st["targets"].items()))
    if gate and not sp["ok"] and sp.get("policy") == "fail":
        raise SystemExit("qc failed: narration words are missing from the final mix (out/qc-report.json)")
    return report
