"""Recoverable library cleanup and portable editable-film packages."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tempfile
import time
import zipfile
import uuid
from pathlib import Path

from .jobs import write_json
from .project import film_lock, slug


def metadata(root: Path) -> dict:
    """Read optional library state without altering the storyboard schema."""
    try:
        data = json.loads((root / ".library.json").read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def path_for(library: Path, project_id: str, trash: bool = False) -> Path:
    """Resolve a directly owned film folder; cleanup never follows folder aliases."""
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", project_id):
        raise ValueError("Unknown film.")
    parent = library / ".trash" if trash else library
    if parent.is_symlink() or not parent.resolve().is_relative_to(library.resolve()):
        raise ValueError("Trash must stay inside this film library.")
    path = parent / project_id
    if path.is_symlink() or not path.resolve().is_relative_to(parent.resolve()) or not (path / "showrig.json").is_file():
        raise ValueError("Unknown film.")
    return path


def list_films(library: Path, trash: bool = False) -> list[dict]:
    """Read film summaries and library state, excluding hidden working directories."""
    parent = library / ".trash" if trash else library
    if parent.is_symlink() or not parent.resolve().is_relative_to(library.resolve()):
        return []
    items = []
    for file in parent.glob("*/showrig.json"):
        if file.parent.name.startswith(".") or file.parent.is_symlink() or not file.resolve().is_relative_to(parent.resolve()):
            continue
        try:
            board = json.loads(file.read_text())
            info = metadata(file.parent)
            items.append({"id": file.parent.name, "title": board["title"], "kind": board.get("kind", "demo"),
                          "scenes": len(board["scenes"]), "updated": file.stat().st_mtime,
                          "archived": bool(info.get("archived")), "trashedAt": info.get("trashedAt"),
                          "format": board.get("format", {}), "accent": board.get("style", {}).get("accent", "#46d9b0"),
                          "background": board.get("style", {}).get("background", "#111c26"),
                          "exported": (file.parent / "out" / "final.json").is_file() or any((file.parent / "out").glob("*.mp4"))})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(items, key=lambda item: item.get("trashedAt") or item["updated"], reverse=True)


def import_package(library: Path, archive_path: Path) -> tuple[str, dict]:
    """Import one Showrig editable ZIP as a new, directly-owned library film."""
    with tempfile.TemporaryDirectory(prefix="showrig-import-", dir=library.parent) as staging:
        stage = Path(staging)
        try:
            with zipfile.ZipFile(archive_path) as source:
                members = source.infolist()
                if not members:
                    raise ValueError("The ZIP is empty.")
                for member in members:
                    name = Path(member.filename)
                    if name.is_absolute() or ".." in name.parts:
                        raise ValueError("The ZIP contains an unsafe path.")
                    mode = (member.external_attr >> 16) & 0o170000
                    if mode == stat.S_IFLNK:
                        raise ValueError("The ZIP contains a symlink; import a self-contained package instead.")
                source.extractall(stage)
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise ValueError(f"Could not read the project ZIP: {exc}") from exc

        candidates = [path.parent for path in stage.rglob("showrig.json") if path.is_file()]
        if len(candidates) != 1:
            raise ValueError("The ZIP must contain one Showrig project folder with showrig.json.")
        imported = candidates[0].resolve()
        if not imported.is_relative_to(stage.resolve()) or imported.is_symlink():
            raise ValueError("The imported project must stay inside the ZIP.")
        try:
            board = json.loads((imported / "showrig.json").read_text())
        except (OSError, ValueError) as exc:
            raise ValueError(f"The imported project has an invalid showrig.json: {exc}") from exc
        if not isinstance(board, dict) or not isinstance(board.get("title"), str) or not isinstance(board.get("scenes"), list):
            raise ValueError("The ZIP does not contain a valid Showrig project.")

        base = slug(board["title"])[:65] or "imported-film"
        project_id = f"{base}-{uuid.uuid4().hex[:8]}"
        destination = (library / project_id).resolve()
        if not destination.is_relative_to(library.resolve()):
            raise ValueError("The imported project must stay inside the film library.")
        shutil.copytree(imported, destination)
        (destination / ".library.json").write_text(json.dumps({"imported": True}, indent=2))
        return project_id, board


def change(library: Path, project_id: str, action: str) -> None:
    """Archive or move a film intact to/from Trash under its producer lock."""
    if action not in ("archive", "unarchive", "trash", "restore"):
        raise ValueError("Choose archive, unarchive, trash, or restore.")
    root = path_for(library, project_id, trash=action == "restore")
    with film_lock(root):
        info = metadata(root)
        if action in ("archive", "unarchive"):
            info["archived"] = action == "archive"
            write_json(root / ".library.json", info)
        else:
            parent = library if action == "restore" else library / ".trash"
            parent.mkdir(exist_ok=True)
            if parent.is_symlink() or not parent.resolve().is_relative_to(library.resolve()):
                raise ValueError("Trash must stay inside this film library.")
            destination = parent / project_id
            if destination.exists():
                raise ValueError("A film with this folder name already exists. Nothing was replaced.")
            if action == "trash":
                info["trashedAt"] = time.time()
            else:
                info.pop("trashedAt", None)
                info["archived"] = False
            write_json(root / ".library.json", info)
            # Windows cannot rename a directory containing an open lock file. Release below,
            # then rename while the API's library guard prevents competing browser writes.
    if action in ("trash", "restore"):
        root.rename(destination)


def erase(library: Path, project_id: str) -> None:
    """Permanently remove only a directly owned Trash entry after API confirmation."""
    root = path_for(library, project_id, trash=True)
    with film_lock(root):
        pass
    shutil.rmtree(root)


def package(root: Path) -> Path:
    """Create a ZIP with source media and generated assets, rebasing FilmCraft paths.

    No user files are modified. Symlinks and references outside this film are refused,
    rather than producing a deceptively portable archive with missing media.
    """
    if not any(root.rglob("*.fcproj")):
        raise ValueError("Render a preview or export first to create an editable FilmCraft project.")
    handle, name = tempfile.mkstemp(prefix="showrig-editable-", suffix=".zip")
    os.close(handle)
    destination = Path(name)
    try:
        with film_lock(root), zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
            projects = []
            for folder, dirs, files in os.walk(root, followlinks=False):
                for directory in dirs:
                    if (Path(folder) / directory).is_symlink():
                        raise ValueError("This film links to media outside its folder. Import copies before packaging it.")
                for filename in files:
                    file = Path(folder) / filename
                    if filename in (".render.lock", ".library.json") or filename.endswith(".tmp"):
                        continue
                    if Path(folder) == root and filename in ("showrig-portable.json", ".showrig-prepared.json", "PREPARE-EDIT.py",
                                                            "Prepare edit.command", "Prepare edit.cmd", "OPEN-IN-FILMCRAFT.txt"):
                        continue
                    if file.is_symlink():
                        raise ValueError("This film links to external media. Import copies before packaging it.")
                    relative = file.relative_to(root)
                    target = f"{root.name}/{relative.as_posix()}"
                    if file.suffix == ".fcproj":
                        data = json.loads(file.read_text())
                        links = {}

                        def rebase(value, key=""):
                            if isinstance(value, dict):
                                return {name: rebase(item, name) for name, item in value.items()}
                            if isinstance(value, list):
                                return [rebase(item) for item in value]
                            if isinstance(value, str) and value and (key == "path" or value.startswith(str(root)) or Path(value).is_absolute()):
                                path = Path(value)
                                if not path.is_absolute():
                                    path = (file.parent / path).resolve()
                                if path.is_relative_to(root):
                                    rebased = Path(os.path.relpath(path, file.parent)).as_posix()
                                    if path.is_file():
                                        links[rebased] = path.relative_to(root).as_posix()
                                    elif key == "path":
                                        raise ValueError("The FilmCraft project has missing media. Relink it before packaging.")
                                    return rebased
                                if path.is_file() or key == "path":
                                    raise ValueError("The FilmCraft project uses external files. Import them into this film before packaging.")
                            return value

                        archive.writestr(target, json.dumps(rebase(data), indent=2))
                        projects.append({"project": relative.as_posix(), "media": links})
                    else:
                        archive.write(file, target)
            preferred = max((root / item["project"] for item in projects),
                            key=lambda path: (path.parent == root / "out", path.stat().st_mtime))
            archive.writestr(f"{root.name}/showrig-portable.json", json.dumps(
                {"schema": 1, "preferredProject": preferred.relative_to(root).as_posix(), "projects": projects}, indent=2))
            archive.write(Path(__file__).parent / "assets/prepare_edit.py", f"{root.name}/PREPARE-EDIT.py")
            launcher = zipfile.ZipInfo(f"{root.name}/Prepare edit.command")
            launcher.external_attr = (stat.S_IFREG | 0o755) << 16
            archive.writestr(launcher, '#!/bin/sh\ncd -- "$(dirname -- "$0")"\npython3 PREPARE-EDIT.py\n')
            archive.writestr(f"{root.name}/Prepare edit.cmd",
                             '@echo off\r\ncd /d "%~dp0"\r\nwhere py >nul 2>nul\r\nif errorlevel 1 (python PREPARE-EDIT.py) else (py -3 PREPARE-EDIT.py)\r\npause\r\n')
            archive.writestr(f"{root.name}/OPEN-IN-FILMCRAFT.txt",
                             "Extract this entire folder. Run PREPARE-EDIT.py with Python 3.11+ first.\n"
                             "Windows: Prepare edit.cmd. macOS/Linux: python3 PREPARE-EDIT.py.\n"
                             "Then open the project printed by the helper in FilmCraft.\n"
                             "The helper binds media to this folder without changing your edits; rerun it if the folder moves.\n"
                             "Keep assets/, work/ and out/ together.\n"
                             "The MP4 is a finished video; the .fcproj is the editable timeline.\n"
                             "Native FilmCraft and any required fonts must be available on the editing computer.\n")
        return destination
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
