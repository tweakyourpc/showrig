"""Inside Blender's GUI: step a stage scene frame by frame and screenshot the whole window each time.

  blender --window-geometry 0 0 1920 1080 SCENE.blend --python blender_ui.py -- OUT_DIR FIRST LAST

Run by record-ui.sh on a virtual display. Each frame is grabbed from the display with FFmpeg after
Blender has redrawn it (Blender's own screenshot reads a black front buffer under Xvfb). Material
Preview takes one sample per redraw, so every grab is a settled image; the scene is never saved.
"""
import os
import subprocess
import sys

import bpy

out, first, last = sys.argv[sys.argv.index("--") + 1:][:3]
first, last = int(first), int(last)
frame = first


def view3d():
    return next(a for a in bpy.context.screen.areas if a.type == "VIEW_3D")


def setup():
    space = view3d().spaces.active
    space.shading.type = "MATERIAL"
    space.region_3d.view_perspective = "CAMERA"
    space.overlay.show_relationship_lines = False
    bpy.context.scene.eevee.taa_samples = 1
    for obj in bpy.data.objects:
        obj.select_set(False)
    bpy.context.scene.frame_set(frame)
    bpy.app.timers.register(shoot, first_interval=6.0)  # shaders compile and the movies open


def shoot():
    global frame
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "x11grab", "-draw_mouse", "0", "-video_size", "1920x1080", "-i", os.environ["DISPLAY"],
                    "-frames:v", "1", f"{out}/f{frame - first:05d}.png"], check=True)
    frame += 1
    if frame > last:
        bpy.ops.wm.quit_blender()
        return None
    bpy.context.scene.frame_set(frame)
    return 0.6


bpy.app.timers.register(setup, first_interval=3.0)
