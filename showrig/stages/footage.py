"""Footage: bring every shot to the film's size and frame rate, recording browser captures first."""
from __future__ import annotations

import json
from pathlib import Path

from .. import tools
from ..project import Film, probe, run


def shot_path(film: Film, sid: str, i: int):
    return film.work / "footage" / f"{sid}-{i + 1:02}.mp4"


HOLD = 4.0  # seconds of held last frame at the end of every clip, so narration never outruns the picture


def normalize_clip(film: Film, src, dst, seconds: float = 8) -> None:
    w, h, fps = film.fmt["width"], film.fmt["height"], film.fmt["fps"]
    info = probe(src)
    if info["width"] is None:
        raise SystemExit(f"{src}: no video stream")
    if abs(info["width"] / info["height"] - w / h) <= 0.02:
        vf = f"scale={w}:{h}:flags=lanczos,fps={fps},tpad=stop_mode=clone:stop_duration={HOLD},format=yuv420p"
    else:  # fit inside the frame over a blurred, darkened fill of itself
        vf = (f"split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
              f"gblur=sigma=40,eq=brightness=-0.18[bg];[b]scale={w}:{h}:force_original_aspect_ratio=decrease:"
              f"flags=lanczos[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={fps},"
              f"tpad=stop_mode=clone:stop_duration={HOLD},format=yuv420p")
    inputs = ["-loop", "1", "-framerate", fps, "-i", src, "-t", seconds] if info["still"] else ["-i", src]
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", vf, "-an", *tools.h264_encoder(),
         "-movflags", "+faststart", dst], film.log(f"footage-{dst.stem}.log"))


def extend_clip(film: Film, src: Path, seconds: float) -> Path:
    """Hold the last picture long enough to finish narration without cutting it off."""
    dst = src.with_name(src.stem + "-held.mp4")
    key = film.fingerprint(src, seconds)
    if not film.fresh(dst, key):
        run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", f"tpad=stop_mode=clone:stop_duration={seconds}",
             "-t", seconds, "-an", *tools.h264_encoder(), "-movflags", "+faststart", dst],
            film.log(f"hold-{src.stem}.log"))
        film.stamp(dst, key)
    return dst


def capture(film: Film, cap: dict, dst) -> None:
    if not (tools.node() and tools.playwright()):
        raise SystemExit("browser captures need node and Playwright (see `showrig doctor`)")
    url = cap["url"] if "://" in cap["url"] else film.asset(cap["url"]).resolve().as_uri()
    job = {**cap, "url": url, "out": str(dst), "width": film.fmt["width"], "height": film.fmt["height"],
           "fps": film.fmt["fps"], "hold": HOLD, "playwright": tools.playwright(), "codec": tools.h264_encoder()}
    job_file = dst.with_suffix(".job.json")
    job_file.write_text(json.dumps(job, indent=2))
    res = run([tools.node(), tools.ASSETS / "capture.mjs", job_file], film.log(f"capture-{dst.stem}.log"),
              timeout=900)
    print(f"    recorded {res.stdout.strip().splitlines()[-1]}")


def build(film: Film) -> None:
    (film.work / "footage").mkdir(parents=True, exist_ok=True)
    for scene in film.scenes("segment"):
        for i, shot in enumerate(scene["shots"]):
            dst = shot_path(film, scene["id"], i)
            src = film.asset(shot["file"]) if shot.get("file") else None
            if src:
                info = probe(src)
                if info["still"] and shot.get("in", 0) != 0:
                    raise SystemExit(f"{src.name}: still images start at zero; use scene timing to keep them on screen longer")
                if not info["still"] and shot.get("in", 0) >= info["duration"]:
                    raise SystemExit(f"{src.name}: the start time is beyond the end of this clip")
            from ..studio import scene_seconds
            duration = max(8, scene_seconds(scene))
            url = (shot.get("capture") or {}).get("url", "")
            page = film.asset(url) if url and "://" not in url else None  # an edited local page is captured again
            key = film.fingerprint(film.fmt, src or shot["capture"], shot.get("fit"), HOLD, duration, "stills-v1",
                                   *([page] if page else []))
            if film.fresh(dst, key):
                continue
            print(f"  footage {dst.name}: {'normalizing ' + src.name if src else 'recording ' + shot['capture']['url']}")
            if src:
                normalize_clip(film, src, dst, duration)
            else:
                capture(film, shot["capture"], dst)
            film.stamp(dst, key)
