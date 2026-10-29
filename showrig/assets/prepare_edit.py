"""Prepare an extracted Showrig package for FilmCraft, without Showrig installed.

FilmCraft versions that resolve media from the process directory need absolute paths.
Run this helper after extraction, and again if the package moves to another folder.
Only known packaged media references change; timeline edits are preserved.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess


def inside(root: Path, relative: str) -> Path:
    """Resolve only files belonging to this extracted package."""
    portable = PurePosixPath(relative)
    if portable.is_absolute() or ".." in portable.parts:
        raise ValueError("Invalid package path.")
    path = root.joinpath(*portable.parts).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"A packaged file is missing: {relative}. Extract the entire ZIP first.")
    return path


def prepare(root: Path) -> Path:
    """Rebind packaged media after extraction or relocation, preserving edits."""
    root = root.resolve()
    manifest = json.loads((root / "showrig-portable.json").read_text())
    receipt_path = root / ".showrig-prepared.json"
    previous = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
    prepared, receipt = [], {}
    for item in manifest["projects"]:
        relative = item["project"]
        file = inside(root, relative)
        replacements, remembered = {}, {}
        for old, asset in item["media"].items():
            absolute = str(inside(root, asset))
            replacements[old] = absolute
            prior = previous.get(relative, {}).get(old)
            if prior:
                replacements[prior] = absolute
            remembered[old] = absolute

        def rebind(value):
            if isinstance(value, dict):
                return {key: rebind(item) for key, item in value.items()}
            if isinstance(value, list):
                return [rebind(item) for item in value]
            return replacements.get(value, value) if isinstance(value, str) else value

        prepared.append((file, rebind(json.loads(file.read_text()))))
        receipt[relative] = remembered
    # Validate every referenced asset before writing any project.
    for file, data in prepared:
        temporary = file.with_suffix(file.suffix + ".preparing.tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n")
        temporary.replace(file)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return inside(root, manifest["preferredProject"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--open", action="store_true", help="also launch FilmCraft if its GUI executable is on PATH")
    args = parser.parse_args()
    try:
        project = prepare(Path(__file__).resolve().parent)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"The film could not be prepared: {exc}") from exc
    print(f"Ready to edit in FilmCraft:\n{project}\nKeep this folder together. Run this helper again if it moves.")
    if args.open:
        program = os.environ.get("FILMCRAFT") or shutil.which("filmcraft")
        if not program:
            raise SystemExit("Media is ready. Open the project printed above in your FilmCraft application.")
        subprocess.Popen([program, str(project)], cwd=project.parent)


if __name__ == "__main__":
    main()
