"""Render immutable input snapshots and publish only successful outputs."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

from .cli import STAGES, make
from .jobs import write_json
from .project import Film, film_lock, probe
from .studio import media_references, resolve_media

LABELS = {"footage": "Preparing your pictures", "voice": "Preparing narration", "plan": "Timing the scenes",
          "titles": "Animating titles", "stage": "Rendering backgrounds", "music": "Scoring the film",
          "assemble": "Assembling the edit", "render": "Exporting the video"}


def execute(root: Path, status_path: Path, mode: str) -> None:
    """Build in a content-addressed workspace, preserving all previous exports."""
    state = json.loads(status_path.read_text())
    state.update(pid=os.getpid(), status="running")
    write_json(status_path, state)
    try:
        with film_lock(root):
            original = Film.load(root)
            board = copy.deepcopy(original.board)
            media = []
            for (owner, key), value in media_references(board):
                path = resolve_media(root, value)
                owner[key] = str(path)
                stat = path.stat()
                media.append((str(path), stat.st_size, stat.st_mtime_ns))
            for scene in board["scenes"]:
                for shot in scene.get("shots", []):
                    if shot.get("capture"):
                        shot["capture"]["offline"] = True
            if mode == "preview":
                board["format"] = {**board["format"], "width": max(2, board["format"]["width"] // 4 * 2),
                                   "height": max(2, board["format"]["height"] // 4 * 2), "fps": 30}
                board["style"]["quality"] = "draft"
            code = hashlib.sha256()
            package = Path(__file__).parent
            for path in sorted(list(package.glob("*.py")) + list((package / "stages").glob("*.py")) + list((package / "assets").glob("*"))):
                if path.is_file():
                    code.update(path.read_bytes())
            key = hashlib.sha256(json.dumps([board, media, code.hexdigest()], sort_keys=True).encode()).hexdigest()[:20]
            workspace = root / "work" / "builds" / f"{mode}-{key}"
            workspace.mkdir(parents=True, exist_ok=True)
            write_json(workspace / "showrig.json", board)
            film = Film(workspace, board)

            def progress(stage: str) -> None:
                """Persist an actual pipeline stage boundary for the browser."""
                state.update(stage=LABELS[stage], completedStages=STAGES.index(stage))
                write_json(status_path, state)

            make(film, "render", mode == "preview", progress)
            info = probe(film.out / f"{film.name}.mp4")
            plan = json.loads((film.work / "plan.json").read_text())
            if abs(info["duration"] - plan["duration"]) > max(.25, 3 / film.fmt["fps"]):
                raise ValueError("Export duration differs from the storyboard. The previous export has been preserved.")
            outputs = {suffix: str((film.out / f"{film.name}.{suffix}").relative_to(root))
                       for suffix in ("mp4", "fcproj", "srt") if (film.out / f"{film.name}.{suffix}").exists()}
            manifest = {"job": state["id"], "mode": mode, "created": time.time(), "duration": info["duration"],
                        "format": film.fmt, "files": outputs, "title": board["title"]}
            if mode == "final":
                root.joinpath("out").mkdir(exist_ok=True)
                for suffix, relative in outputs.items():
                    destination = root / "out" / f"{film.name}.{suffix}"
                    temporary = destination.with_name(destination.name + ".publishing")
                    shutil.copy2(root / relative, temporary)
                    temporary.replace(destination)
            write_json(root / "out" / f"{mode}.json", manifest)
            state.update(status="succeeded", stage="Ready to watch", completedStages=8,
                         finished=time.time(), output=manifest)
            write_json(status_path, state)
    except (Exception, SystemExit) as exc:
        state.update(status="failed", error=str(exc)[-4000:], finished=time.time())
        write_json(status_path, state)
        raise


if __name__ == "__main__":
    execute(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3])
