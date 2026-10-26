"""The README hero: Showrig's pipeline as a row of its own glowing screens, receding from the finished
film back to the storyboard, with dark space on the left for the title.

blender -b -P hero_scene.py -- <job.json> <out.png>
  job: {width, height, quality, background, panels: [{video, color}]}  (panels: storyboard first)

It reuses the film stage's screens, floor, camera and bloom from showrig/assets/blender_stage.py.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

STAGE = Path(__file__).resolve().parents[2] / "showrig" / "assets" / "blender_stage.py"
argv = sys.argv[sys.argv.index("--") + 1:]
job = json.loads(Path(argv[0]).read_text())
job.update(fps=30, seconds=1, shot="hero")
sys.argv[sys.argv.index("--") + 1:] = [argv[0] + ".stage.json", str(Path(argv[1]).parent)]
Path(argv[0] + ".stage.json").write_text(json.dumps(job))
stage: dict = {"__name__": "blender_stage", "__file__": str(STAGE)}
exec(compile(STAGE.read_text().removesuffix("main()\n"), str(STAGE), "exec"), stage)

scene = stage["reset"]()
scene.frame_start = scene.frame_end = scene.frame_current = 1
stage["floor"]()
for attr in ("use_ssr", "use_gtao"):  # floor reflections in the Blender 4.0 EEVEE
    if hasattr(scene.eevee, attr):
        setattr(scene.eevee, attr, True)
# a row of screens receding from the camera: the finished film nearest, the storyboard farthest
cam_at = Vector(job.get("cam", (-2.0, -7.5, 1.9)))
near, step = Vector(job.get("near", (3.6, -1.0, 1.25))), Vector(job.get("step", (-1.5, 4.2, 0)))
roots = []
for i, p in enumerate(reversed(job["panels"])):
    loc = near + step * i
    to_cam = cam_at - loc
    yaw = math.degrees(math.atan2(to_cam.x, -to_cam.y)) + job.get("turn", -28)
    roots.insert(0, stage["panel"](p, tuple(loc), yaw))
cam, tgt = stage["camera"](lens=job.get("lens", 30), fstop=job.get("fstop", 2.8))
stage["move"](cam, tgt, 1, tuple(cam_at), job.get("target", (0.6, 4.0, 1.4)))
stage["compositor"](scene)
scene.render.filepath = argv[1]
scene.render.use_file_extension = False
bpy.ops.render.render(write_still=True)

# where each screen's top-left corner lands in the picture (0-1 from the top left), for the labels
bpy.context.view_layer.update()
corner = Vector((-stage["PANEL_W"] / 2, 0, stage["PANEL_H"] / 2))
spots = []
for root in roots:
    x, y, _ = world_to_camera_view(scene, cam, root.matrix_world @ corner)
    spots.append({"x": x, "y": 1 - y})
Path(argv[1] + ".json").write_text(json.dumps(spots))
