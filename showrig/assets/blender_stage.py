"""Showrig's Blender stage: footage playing on floating, glowing screens over a reflective floor.

blender -b -P blender_stage.py -- <job.json> <frames_dir>
  job: {shot: intro|outro|establishing, focus, seconds, fps, width, height, quality,
        background, panels: [{video, color, offset}], blend?, movie?}
  blend: also save the scene there. movie: render straight to this H.264 MP4 instead of PNG frames.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
JOB = json.loads(Path(argv[0]).read_text())
OUT = Path(argv[1])
FPS = JOB["fps"]
DRAFT = JOB["quality"] == "draft"
PANELS = JOB["panels"]
PANEL_H = 1.8
PANEL_W = PANEL_H * JOB["width"] / JOB["height"]
RADIUS = 0.09


def hex_rgb(h: str) -> tuple[float, float, float]:
    """sRGB hex to linear RGB."""
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return tuple(lin(int(h[i:i + 2], 16) / 255) for i in (1, 3, 5))


def reset() -> bpy.types.Scene:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE"
    except TypeError:  # Blender 4.2 to 4.5 call it EEVEE Next
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    ee = scene.eevee
    for attr, value in (("use_raytracing", True), ("taa_render_samples", 16 if DRAFT else 48),
                        ("use_shadows", True)):
        if hasattr(ee, attr):
            setattr(ee, attr, value)
    if hasattr(ee, "ray_tracing_options"):
        ee.ray_tracing_options.resolution_scale = "2" if DRAFT else "1"
    scene.render.resolution_x, scene.render.resolution_y = JOB["width"], JOB["height"]
    scene.render.resolution_percentage = 50 if DRAFT else 100
    scene.render.fps = FPS
    # Standard keeps the footage colours exact; bloom supplies the glow.
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*hex_rgb(JOB["background"]), 1)
    bg.inputs["Strength"].default_value = 1.0
    return scene


def rounded_rect(name: str, w: float, h: float, r: float, segments: int = 10) -> bpy.types.Object:
    """A flat rounded rectangle in the XZ plane facing -Y, UV-mapped edge to edge."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    pts = []
    for cx, cz, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                       (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for i in range(segments + 1):
            a = math.radians(a0 + 90 * i / segments)
            pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    verts = [bm.verts.new((x, 0, z)) for x, z in pts]
    face = bm.faces.new(verts)
    uv = bm.loops.layers.uv.new()
    for loop in face.loops:
        loop[uv].uv = (loop.vert.co.x / w + 0.5, loop.vert.co.z / h + 0.5)
    face.normal_update()
    if face.normal.y > 0:
        face.normal_flip()
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def screen_material(p: dict) -> bpy.types.Material:
    mat = bpy.data.materials.new(f"Screen {Path(p['video']).stem}")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tex = nt.nodes.new("ShaderNodeTexImage")
    img = bpy.data.images.load(p["video"])
    img.source = "MOVIE"
    tex.image = img
    user = tex.image_user
    user.frame_duration = img.frame_duration
    user.frame_start = 1
    user.frame_offset = round(p.get("offset", 0) * FPS)
    user.use_auto_refresh = True
    user.use_cyclic = True
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], emit.inputs["Color"])
    nt.links.new(emit.outputs[0], out.inputs["Surface"])
    return mat


def emissive(name: str, color: str, strength: float) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (*hex_rgb(color), 1)
    emit.inputs["Strength"].default_value = strength
    nt.links.new(emit.outputs[0], out.inputs["Surface"])
    return mat


def panel(p: dict, loc, rot_z_deg: float, scale: float = 1.0):
    """A screen with a glowing rim and coloured light spill; returns the parent empty."""
    name = Path(p["video"]).stem
    root = bpy.data.objects.new(f"Panel {name}", None)
    bpy.context.collection.objects.link(root)
    root.location = loc
    root.rotation_euler = (0, 0, math.radians(rot_z_deg))
    root.scale = (scale, scale, scale)
    scr = rounded_rect(f"Screen {name}", PANEL_W, PANEL_H, RADIUS)
    scr.data.materials.append(screen_material(p))
    scr.parent = root
    rim = rounded_rect(f"Rim {name}", PANEL_W + 0.05, PANEL_H + 0.05, RADIUS + 0.025)
    rim.data.materials.append(emissive(f"Rim {name}", p["color"], 3.5))
    rim.parent = root
    rim.location = (0, 0.012, 0)
    back = rounded_rect(f"Back {name}", PANEL_W + 0.05, PANEL_H + 0.05, RADIUS + 0.025)
    back.data.materials.append(emissive("Back", "#05070c", 0.0))
    back.parent = root
    back.location = (0, 0.02, 0)
    light = bpy.data.lights.new(f"Spill {name}", "AREA")
    light.color = hex_rgb(p["color"])
    light.energy = 160 * scale
    light.size = 2.4
    lo = bpy.data.objects.new(f"Spill {name}", light)
    bpy.context.collection.objects.link(lo)
    lo.parent = root
    lo.location = (0, 0.3, -0.2)
    lo.rotation_euler = (math.radians(120), 0, 0)
    return root


def floor() -> None:
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, 0))
    obj = bpy.context.object
    mat = bpy.data.materials.new("Floor")
    mat.use_nodes = True
    p = mat.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.006, 0.008, 0.012, 1)
    p.inputs["Roughness"].default_value = 0.12
    p.inputs["Metallic"].default_value = 0.4
    obj.data.materials.append(mat)


def camera(lens: float = 35, fstop: float = 2.2) -> tuple[bpy.types.Object, bpy.types.Object]:
    cam = bpy.data.cameras.new("Camera")
    cam.lens = lens
    cam.dof.use_dof = True
    cam.dof.aperture_fstop = fstop
    obj = bpy.data.objects.new("Camera", cam)
    bpy.context.collection.objects.link(obj)
    bpy.context.scene.camera = obj
    target = bpy.data.objects.new("Target", None)
    bpy.context.collection.objects.link(target)
    track = obj.constraints.new("TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    cam.dof.focus_object = target
    return obj, target


def move(cam, tgt, frame: int, cam_at, tgt_at) -> None:
    cam.location = Vector(cam_at)
    cam.keyframe_insert("location", frame=frame)
    tgt.location = Vector(tgt_at)
    tgt.keyframe_insert("location", frame=frame)


def smooth_all() -> None:
    for action in bpy.data.actions:
        fcurves = getattr(action, "fcurves", None)
        if fcurves is None:  # layered actions (Blender 4.4+)
            fcurves = [fc for layer in action.layers for strip in layer.strips
                       for bag in strip.channelbags for fc in bag.fcurves]
        for fc in fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"
                kp.easing = "AUTO"
                kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"


def compositor(scene: bpy.types.Scene) -> None:
    """Bloom on the rims and a soft vignette (written for both the 4.x and 5.x compositors)."""
    scene.use_nodes = True
    tree = getattr(scene, "compositing_node_group", None)
    if tree is None and not hasattr(scene, "node_tree"):
        tree = bpy.data.node_groups.new("Compositor", "CompositorNodeTree")
        scene.compositing_node_group = tree
    tree = tree or scene.node_tree
    nodes, links = tree.nodes, tree.links
    nodes.clear()
    rl = nodes.new("CompositorNodeRLayers")
    glare = nodes.new("CompositorNodeGlare")
    for attr, value in (("glare_type", "BLOOM"), ("quality", "HIGH"), ("size", 7), ("mix", 0.0),
                        ("threshold", 0.9)):
        if hasattr(glare, attr):
            try:
                setattr(glare, attr, value)
            except (TypeError, ValueError):
                pass
    for name, value in (("Type", "Bloom"), ("Threshold", 0.9), ("Strength", 0.6), ("Size", 0.7), ("Quality", "High")):
        if name in glare.inputs:
            try:
                glare.inputs[name].default_value = value
            except (TypeError, ValueError):
                pass
    links.new(rl.outputs["Image"], glare.inputs["Image"])
    ell = nodes.new("CompositorNodeEllipseMask")
    for name, value in (("width", 1.25), ("height", 1.15)):
        if hasattr(ell, name):
            setattr(ell, name, value)
    if "Size" in ell.inputs:
        ell.inputs["Size"].default_value = (1.25, 1.15)
    blur = nodes.new("CompositorNodeBlur")
    try:
        if hasattr(blur, "size_x"):
            blur.size_x = 300
        if hasattr(blur, "size_y"):
            blur.size_y = 300
    except Exception:
        pass
    try:
        if "Size" in blur.inputs:
            try:
                blur.inputs["Size"].default_value = 300
            except Exception:
                try:
                    blur.inputs["Size"].default_value = (300, 300)
                except Exception:
                    pass
    except Exception:
        pass
    links.new(ell.outputs[0], blur.inputs[0] if blur.inputs[0].name != "Image" else blur.inputs["Image"])
    if hasattr(scene, "compositing_node_group"):  # 5.x: generic Mix node and a group output
        mul = nodes.new("ShaderNodeMix")
        mul.data_type = "RGBA"
        mul.blend_type = "MULTIPLY"
        mul.inputs[0].default_value = 0.55
        color_in = [i for i in mul.inputs if i.type == "RGBA"]
        links.new(glare.outputs[0], color_in[0])
        links.new(blur.outputs[0], color_in[1])
        out = nodes.new("NodeGroupOutput")
        if not tree.interface.items_tree:
            tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        links.new([o for o in mul.outputs if o.type == "RGBA"][0], out.inputs[0])
    else:
        mul = nodes.new("CompositorNodeMixRGB")
        mul.blend_type = "MULTIPLY"
        mul.inputs[0].default_value = 0.55
        links.new(glare.outputs[0], mul.inputs[1])
        links.new(blur.outputs[0], mul.inputs[2])
        links.new(mul.outputs[0], nodes.new("CompositorNodeComposite").inputs[0])


def build_intro(end: int) -> None:
    """Every screen on an arc; the camera sweeps from a close pass on the first to the whole arc."""
    n, radius = len(PANELS), 11.5
    span = min(19 * (n - 1), 140)
    locs = []
    for i, p in enumerate(PANELS):
        a = math.radians(-span / 2 + (span * i / (n - 1) if n > 1 else 0))
        loc = (radius * math.sin(a), radius * math.cos(a) - radius + 4.0, 1.25)
        locs.append(loc)
        panel(p, loc, -math.degrees(a))
    first = Vector(locs[0])
    width = abs(locs[-1][0] - locs[0][0]) + PANEL_W
    cam, tgt = camera(lens=32, fstop=2.0)
    move(cam, tgt, 1, first + Vector((4.0, -3.2, -0.2)), first + Vector((0.35, 0.35, 0)))
    move(cam, tgt, int(end * 0.45), (first.x * 0.25, -8.5, 1.8), (first.x * 0.27, 1.2, 1.25))
    move(cam, tgt, end, (0, -max(9.0, width * 0.95 + 2), 3.0), (0, 1.0, 1.2))


def build_outro(end: int) -> None:
    """A wall of screens the camera pulls away from."""
    n = len(PANELS)
    cols = min(4, n)
    rows = math.ceil(n / cols)
    wall = [PANELS[i % n] for i in range(rows * cols)]
    for i, p in enumerate(wall):
        r, c = divmod(i, cols)
        mid = (cols - 1) / 2
        x = (c - mid) * (PANEL_W + 0.25)
        z = 1.95 + ((rows - 1) / 2 - r) * (PANEL_H + 0.2)
        panel(p, (x, 2.0 + abs(c - mid) * 0.35, z), (c - mid) * -6)
    cam, tgt = camera(lens=40, fstop=4.0)
    move(cam, tgt, 1, (0.6, -3.5, 2.1), (0.3, 2.0, 2.0))
    move(cam, tgt, end, (0, -max(8.0, 3.5 * cols), 2.6), (0, 2.0, 1.95))


def build_establishing(end: int) -> None:
    """One screen, angled, the camera drifting in with shallow focus; two neighbours for depth."""
    focus = JOB.get("focus", 0)
    panel(PANELS[focus], (0, 0, 1.25), -22)
    others = [p for i, p in enumerate(PANELS) if i != focus]
    for p, loc, rot in zip(others, ((-4.6, 3.2, 1.25), (4.4, 4.5, 1.25)), (12, -38)):
        panel(p, loc, rot, scale=0.9)
    cam, tgt = camera(lens=40, fstop=1.6)
    move(cam, tgt, 1, (-3.2, -5.6, 1.05), (-0.3, 0.0, 1.2))
    move(cam, tgt, end, (-1.2, -4.6, 1.45), (0.25, 0.0, 1.3))


def main() -> None:
    scene = reset()
    scene.frame_start, scene.frame_end = 1, round(JOB["seconds"] * FPS)
    floor()
    {"intro": build_intro, "outro": build_outro, "establishing": build_establishing}[JOB["shot"]](scene.frame_end)
    smooth_all()
    compositor(scene)
    OUT.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(OUT / "f_")
    if JOB.get("movie"):
        settings = scene.render.image_settings
        settings.file_format = "FFMPEG"
        scene.render.ffmpeg.format, scene.render.ffmpeg.codec = "MPEG4", "H264"
        scene.render.ffmpeg.constant_rate_factor, scene.render.ffmpeg.ffmpeg_preset = "PERC_LOSSLESS", "GOOD"
        scene.render.filepath = JOB["movie"]
        scene.render.use_file_extension = False
    if JOB.get("blend"):  # keep the scene so it can be reopened and re-rendered in Blender
        bpy.ops.wm.save_as_mainfile(filepath=JOB["blend"], copy=True)
    bpy.ops.render.render(animation=True)


main()
