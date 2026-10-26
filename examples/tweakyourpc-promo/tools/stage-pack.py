#!/usr/bin/env python3
"""Render the film's 3D shots on another computer (one with a real GPU), then bring them back.

  tools/stage-pack.py export [PACK_DIR]     write a self-contained pack (default: ../tweakyourpc-stage-pack)
  tools/stage-pack.py import PACK_DIR       copy the rendered shots back into the film, marked up to date

The pack holds the eight Blender jobs at final quality, the videos that play on the screens, and
Showrig's stage script. On the other computer it needs only Blender 4.x, on Linux, Windows or macOS:

  blender -b --python render_all.py

That renders every shot to rendered/<scene>.mp4 (and a reopenable .blend). Copy the pack folder back,
run `tools/stage-pack.py import <pack>`, then `./build.sh`: it reuses the imported shots and goes
straight on to the music, the FilmCraft edit and the final render.

Export after a build (`./build.sh --draft` is enough), so the plan and the screen videos exist. Import
refuses shots that no longer match the film, for example after the storyboard changed what they show.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
SHOWRIG_ROOT = KIT.parent.parent
sys.path.insert(0, str(SHOWRIG_ROOT))

from showrig import tools  # noqa: E402
from showrig.project import Film, probe  # noqa: E402
from showrig.stages.stage3d import job_key, job_spec  # noqa: E402

FILM = SHOWRIG_ROOT / "films" / "tweakyourpc-promo"

RUNNER = '''"""Render every job in jobs/ with this Blender: blender -b --python render_all.py

Each shot runs in its own Blender process (as it does at home) and lands in rendered/. Shots that are
already rendered are skipped, so the script can be stopped and started again.
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import bpy

pack = Path(__file__).resolve().parent
jobs = sorted((pack / "jobs").glob("*.json"))
(pack / "rendered").mkdir(exist_ok=True)
for n, path in enumerate(jobs, 1):
    job = json.loads(path.read_text())
    movie = pack / job["movie"]
    if movie.exists() and movie.stat().st_size > 0:
        print(f"[{n}/{len(jobs)}] {path.stem}: already rendered")
        continue
    job["movie"], job["blend"] = str(movie), str(pack / job["blend"])
    for panel in job["panels"]:
        panel["video"] = str(pack / panel["video"])
    run = pack / "rendered" / f"{path.stem}.run.json"
    run.write_text(json.dumps(job))
    print(f"[{n}/{len(jobs)}] {path.stem}: {job['seconds']:.1f}s at {job['width']}x{job['height']}", flush=True)
    t0 = time.time()
    subprocess.run([bpy.app.binary_path, "-b", "-P", str(pack / "blender_stage.py"), "--", str(run),
                    str(pack / "rendered" / f"{path.stem}.frames")], check=True)
    run.unlink()
    shutil.rmtree(pack / "rendered" / f"{path.stem}.frames", ignore_errors=True)
    print(f"    done in {time.time() - t0:.0f}s", flush=True)
print("All shots rendered. Copy this folder back and run: tools/stage-pack.py import <this folder>")
'''


def plan(film: Film) -> dict:
    path = film.work / "plan.json"
    if not path.exists():
        raise SystemExit(f"{path} not found: build the film first (./build.sh --draft)")
    return json.loads(path.read_text())


def export(pack: Path) -> None:
    film = Film.load(FILM)
    p = plan(film)
    if not p["stage"]:
        raise SystemExit("this film has no 3D shots")
    if pack.exists():
        shutil.rmtree(pack)
    (pack / "jobs").mkdir(parents=True)
    (pack / "footage").mkdir()
    manifest = {}
    for panel in p["panels"]:
        shutil.copy2(film.root / panel["video"], pack / "footage" / Path(panel["video"]).name)
    for job in p["stage"]:
        spec = job_spec(film, p, job, quality="final")
        manifest[job["scene"]] = job_key(film, p, spec)
        portable = {**spec, "panels": [{**x, "video": f"footage/{Path(x['video']).name}"} for x in spec["panels"]],
                    "movie": f"rendered/{job['scene']}.mp4", "blend": f"rendered/{job['scene']}.blend"}
        (pack / "jobs" / f"{job['scene']}.json").write_text(json.dumps(portable, indent=2))
    shutil.copy2(tools.ASSETS / "blender_stage.py", pack / "blender_stage.py")
    (pack / "render_all.py").write_text(RUNNER)
    (pack / "manifest.json").write_text(json.dumps({"film": film.name, "keys": manifest}, indent=2))
    (pack / "README.txt").write_text(
        f"The {len(manifest)} 3D shots of '{film.board['title']}', ready to render with Blender 4.x.\n\n"
        "  blender -b --python render_all.py\n\n"
        "Then copy this whole folder back and run tools/stage-pack.py import <folder> in the promo kit.\n")
    size = sum(f.stat().st_size for f in pack.rglob("*") if f.is_file()) / 1e6
    print(f"wrote {pack}: {len(manifest)} shots, {size:.0f} MB")
    print(f"on the other computer: cd {pack.name} && blender -b --python render_all.py")


def import_(pack: Path) -> None:
    film = Film.load(FILM)
    p = plan(film)
    keys = json.loads((pack / "manifest.json").read_text())["keys"]
    stage = film.work / "stage"
    stage.mkdir(parents=True, exist_ok=True)
    done = 0
    for job in p["stage"]:
        scene = job["scene"]
        movie = pack / "rendered" / f"{scene}.mp4"
        key = job_key(film, p, job_spec(film, p, job, quality="final"))
        if keys.get(scene) != key:
            print(f"  {scene}: skipped, the film changed since the pack was made (render it here, or export again)")
            continue
        if not movie.exists():
            print(f"  {scene}: not rendered in the pack yet")
            continue
        info = probe(movie)
        if abs(info["duration"] - job["seconds"]) > 0.5:
            print(f"  {scene}: skipped, the movie is {info['duration']:.1f}s but the shot needs {job['seconds']:.1f}s")
            continue
        shutil.copy2(movie, stage / f"{scene}.mp4")
        if (pack / "rendered" / f"{scene}.blend").exists():
            shutil.copy2(pack / "rendered" / f"{scene}.blend", stage / f"{scene}.blend")
        film.stamp(stage / f"{scene}.mp4", key)
        done += 1
        print(f"  {scene}: imported")
    print(f"{done} of {len(p['stage'])} shots imported. Run ./build.sh to finish the film.")


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["export"]:
        export(Path(args[1]).resolve() if len(args) > 1 else KIT.parent / "tweakyourpc-stage-pack")
    elif args[:1] == ["import"] and len(args) > 1:
        import_(Path(args[1]).resolve())
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
