"""What this machine can do for Showrig.

One catalog, used by `showrig doctor`: each capability belongs to a profile, is found quickly (a path and
a version), and can be proved by a small, time-limited functional probe in scratch space. Finding a
program only shows it is available; a capability is `ready` only after its probe succeeds.

  states    ready · degraded (works, slower or reduced) · missing · incompatible · failed · not-tested
  profiles  core · capture · voice · showcase3d (the studio profile is all four) · drafting (optional)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import __version__, inventory, tools

SCHEMA = 1
PROFILES = {
    "core": ["ffmpeg", "filmcraft", "effectcraft", "fonts", "disk"],
    "capture": ["node", "chromium"],
    "voice": ["kokoro"],
    "showcase3d": ["blender"],
    "drafting": ["ollama"],
}
PROFILES["studio"] = PROFILES["core"] + PROFILES["capture"] + PROFILES["voice"] + PROFILES["showcase3d"]
FONTS = ["Inter-Bold", "Inter-Regular", "DejaVuSans", "DejaVuSans-Bold"]  # named by the title templates


@dataclass
class Result:
    id: str
    state: str
    path: str | None = None
    version: str | None = None
    evidence: dict = field(default_factory=dict)
    remedy: str | None = None
    seconds: float | None = None


@dataclass
class Capability:
    id: str
    profile: str
    unlocks: str
    find: Callable[[], str | None]
    remedy: str
    version: Callable[[str], str | None] = lambda path: None
    probe: Callable[[str, Path], tuple[str, dict]] | None = None


def _run(cmd: list, timeout: float, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout, **kw)


def _why(r: subprocess.CompletedProcess) -> str:
    """The last lines a failed tool printed, or its exit code when it printed nothing."""
    lines = [x.strip() for x in (r.stderr + "\n" + r.stdout).splitlines() if x.strip()]
    return " | ".join(lines[-2:])[-300:] if lines else f"exited with code {r.returncode} and printed nothing"


def _first_line(cmd: list) -> str | None:
    try:
        r = _run(cmd, 20)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = (r.stdout or r.stderr).strip().splitlines()
    return next((x for x in lines if re.search(r"\d+\.\d+", x)), lines[0] if lines else None)


def _media(path: Path) -> dict:
    out = _run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                "stream=codec_name,width,height,pix_fmt,nb_read_frames,sample_rate:format=duration",
                "-of", "json", path], 60)
    data = json.loads(out.stdout or "{}")
    return {"streams": data.get("streams", []), "duration": float(data.get("format", {}).get("duration") or 0)}


# ---- probes: each returns (state, evidence) ----------------------------------------------------------

def probe_ffmpeg(path: str, tmp: Path) -> tuple[str, dict]:
    """Encode a second of video with the encoder Showrig would pick, then decode every frame."""
    codec = tools.h264_encoder()
    out = tmp / "probe.mp4"
    r = _run([path, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=1", *codec,
              "-pix_fmt", "yuv420p", out], 60)
    if r.returncode != 0:
        return "failed", {"encoder": codec[1], "error": r.stderr[-300:]}
    frames = _media(out)["streams"][0].get("nb_read_frames")
    built = _run([path, "-hide_banner", "-encoders"], 20).stdout
    ev = {"encoder": codec[1], "decoded_frames": int(frames or 0)}
    if codec[1] != "h264_nvenc":
        ev["gpu_encoder"] = ("h264_nvenc is built into ffmpeg but could not open a GPU" if "h264_nvenc" in built
                             else "ffmpeg has no h264_nvenc")
    return ("ready" if ev["decoded_frames"] == 30 else "failed"), ev


def probe_filmcraft(path: str, tmp: Path) -> tuple[str, dict]:
    """Build a one-clip project, export a second of it, and read the project back."""
    clip = tmp / "clip.mp4"
    _run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=1", "-pix_fmt", "yuv420p",
          clip], 60)
    project, script, out = tmp / "probe.fcproj", tmp / "probe.jsonl", tmp / "probe-export.mp4"
    cmds = [{"id": "file.newProject", "params": {"name": "probe"}},
            {"id": "file.newSequence", "params": {"name": "probe", "width": 320, "height": 180, "fps": 30,
                                                   "sampleRate": 48000, "video": 1, "audio": 1}},
            {"id": "file.import", "params": {"paths": [str(clip)]}}]
    script.write_text("".join(json.dumps(c) + "\n" for c in cmds))
    r = _run([path, "--compact", "--save-as", project, "run", script], 120)
    rows = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
    if r.returncode != 0 or len(rows) != 3 or not all(x.get("ok") for x in rows):
        return "failed", {"step": "create", "error": _why(r)}
    item = rows[2]["result"]["items"][0]
    place = {"id": "timeline.place", "params": {"item": item, "track": "V1", "seconds": 0, "insert": False}}
    script.write_text(json.dumps(place) + "\n")
    r = _run([path, "--compact", "--project", project, "--save", "run", script], 120)
    if r.returncode != 0:
        return "failed", {"step": "place", "error": _why(r)}
    r = _run([path, "--project", project, "export", out, "--format", "h264"], 300)
    if r.returncode != 0 or not out.exists():
        return "failed", {"step": "export", "error": _why(r)}
    info = _media(out)
    reopened = _run([path, "--project", project, "inspect", "sequence"], 60)
    ev = {"export_seconds": round(info["duration"], 2), "reopened": reopened.returncode == 0}
    ok = 0.9 <= info["duration"] <= 1.2 and ev["reopened"]
    return ("ready" if ok else "failed"), ev


def probe_effectcraft(path: str, tmp: Path) -> tuple[str, dict]:
    """Script a one-second title from Showrig's own template and check it renders with alpha."""
    spec = {"width": 320, "height": 180, "fps": 30, "secs": 1.0, "name": "Probe", "tagline": "", "subtitle": "",
            "color": "#46d9b0", "layout": "center", "style": "rise", "mono": "DejaVuSansMono-Bold", "inset": 0}
    jsx, project, out = tmp / "probe.jsx", tmp / "probe.ecproj", tmp / "probe.mov"
    jsx.write_text(f"var TITLE = {json.dumps(spec)};\n{(tools.ASSETS / 'title.jsx').read_text()}")
    r = _run([path, "--empty", "--save-as", project, "script", jsx], 120)
    if r.returncode != 0:
        return "failed", {"step": "script", "error": _why(r)}
    r = _run([path, "--project", project, "--gpu", "render", "--out", out, "--format", "prores", "--prores", "4444",
              "--channels", "rgba", "--quality", "best", "--audio", "off"], 300)
    if r.returncode != 0 or not out.exists():
        return "failed", {"step": "render", "error": _why(r)}
    v = _media(out)["streams"][0]
    ev = {"size": f"{v.get('width')}x{v.get('height')}", "pix_fmt": v.get("pix_fmt"),
          "frames": int(v.get("nb_read_frames") or 0)}
    ok = ev["size"] == "320x180" and "a" in (ev["pix_fmt"] or "").replace("yuv", "") and ev["frames"] >= 29
    return ("ready" if ok else "failed"), ev


def probe_fonts(path: str, tmp: Path) -> tuple[str, dict]:
    have = set(_run([path, ":", "postscriptname"], 30).stdout.replace(":postscriptname=", "").split())
    missing = [f for f in FONTS if f not in have]
    return ("ready" if not missing else "missing"), {"needed": FONTS, "missing": missing}


def probe_blender(path: str, tmp: Path) -> tuple[str, dict]:
    """Render a 64x64 EEVEE frame of the default scene and report which OpenGL driver drew it."""
    script, png = tmp / "probe.py", tmp / "probe.png"
    script.write_text(
        "import bpy\ns = bpy.context.scene\n"
        "try:\n    s.render.engine = 'BLENDER_EEVEE'\nexcept TypeError:\n    s.render.engine = 'BLENDER_EEVEE_NEXT'\n"
        "s.render.resolution_x = s.render.resolution_y = 64\ns.render.resolution_percentage = 100\n"
        f"s.render.filepath = {str(png)!r}\nbpy.ops.render.render(write_still=True)\n"
        "print('PROBE_ENGINE', s.render.engine)\n")
    r = _run([path, "-b", "--factory-startup", "--python", script], 300, env={**os.environ, "LIBGL_DEBUG": "verbose"})
    log = r.stdout + r.stderr
    engine = re.search(r"PROBE_ENGINE (\S+)", log)
    drivers = sorted(set(re.findall(r"driver (\w+)\s*$", log, re.M)) - {"i915"})
    software = re.search(r"llvmpipe|softpipe|swrast", log)
    ev = {"engine": engine.group(1) if engine else None, "gl_driver": drivers[-1] if drivers else None}
    if r.returncode != 0 or not png.exists() or png.stat().st_size < 200:
        return "failed", {**ev, "error": _why(r)}
    if software or not drivers:
        ev["note"] = "rendered by a software OpenGL driver" if software else "the OpenGL driver did not identify itself"
        return "degraded", ev
    return "ready", ev


def probe_chromium(path: str, tmp: Path) -> tuple[str, dict]:
    """Launch Playwright's Chromium with Showrig's capture flags, draw WebGL, read back the real renderer."""
    pw = tools.playwright()
    if not pw:
        return "missing", {"error": "no playwright package found"}
    flags = re.search(r"const GPU_ARGS = (\[.*?\]);", (tools.ASSETS / "capture.mjs").read_text(), re.S)
    args = json.loads(flags.group(1).replace("'", '"')) if flags else []
    js = tmp / "probe.mjs"
    js.write_text(f"""
import {{createRequire}} from 'node:module';
const {{chromium}} = createRequire(import.meta.url)({json.dumps(pw)});
const b = await chromium.launch({{headless: true, args: {json.dumps(args)}}});
const p = await b.newPage({{viewport: {{width: 320, height: 180}}}});
await p.setContent('<canvas id=c width=320 height=180></canvas>');
const gl = await p.evaluate(() => {{
  const g = document.getElementById('c').getContext('webgl');
  if (!g) return null;
  g.clearColor(0.27, 0.85, 0.69, 1); g.clear(g.COLOR_BUFFER_BIT);
  const e = g.getExtension('WEBGL_debug_renderer_info');
  return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER);
}});
const shot = await p.screenshot();
console.log(JSON.stringify({{renderer: gl, browser: b.version(), screenshot_bytes: shot.length}}));
await b.close();
""")
    r = _run([path, js], 120)
    try:
        ev = json.loads(r.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return "failed", {"error": _why(r)}
    if not ev.get("renderer") or ev.get("screenshot_bytes", 0) < 100:
        return "failed", ev
    if re.search(r"SwiftShader|llvmpipe|Software", ev["renderer"], re.I):
        ev["note"] = "captures work, drawn in software"
        return "degraded", ev
    return "ready", ev


def probe_kokoro(path: str, tmp: Path) -> tuple[str, dict]:
    """Speak a short phrase with the default voice, network blocked, and check the audio decodes."""
    wav = tmp / "probe.wav"
    job = tmp / "probe-tts.json"
    job.write_text(json.dumps({"voice": "af_heart", "speed": 1.0, "items": [{"text": "Showrig probe.", "out": str(wav)}]}))
    t0 = time.time()
    r = _run([path, tools.ASSETS / "tts_kokoro.py", job], 300)
    if r.returncode != 0 or not wav.exists():
        if re.search(r"LocalEntryNotFoundError|requires preinstalled models", r.stderr):
            return "missing", {"voice": "af_heart", "error": "the Kokoro model or the af_heart voice is not installed "
                               "on this machine, and builds never download it"}
        return "failed", {"voice": "af_heart", "error": _why(r)}
    info = _media(wav)
    ev = {"voice": "af_heart", "seconds_of_speech": round(info["duration"], 2),
          "synthesis_seconds": round(time.time() - t0, 1), "network": "blocked by tts_kokoro.py"}
    return ("ready" if info["duration"] > 0.3 else "failed"), ev


def probe_disk(path: str, tmp: Path) -> tuple[str, dict]:
    free = shutil.disk_usage(Path.home()).free / 1e9
    ev = {"home_free_gb": round(free, 1), "scratch_writable": tmp.exists()}
    if free < 2:
        return "missing", ev
    return ("degraded" if free < 10 else "ready"), {**ev, **({"note": "under 10 GB free"} if free < 10 else {})}


CATALOG = [
    Capability("ffmpeg", "core", "probing, normalizing and encoding media", lambda: shutil.which("ffmpeg"),
               "install ffmpeg (Ubuntu: sudo apt install ffmpeg)", lambda p: _first_line([p, "-version"]), probe_ffmpeg),
    Capability("filmcraft", "core", "the editable timeline and the final render", tools.filmcraft,
               "install the FilmCraft CLI, or set FILMCRAFT_CLI", lambda p: _first_line([p, "--version"]), probe_filmcraft),
    Capability("effectcraft", "core", "title cards and credits", tools.effectcraft,
               "install the EffectCraft CLI, or set EFFECTCRAFT_CLI", lambda p: _first_line([p, "--version"]),
               probe_effectcraft),
    Capability("fonts", "core", "the typefaces the title templates name", lambda: shutil.which("fc-list"),
               "install Inter and DejaVu (Ubuntu: sudo apt install fonts-inter fonts-dejavu)", probe=probe_fonts),
    Capability("disk", "core", "room for renders and caches", lambda: str(Path.home()),
               "free some disk space: a 1080p film needs a few GB while it builds", probe=probe_disk),
    Capability("node", "capture", "scripted browser captures", tools.node, "install Node.js 20 or newer, or set NODE",
               lambda p: _first_line([p, "--version"])),
    Capability("chromium", "capture", "scripted browser captures, with the renderer they really use", tools.node,
               "install Playwright and its Chromium (npm i -g playwright; npx playwright install chromium), "
               "or set SHOWRIG_PLAYWRIGHT", lambda p: tools.playwright(), probe_chromium),
    Capability("kokoro", "voice", "generated narration, offline", tools.tts_python,
               "make a Python venv with kokoro and its voices, and set SHOWRIG_TTS_PYTHON",
               lambda p: _first_line([p, "-c", "import kokoro; print('kokoro', kokoro.__version__)"]), probe_kokoro),
    Capability("blender", "showcase3d", "the 3D showcase: glowing floating screens", tools.blender,
               "install Blender (4.0 is the tested version), or set BLENDER", lambda p: _first_line([p, "--version"]),
               probe_blender),
    Capability("ollama", "drafting", "the optional AI drafting pass", lambda: shutil.which("ollama"),
               "install Ollama and pull a model (optional; builds never need it)",
               lambda p: _first_line([p, "--version"])),
]


def check(ids: list[str], deep: bool) -> list[Result]:
    results = []
    for cap in [c for c in CATALOG if c.id in ids]:
        t0 = time.time()
        path = cap.find()
        if not path:
            results.append(Result(cap.id, "missing", remedy=cap.remedy))
            continue
        res = Result(cap.id, "not-tested", path, cap.version(path))
        if deep and cap.probe:
            with tempfile.TemporaryDirectory(prefix=f"showrig-probe-{cap.id}-") as tmp:
                try:
                    res.state, res.evidence = cap.probe(path, Path(tmp))
                except subprocess.TimeoutExpired as e:
                    res.state, res.evidence = "failed", {"error": f"timed out after {e.timeout:.0f}s"}
                except (OSError, ValueError, KeyError, IndexError) as e:
                    res.state, res.evidence = "failed", {"error": f"{type(e).__name__}: {e}"}
        elif deep:
            res.evidence = {"note": "no functional probe for this capability yet"}
        if res.state in ("missing", "failed", "incompatible", "degraded"):
            res.remedy = cap.remedy
        res.seconds = round(time.time() - t0, 2)
        results.append(res)
    return results


def report(profile: str | None, deep: bool) -> dict:
    requested = PROFILES[profile] if profile else PROFILES["core"]
    ids = requested if profile else [c.id for c in CATALOG]
    results = check(ids, deep)
    bad = [r.id for r in results if r.id in requested and r.state in ("missing", "failed", "incompatible")]
    host = inventory.collect()
    return {"schema": SCHEMA, "kind": "showrig-doctor", "showrig": __version__,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "profile": profile or "core", "deep": deep,
            "host": {k: host[k] for k in ("os", "cpu", "memory_gb", "graphics")},
            "capabilities": [r.__dict__ for r in results],
            "summary": {"requested": requested, "unavailable": bad,
                        "degraded": [r.id for r in results if r.state == "degraded"]}}


def print_report(rep: dict) -> None:
    mark = {"ready": "ready", "degraded": "degraded", "not-tested": "ok", "missing": "MISSING",
            "failed": "FAILED", "incompatible": "INCOMPAT"}
    profile_of = {c.id: c.profile for c in CATALOG}
    unlocks = {c.id: c.unlocks for c in CATALOG}
    for r in rep["capabilities"]:
        required = r["id"] in rep["summary"]["requested"]
        state = mark[r["state"]] if r["state"] != "missing" or required else "--"
        detail = r["version"] or r["path"] or ""
        print(f"  {state:9} {r['id']:12} {profile_of[r['id']]:10} {detail[:46]:46}  {unlocks[r['id']]}")
        for k, v in r["evidence"].items():
            print(f"  {'':9} {'':12} {'':10} {k}: {v if not isinstance(v, str) else v[:110]}")
        if r["remedy"] and (required or r["state"] != "missing"):
            print(f"  {'':9} {'':12} {'':10} fix: {r['remedy']}")
    s = rep["summary"]
    if not rep["deep"]:
        print("\n  Found is not proven: `showrig doctor --deep` runs a small real job for each capability.")
    verdict = "unavailable: " + ", ".join(s["unavailable"]) if s["unavailable"] else "ready"
    print(f"\n  profile {rep['profile']}: {verdict}" + (f"  (degraded: {', '.join(s['degraded'])})" if s["degraded"] else ""))
