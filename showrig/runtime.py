"""Find portable prerequisites and explicitly install optional local voices."""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path


VOICES = ("af_heart", "af_bella", "am_michael", "bf_emma", "bm_george")


def root() -> Path:
    """Return the per-user optional runtime directory for this operating system."""
    if os.environ.get("SHOWRIG_RUNTIME"):
        return Path(os.environ["SHOWRIG_RUNTIME"]).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Showrig/runtime"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Showrig/runtime"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "showrig/runtime"


def python_path() -> Path:
    """Return the managed voice environment interpreter, with native separators."""
    return root() / "voices" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def activate() -> None:
    """Prefer an optional portable bin folder; never install anything implicitly."""
    tag = f"{platform.system().lower()}-{platform.machine().lower()}"
    candidates = [root() / "bin", Path(__file__).parent.parent / "runtime" / tag / "bin",
                  Path(__file__).parent / "runtime" / tag / "bin"]
    parts = os.environ.get("PATH", "").split(os.pathsep)
    for path in reversed(candidates):
        if path.is_dir() and str(path) not in parts:
            parts.insert(0, str(path))
    os.environ["PATH"] = os.pathsep.join(parts)


def setup_catalog() -> dict:
    """Describe setup on the server OS, without running package managers."""
    systems = {
        "linux": {"name": "Linux (Ubuntu / Debian)", "core": "sudo apt install ffmpeg fonts-dejavu-core fonts-inter",
                  "voiceSystem": "sudo apt install espeak-ng", "blender": "sudo apt install blender",
                  "setTool": 'export FILMCRAFT_CLI="/path/to/filmcraft-cli"\nexport EFFECTCRAFT_CLI="/path/to/effectcraft-cli"'},
        "darwin": {"name": "macOS", "core": "brew install ffmpeg", "voiceSystem": "brew install espeak-ng",
                   "blender": "brew install --cask blender",
                   "setTool": 'export FILMCRAFT_CLI="/path/to/filmcraft-cli"\nexport EFFECTCRAFT_CLI="/path/to/effectcraft-cli"'},
        "win32": {"name": "Windows (PowerShell)", "core": "winget install --id Gyan.FFmpeg --exact",
                  "voiceSystem": "Install the eSpeak NG Windows MSI from its official releases, then reopen your terminal.",
                  "blender": "winget install --id BlenderFoundation.Blender --exact",
                  "setTool": '$env:FILMCRAFT_CLI = "C:\\Tools\\FilmCraft\\filmcraft-cli.exe"\n$env:EFFECTCRAFT_CLI = "C:\\Tools\\EffectCraft\\effectcraft-cli.exe"'},
    }
    return {"platform": sys.platform, "platformName": platform.system(), "architecture": platform.machine(),
            "runtimeRoot": str(root()), "managedVoicePython": str(python_path()),
            "managedVoicesInstalled": python_path().is_file(), "systems": systems,
            "voiceCommand": "showrig setup --install-voices", "voicePreviewCommand": "showrig setup --install-voices --dry-run",
            "voiceCheckCommand": "showrig doctor --profile voice --deep",
            "policy": "Setup downloads happen only when you explicitly run the installer. Creating and exporting films stays offline."}


def install_voices(dry_run: bool = False) -> None:
    """Explicit, isolated CPU voice installation followed by an offline synthesis check."""
    py = python_path()
    commands = [[sys.executable, "-m", "venv", str(py.parent.parent)],
                [str(py), "-m", "pip", "install", "--upgrade", "pip"]]
    if sys.platform != "darwin":
        commands.append([str(py), "-m", "pip", "install", "torch", "--index-url", "https://download.pytorch.org/whl/cpu"])
    commands.extend([[str(py), "-m", "pip", "install", "kokoro>=0.9.4,<1", "soundfile", "huggingface_hub"],
                     [str(py), "-m", "spacy", "download", "en_core_web_sm"]])
    model_script = ("from huggingface_hub import hf_hub_download\n"
                    f"files = {['config.json', 'kokoro-v1_0.pth', *['voices/' + v + '.pt' for v in VOICES]]!r}\n"
                    "for name in files: hf_hub_download(repo_id='hexgrad/Kokoro-82M', filename=name)\n")
    commands.append([str(py), "-c", model_script])
    commands.append([str(py), str(Path(__file__).parent / "assets/tts_kokoro.py"), "--check", VOICES[0]])
    if dry_run:
        print(json.dumps({"runtime": str(root()), "network": "only for explicit setup; final check is offline",
                          "systemPrerequisite": setup_catalog()["systems"].get(sys.platform, {})
                          .get("voiceSystem", "Install eSpeak NG for your platform."), "commands": commands}, indent=2))
        return
    print(f"Installing optional voices in {py.parent.parent}. Downloads require a connection during setup only.", flush=True)
    env = {key: value for key, value in os.environ.items() if key not in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")}
    env.update(HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1")
    env.setdefault("HF_HOME", str(root() / "models"))
    try:
        for command in commands:
            subprocess.run(command, check=True, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit("Optional voice setup did not complete. Check Python compatibility and install eSpeak NG, "
                         "then run this command again. Your films and other tools were not changed.\n" + str(exc)) from exc
    print("Voice setup passed an offline synthesis check. Recheck setup in the browser.")
