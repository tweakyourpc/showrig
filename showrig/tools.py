"""Find the external programs Showrig drives, and report what this machine can do."""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
from functools import cache
from pathlib import Path

from . import runtime

runtime.activate()

ASSETS = Path(__file__).parent / "assets"
ARTCRAFT = Path(os.getenv("ARTCRAFT_HOME", Path.home() / "Work/ArtCraft"))


def _first(*candidates: str | Path | None) -> str | None:
    for c in candidates:
        if not c:
            continue
        found = shutil.which(str(c)) if os.sep not in str(c) else (str(c) if Path(c).is_file() else None)
        if not found and os.name == "nt" and Path(str(c) + ".exe").is_file():
            found = str(c) + ".exe"
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
    for py in (os.getenv("SHOWRIG_TTS_PYTHON"), str(runtime.python_path()), shutil.which("python3"),
               str(Path.home() / "venvs/kokoro/bin/python")):
        if not py or not Path(py).exists():
            continue
        try:
            if subprocess.run([py, "-c", "import kokoro"], capture_output=True, timeout=30).returncode == 0:
                if py == str(runtime.python_path()):
                    os.environ.setdefault("HF_HOME", str(runtime.root() / "models"))
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
