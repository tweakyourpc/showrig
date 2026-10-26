"""Voiceover: generated offline with Kokoro, or the user's own recordings, levelled to one loudness.

Writes work/voice/<scene>-NN.wav and work/voice/manifest.json. With no voiceover, lines still
become captions, timed at a comfortable reading speed.
"""
from __future__ import annotations

import json

from .. import tools
from ..project import Film, probe, run

LEVEL = ("highpass=f=70,acompressor=threshold=-20dB:ratio=2.5:attack=5:release=80,"
         "loudnorm=I=-17:TP=-2:LRA=6")
READ_CPS = 15  # characters per second for captions with no voice


def spoken(film: Film, text: str) -> str:
    for word, say in film.board["voice"].get("say", {}).items():
        text = text.replace(word, say)
    return text


def build(film: Film) -> list[dict]:
    out = film.work / "voice"
    out.mkdir(parents=True, exist_ok=True)
    v = film.board["voice"]
    todo, manifest = [], []
    for scene in film.scenes():
        for i, text in enumerate(scene["lines"]):
            lid = f"{scene['id']}-{i + 1:02}"
            item = {"id": lid, "scene": scene["id"], "text": text, "path": None,
                    "duration": round(max(1.6, len(text) / READ_CPS), 3)}
            manifest.append(item)
            if v["source"] == "none":
                continue
            dst = out / f"{lid}.wav"
            item["path"] = str(dst)
            if v["source"] == "files":
                src = film.asset(scene["voice"][i])
                key = film.fingerprint(src, LEVEL)
            else:
                src = None
                key = film.fingerprint(spoken(film, text), v["engine"], v["voice"], v["speed"], LEVEL)
            if not film.fresh(dst, key):
                todo.append((item, src, dst, key))
    if todo and v["source"] == "tts":
        py = tools.tts_python()
        if not py:
            raise SystemExit("voice source is tts but no Python with kokoro was found; set SHOWRIG_TTS_PYTHON")
        job = {"voice": v["voice"], "speed": v["speed"],
               "items": [{"text": spoken(film, it["text"]), "out": str(d.with_suffix(".raw.wav"))}
                         for it, _, d, _ in todo]}
        job_file = out / "tts-job.json"
        job_file.write_text(json.dumps(job, indent=2))
        print(f"  voice: generating {len(todo)} lines with Kokoro ({v['voice']})")
        run([py, tools.ASSETS / "tts_kokoro.py", job_file], film.log("voice-tts.log"))
    for _, src, dst, key in todo:
        raw = src or dst.with_suffix(".raw.wav")
        run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-af", LEVEL, "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
             dst], film.log(f"voice-{dst.stem}.log"))
        if not src:
            raw.unlink()
        film.stamp(dst, key)
    for item in manifest:
        if item["path"]:
            item["duration"] = round(probe(item["path"])["duration"], 3)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if v["source"] != "none":
        print(f"  voice: {len(manifest)} lines, {sum(m['duration'] for m in manifest):.1f}s of speech")
    return manifest
