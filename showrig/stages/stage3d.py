"""The 3D showcase in Blender, and plain moving backdrops for cards, credits and films without 3D."""
from __future__ import annotations

import json
import shutil
import time
import tempfile
from pathlib import Path

from .. import tools
from ..project import Film, run


def job_spec(film: Film, plan: dict, job: dict, quality: str | None = None) -> dict:
    """Everything Blender needs for one shot."""
    return {**job, "fps": film.fmt["fps"], "width": film.fmt["width"], "height": film.fmt["height"],
            "quality": quality or film.style["quality"], "background": film.style["background"], "panels": plan["panels"]}


def job_key(film: Film, plan: dict, spec: dict) -> str:
    """The shot's fingerprint: its spec, the panel videos and the stage script. A shot rendered elsewhere
    from the same spec (tools that export and import stage jobs) carries the same key."""
    return film.fingerprint(spec, [p["video"] for p in plan["panels"]],
                            [film.root.joinpath(p["video"]) for p in plan["panels"]],
                            (tools.ASSETS / "blender_stage.py").read_text())


def build(film: Film, plan: dict) -> None:
    out = film.work / "stage"
    out.mkdir(parents=True, exist_ok=True)
    for job in plan["stage"]:
        dst = out / f"{job['scene']}.mp4"
        spec = job_spec(film, plan, job)
        key = job_key(film, plan, spec)
        if film.fresh(dst, key):
            continue
        if not tools.blender():
            raise SystemExit("the 3D showcase needs Blender; install it or set style.showcase3d to false")
        frames = Path(tempfile.mkdtemp(prefix=f"{job['scene']}-", suffix=".frames", dir=out))
        job_file = out / f"{job['scene']}.job.json"
        job_file.write_text(json.dumps({**spec, "blend": str(out / f"{job['scene']}.blend")}, indent=2))
        print(f"  blender {job['scene']} ({job['shot']}, {job['seconds']:.1f}s, {film.style['quality']})", flush=True)
        t0 = time.time()
        run([tools.blender(), "-b", "-P", tools.ASSETS / "blender_stage.py", "--", job_file, frames],
            film.log(f"blender-{job['scene']}.log"))
        expected = round(spec["seconds"] * spec["fps"])
        if any(not (frames / f"f_{i:04}.png").is_file() for i in range(1, expected + 1)):
            raise SystemExit(f"Blender produced an incomplete frame sequence. Frames retained in {frames}")
        run(["ffmpeg", "-v", "error", "-y", "-framerate", film.fmt["fps"], "-start_number", "1", "-i", frames / "f_%04d.png",
             "-vf", f"scale={film.fmt['width']}:{film.fmt['height']}:flags=lanczos,format=yuv420p",
             *tools.h264_encoder(), "-movflags", "+faststart", dst], film.log(f"blender-{job['scene']}-encode.log"))
        shutil.rmtree(frames)
        film.stamp(dst, key)
        print(f"    done in {time.time() - t0:.0f}s")


def backdrops(film: Film, plan: dict) -> None:
    """A slow drifting gradient in the film's background and accent colours."""
    out = film.work / "backdrops"
    out.mkdir(parents=True, exist_ok=True)
    w, h, fps = film.fmt["width"], film.fmt["height"], film.fmt["fps"]
    bg, accent = film.style["background"].lstrip("#"), film.style["accent"].lstrip("#")
    studio = bool(film.style.get("design"))
    if studio:
        accent = "".join(f"{round(int(bg[i:i+2], 16) * .78 + int(accent[i:i+2], 16) * .22):02x}" for i in (0, 2, 4))
    for job in plan["backdrops"]:
        dst = out / f"{job['scene']}.mp4"
        key = film.fingerprint(job, film.fmt, bg, accent, studio)
        if film.fresh(dst, key):
            continue
        src = (f"gradients=s={w}x{h}:r={fps}:d={job['seconds']}:n=3:c0=0x{bg}:c1=0x{bg}:c2=0x{accent}:"
               f"speed=0.004:type=radial,eq=brightness=-0.06:saturation=0.8,"
               f"noise=alls=4:allf=t,vignette=PI/4,format=yuv420p")
        if studio:
            src = (f"gradients=s={w}x{h}:r={fps}:d={job['seconds']}:n=2:c0=0x{bg}:c1=0x{accent}:"
                   "seed=7:speed=0.004:type=linear,format=yuv420p")
        run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src, *tools.h264_encoder(), dst],
            film.log(f"backdrop-{job['scene']}.log"))
        film.stamp(dst, key)
