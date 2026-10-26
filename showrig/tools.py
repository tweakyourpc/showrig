"""Find the external programs Showrig drives, and report what this machine can do."""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
from functools import cache
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"
ARTCRAFT = Path(os.getenv("ARTCRAFT_HOME", Path.home() / "Work/ArtCraft"))


def _first(*candidates: str | Path | None) -> str | None:
    for c in candidates:
        if not c:
            continue
        found = shutil.which(str(c)) if os.sep not in str(c) else (str(c) if Path(c).is_file() else None)
        if found:
            return found
    return None


@cache
def filmcraft() -> str | None:
    return _first(os.getenv("FILMCRAFT_CLI"), ARTCRAFT / "filmcraft/target/release/filmcraft-cli", "filmcraft-cli")


@cache
def effectcraft() -> str | None:
    return _first(os.getenv("EFFECTCRAFT_CLI"), ARTCRAFT / "effectcraft/target/release/effectcraft-cli",
                  "effectcraft-cli")


@cache
def blender() -> str | None:
    return _first(os.getenv("BLENDER"), "blender")


@cache
def node() -> str | None:
    return _first(os.getenv("NODE"), "node")


@cache
def playwright() -> str | None:
    """Directory of the playwright npm package (global npm, mise, or SHOWRIG_PLAYWRIGHT)."""
    env = os.getenv("SHOWRIG_PLAYWRIGHT")
    if env:
        return env
    roots = []
    if shutil.which("npm"):
        try:
            roots.append(subprocess.check_output(["npm", "root", "-g"], text=True, timeout=20).strip())
        except (subprocess.SubprocessError, OSError):
            pass
    for root in roots:
        if (Path(root) / "playwright/package.json").exists():
            return str(Path(root) / "playwright")
    hits = glob.glob(str(Path.home() / ".local/share/mise/installs/npm-playwright/*/node_modules/playwright"))
    return sorted(hits)[-1] if hits else None


@cache
def tts_python() -> str | None:
    """A Python interpreter that can import kokoro (SHOWRIG_TTS_PYTHON, or this one)."""
    for py in (os.getenv("SHOWRIG_TTS_PYTHON"), shutil.which("python3"), str(Path.home() / "venvs/kokoro/bin/python")):
        if not py or not Path(py).exists():
            continue
        try:
            if subprocess.run([py, "-c", "import kokoro"], capture_output=True, timeout=30).returncode == 0:
                return py
        except (OSError, subprocess.SubprocessError):
            pass
    return None


@cache
def h264_encoder() -> list[str]:
    """ffmpeg video codec arguments: NVENC when the GPU offers it, x264 otherwise."""
    try:
        probe = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.1",
                                "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True, timeout=30)
        if probe.returncode == 0:
            return ["-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-rc", "vbr", "-cq", "16", "-b:v", "0"]
    except (subprocess.SubprocessError, OSError):
        pass
    return ["-c:v", "libx264", "-preset", "slow", "-crf", "16"]


def gpu_name() -> str | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        return subprocess.check_output(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], text=True,
                                       timeout=10).strip().splitlines()[0]
    except (subprocess.SubprocessError, OSError, IndexError):
        return None


def doctor() -> int:
    """Print every tool and what it unlocks; return 1 when a required one is missing."""
    rows = [
        ("ffmpeg", shutil.which("ffmpeg"), True, "probing, normalizing and encoding media"),
        ("FilmCraft CLI", filmcraft(), True, "the editable timeline and the final render"),
        ("EffectCraft CLI", effectcraft(), False, "title cards and credits"),
        ("Blender", blender(), False, "the 3D showcase: glowing floating screens"),
        ("Kokoro TTS", tts_python(), False, "generated voiceover (set SHOWRIG_TTS_PYTHON to a venv with kokoro)"),
        ("node", node(), False, "scripted browser captures"),
        ("Playwright", playwright(), False, "scripted browser captures"),
        ("Ollama", shutil.which("ollama"), False, "the optional AI drafting pass"),
    ]
    missing = False
    for name, path, required, unlocks in rows:
        mark = "ok " if path else ("MISSING" if required else "-- ")
        missing |= required and not path
        print(f"  {mark:7} {name:16} {path or '':60.60}  {unlocks}")
    enc = "NVENC (GPU)" if "h264_nvenc" in h264_encoder() else "x264 (CPU)"
    print(f"\n  GPU: {gpu_name() or 'none found'}   video encoder: {enc}")
    return 1 if missing else 0
