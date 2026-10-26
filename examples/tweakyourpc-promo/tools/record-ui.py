#!/usr/bin/env python3
"""Record the "made on this PC" clips: Blender, EffectCraft and FilmCraft at work on this film.

  tools/record-ui.py [FILM_DIR]        default: <showrig>/films/tweakyourpc-promo

Run it after a build, so the apps open this film's own files: the intro's Blender scene, the
Game Night title's EffectCraft project and the FilmCraft edit. Each app runs on a private virtual
display (Xvfb). The script steps time one frame at a time, grabs the screen after each step, and
encodes the grabs at 30 fps into ../media/. It works offline and changes nothing in the film folder:
EffectCraft and FilmCraft open copies, and Blender never saves.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
MEDIA = TOOLS.parent / "media"
FPS = 30
APPS = Path.home() / "Applications"


def appimage(name: str) -> str:
    found = sorted(APPS.glob(f"{name}-*.AppImage"), key=lambda p: p.stat().st_mtime)
    if not found:
        raise SystemExit(f"{name} AppImage not found in {APPS}")
    return str(found[-1])


def port(name: str) -> int:
    for verb in ("get", "alloc"):
        r = subprocess.run(["portbroker", verb, "--name", name], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip().isdigit():
            return int(r.stdout.strip())
    raise SystemExit(f"portbroker could not give a port for {name}")


def call(port_: int, method: str, params: dict | None = None) -> dict:
    """One call on an ArtCraft app's control channel (JSON lines over localhost)."""
    with socket.create_connection(("127.0.0.1", port_), timeout=90) as s:
        s.sendall((json.dumps({"id": 1, "method": method, "params": params or {}}) + "\n").encode())
        reply = json.loads(s.makefile().readline())
    if not reply.get("ok"):
        raise RuntimeError(f"{method}: {reply.get('error')}")
    return reply.get("result")


def command(cli: str, port_: int, cid: str, params: dict) -> None:
    subprocess.run([cli, "--bridge", f"127.0.0.1:{port_}", "exec", cid, json.dumps(params)],
                   check=True, capture_output=True)


def wait_port(port_: int, seconds: float = 60) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port_), timeout=1).close()
            return
        except OSError:
            time.sleep(0.5)
    raise SystemExit(f"the app did not open its control port {port_}")


class Display:
    """A private Xvfb screen, a little larger than the window so nothing is clipped."""

    def __init__(self, number: int, size: str = "2000x1120"):
        self.name = f":{number}"
        self.proc = subprocess.Popen(["Xvfb", self.name, "-screen", "0", f"{size}x24", "-nolisten", "tcp"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        self.env = {**os.environ, "DISPLAY": self.name, "WAYLAND_DISPLAY": "", "XDG_SESSION_TYPE": "x11"}

    def grab(self, path: Path, x: int = 0, y: int = 0) -> None:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "x11grab", "-draw_mouse", "0", "-video_size", "1920x1080",
                        "-i", f"{self.name}+{x},{y}", "-frames:v", "1", str(path)], check=True)

    def close(self) -> None:
        self.proc.terminate()


def encode(frames: Path, out: Path) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", str(frames / "f%05d.png"),
                    "-vf", "tpad=stop_mode=clone:stop_duration=1,format=yuv420p", "-c:v", "libx264", "-preset", "slow",
                    "-crf", "16", "-movflags", "+faststart", str(out)], check=True)
    print(f"  wrote {out.relative_to(TOOLS.parent)}")


def window_origin(display: Display) -> tuple[int, int]:
    """Where the app's window landed: the first row and column that are not the empty screen."""
    probe = Path(tempfile.mkdtemp()) / "probe.raw"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "x11grab", "-draw_mouse", "0", "-video_size", "2000x1120",
                    "-i", display.name, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", str(probe)], check=True)
    px, w = probe.read_bytes(), 2000
    rows = [y for y in range(1120) if any(px[y * w + x] for x in range(0, w, 8))]
    cols = [x for x in range(w) if any(px[y * w + x] for y in range(0, 1120, 8))]
    shutil.rmtree(probe.parent)
    return (min(cols[0], 80), min(rows[0], 40)) if rows and cols else (0, 0)


def blender(film: Path, work: Path) -> None:
    scene = film / "work" / "stage" / "intro.blend"
    frames = work / "blender"
    frames.mkdir()
    display = Display(91, "1920x1080")
    try:
        subprocess.run(["blender", "--window-geometry", "0", "0", "1920", "1080", str(scene), "--python",
                        str(TOOLS / "blender_ui.py"), "--", str(frames), "30", "300"], env=display.env, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        display.close()
    encode(frames, MEDIA / "blender-ui.mp4")


def effectcraft(film: Path, work: Path) -> None:
    project = work / "title.ecproj"
    shutil.copy(film / "work" / "titles" / "game-night.ecproj", project)
    frames = work / "effectcraft"
    frames.mkdir()
    p = port("promo-effectcraft-ui")
    display = Display(92)
    app = subprocess.Popen([appimage("effectcraft"), "--control", str(p), str(project)], env=display.env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_port(p)
        time.sleep(6)
        call(p, "ui.resize", {"width": 1920, "height": 1080})
        cli = shutil.which("effectcraft-cli") or "effectcraft-cli"
        command(cli, p, "window.workspace", {"name": "Default"})
        command(cli, p, "comp.open", {"comp": "Title Game Night"})
        time.sleep(3)
        x, y = window_origin(display)
        for i in range(150):  # the typewriter title, from its first letter to settled
            command(cli, p, "time.set", {"time": round(i / FPS, 4)})
            time.sleep(0.35)
            display.grab(frames / f"f{i:05d}.png", x, y)
    finally:
        app.terminate()
        display.close()
    encode(frames, MEDIA / "effectcraft-ui.mp4")


def filmcraft(film: Path, work: Path) -> None:
    edit = next((film / "out").glob("*.fcproj"))
    project = work / edit.name
    shutil.copy(edit, project)
    frames = work / "filmcraft"
    frames.mkdir()
    p = port("promo-filmcraft-ui")
    display = Display(93)
    app = subprocess.Popen([appimage("filmcraft"), "--control", str(p), "--data-dir", str(work / "fcdata"), "--no-recover",
                            str(project)], env=display.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_port(p)
        time.sleep(8)
        call(p, "ui.resize", {"width": 1920, "height": 1080})
        time.sleep(2)
        x, y = window_origin(display)
        cli = shutil.which("filmcraft-cli") or "filmcraft-cli"
        start = 10.0  # into the intro's 3D shot, with the titles and the first project coming up
        for i in range(250):
            command(cli, p, "playhead.set", {"seconds": round(start + i / FPS, 4)})
            time.sleep(0.45)
            display.grab(frames / f"f{i:05d}.png", x, y)
    finally:
        app.terminate()
        display.close()
    encode(frames, MEDIA / "filmcraft-ui.mp4")


def main() -> None:
    film = Path(sys.argv[1] if len(sys.argv) > 1 else TOOLS.parents[2] / "films" / "tweakyourpc-promo")
    for need in (film / "work/stage/intro.blend", film / "work/titles/game-night.ecproj"):
        if not need.exists():
            raise SystemExit(f"{need} not found: build the film first (./build.sh --draft is enough)")
    for tool in ("Xvfb", "ffmpeg", "blender", "portbroker"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} is needed to record the app clips")
    with tempfile.TemporaryDirectory(prefix="promo-ui-") as tmp:
        work = Path(tmp)
        for step in (blender, effectcraft, filmcraft):
            print(f"== {step.__name__}")
            step(film, work)


if __name__ == "__main__":
    main()
