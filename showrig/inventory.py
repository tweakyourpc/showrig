"""A description of this computer for planning a Showrig install: OS, CPU, memory, disk, graphics and the
tools already present. Standard library only, so it runs on a machine with nothing installed:

  python3 inventory.py [--out machine.json]

It reads no environment values beyond the display session type, and records no user names: paths
under the home directory are written from ~.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path

SCHEMA = 1
TOOLS = {  # name: (command, version arguments)
    "python3": ("python3", ["--version"]),
    "ffmpeg": ("ffmpeg", ["-version"]),
    "blender": ("blender", ["--version"]),
    "node": ("node", ["--version"]),
    "npm": ("npm", ["--version"]),
    "filmcraft-cli": ("filmcraft-cli", ["--version"]),
    "effectcraft-cli": ("effectcraft-cli", ["--version"]),
    "ollama": ("ollama", ["--version"]),
    "nvidia-smi": ("nvidia-smi", ["--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]),
    "vulkaninfo": ("vulkaninfo", ["--summary"]),
    "fc-list": ("fc-list", ["--version"]),
}


def _out(cmd: list[str], timeout: float = 20) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return (r.stdout or r.stderr).strip() if r.returncode == 0 else None


def os_release() -> dict:
    try:
        rows = Path("/etc/os-release").read_text().splitlines()
    except OSError:
        return {}
    pairs = dict(line.split("=", 1) for line in rows if "=" in line)
    return {k.lower(): pairs[k].strip('"') for k in ("ID", "VERSION_ID", "PRETTY_NAME") if k in pairs}


def cpu() -> dict:
    model = None
    try:
        model = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                      if line.startswith("model name")), None)
    except OSError:
        pass
    return {"model": model or platform.processor() or None, "logical": os.cpu_count()}


def memory_gb() -> float | None:
    try:
        kb = int(re.search(r"MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text()).group(1))
    except (OSError, AttributeError):
        return None
    return round(kb / 1024 ** 2, 1)


def graphics() -> list[dict]:
    """Each DRM device with its PCI id and kernel driver, plus what lspci calls it."""
    names = {}
    listing = _out(["lspci", "-nn"]) or ""
    for line in listing.splitlines():
        if re.search(r"VGA|3D|Display", line):
            ids = re.search(r"\[([0-9a-f]{4}:[0-9a-f]{4})\]", line)
            if ids:
                names[ids.group(1)] = line.split(": ", 1)[-1]
    out = []
    for card in sorted(Path("/sys/class/drm").glob("card[0-9]")):
        dev = card / "device"
        try:
            vendor = (dev / "vendor").read_text().strip()[2:]
            device = (dev / "device").read_text().strip()[2:]
        except OSError:
            continue
        driver = (dev / "driver").resolve().name if (dev / "driver").exists() else None
        out.append({"card": card.name, "pci": f"{vendor}:{device}", "driver": driver,
                    "name": names.get(f"{vendor}:{device}"),
                    "render_node": any(Path("/dev/dri").glob("renderD*"))})
    return out


def tools() -> dict:
    found = {}
    for name, (cmd, args) in TOOLS.items():
        path = shutil.which(cmd)
        text = _out([path, *args]) if path else None
        lines = (text or "").splitlines()
        line = next((x for x in lines if re.search(r"\d+\.\d+", x)), lines[0] if lines else None)
        home = str(Path.home())
        shown = "~" + path[len(home):] if path and path.startswith(home + "/") else path
        found[name] = {"path": shown, "version": line[:160] if line else None}
    return found


def collect() -> dict:
    home = Path.home()
    usage = shutil.disk_usage(home)
    return {
        "schema": SCHEMA, "kind": "showrig-inventory", "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "os": {**os_release(), "system": platform.system(), "kernel": platform.release(), "arch": platform.machine()},
        "cpu": cpu(), "memory_gb": memory_gb(),
        "disk": {"home_free_gb": round(usage.free / 1e9, 1), "home_total_gb": round(usage.total / 1e9, 1)},
        "graphics": graphics(),
        "session": {"type": os.environ.get("XDG_SESSION_TYPE"), "display": bool(os.environ.get("DISPLAY")),
                    "wayland": bool(os.environ.get("WAYLAND_DISPLAY"))},
        "tools": tools(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, help="write the JSON here instead of printing it")
    a = ap.parse_args()
    text = json.dumps(collect(), indent=1)
    if a.out:
        a.out.write_text(text + "\n")
        print(f"wrote {a.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
