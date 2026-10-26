"""Offline browser studio backed by the existing Showrig production pipeline."""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
import uuid
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, tools
from .board import markdown
from .jobs import Jobs, write_json
from .project import film_lock, probe, slug
from .studio import LOOKS, TEMPLATES, estimate, media_references, new_board, resolve_media, validate

STATIC = Path(__file__).parent / "static"
MEDIA_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".mkv", ".webm", ".wav", ".mp3", ".m4a", ".flac", ".ogg"}
UPLOAD_LIMIT = 1024 * 1024 * 1024


def app_from_environment() -> FastAPI:
    """Factory for process managers; PORT must come from a broker reservation."""
    if not os.environ.get("PORT"):
        raise RuntimeError("Set PORT to the portbroker reservation for showrig.")
    return create_app(Path(os.environ.get("SHOWRIG_PROJECTS", "films")),
                      os.environ.get("SHOWRIG_HOST", "0.0.0.0"), int(os.environ["PORT"]))


def create_app(projects: Path, host: str = "0.0.0.0", port: int = 0) -> FastAPI:
    """Create an app confined to one project library and its bundled examples."""
    projects = projects.resolve()
    projects.mkdir(parents=True, exist_ok=True)
    jobs = Jobs(projects)
    allowed = [projects, projects.parent / "examples"]
    speech = {}
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    @asynccontextmanager
    async def lifespan(app):
        yield
        jobs.close()

    app = FastAPI(title="Showrig", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.jobs = jobs

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        """Reject cross-origin writes and apply local-only browser policy."""
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if request.headers.get("x-showrig-request") != "1" or (origin and urlparse(origin).netloc != request.headers.get("host")):
                return JSONResponse({"detail": "Open the wizard on this Showrig server to make changes."}, status_code=403)
            limit = UPLOAD_LIMIT + 1024 * 1024 if request.url.path.endswith("/assets") else 2 * 1024 * 1024
            if int(request.headers.get("content-length", "0")) > limit:
                return JSONResponse({"detail": "This upload is too large."}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; object-src 'none'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def bad_input(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    def project_path(project_id: str) -> Path:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", project_id):
            raise HTTPException(404, "Unknown film.")
        path = (projects / project_id).resolve()
        if not path.is_relative_to(projects) or not (path / "showrig.json").is_file():
            raise HTTPException(404, "Unknown film.")
        return path

    def editable(root: Path) -> None:
        if jobs.active and jobs.read(jobs.active)["project"] == root.name:
            raise HTTPException(409, "This film is rendering. Cancel the render before editing it.")

    def result_manifest(root: Path, mode: str) -> dict | None:
        manifest = root / "out" / f"{mode}.json"
        if manifest.is_file():
            return json.loads(manifest.read_text())
        if mode == "final":
            board = json.loads((root / "showrig.json").read_text())
            name = slug(board["title"])
            paths = {ext: f"out/{name}.{ext}" for ext in ("mp4", "fcproj", "srt") if (root / "out" / f"{name}.{ext}").is_file()}
            if "mp4" in paths:
                return {"mode": mode, "files": paths, "title": board["title"], "legacy": True}
        return None

    @app.get("/whoami")
    def whoami():
        return {"service": "showrig", "version": __version__, "pid": os.getpid(),
                "startedAt": started, "host": host, "port": port}

    @app.get("/api/catalog")
    def catalog():
        return {"templates": TEMPLATES, "looks": LOOKS}

    @app.get("/api/capabilities")
    def capabilities():
        checks = [("ffmpeg", shutil.which("ffmpeg")), ("ffprobe", shutil.which("ffprobe")),
                  ("FilmCraft", tools.filmcraft()), ("EffectCraft", tools.effectcraft())]
        missing = []
        for name, path in checks:
            try:
                flag = "-version" if name in ("ffmpeg", "ffprobe") else "--help"
                if not path or subprocess.run([path, flag], capture_output=True, timeout=10).returncode:
                    missing.append(name)
            except (OSError, subprocess.SubprocessError):
                missing.append(name)
        return {"ready": not missing, "missing": missing, "blender": bool(tools.blender()),
                "speech": speech, "offline": True, "activeJob": jobs.read(jobs.active) if jobs.active else None}

    @app.post("/api/speech/check")
    def check_speech(body: dict):
        voice = body.get("voice", "af_heart")
        if voice not in ("af_heart", "af_bella", "am_michael", "bf_emma", "bm_george"):
            raise ValueError("Choose a supported voice.")
        py = tools.tts_python()
        result = {"ready": False, "reason": "Kokoro is not installed. Use your own recordings or no narration."}
        if py:
            try:
                check = subprocess.run([py, tools.ASSETS / "tts_kokoro.py", "--check", voice],
                                       capture_output=True, text=True, timeout=120)
                result = {"ready": check.returncode == 0, "reason": "Ready for offline narration." if not check.returncode else
                          "Offline speech is not ready. The installed language package or voice model needs repair.",
                          "detail": (check.stderr or check.stdout)[-1800:] if check.returncode else ""}
            except (OSError, subprocess.SubprocessError) as exc:
                result = {"ready": False, "reason": "The local speech check could not finish.", "detail": str(exc)}
        speech[voice] = result
        return result

    @app.get("/api/projects")
    def list_projects():
        items = []
        for path in projects.glob("*/showrig.json"):
            if not path.resolve().is_relative_to(projects):
                continue
            try:
                board = json.loads(path.read_text())
                items.append({"id": path.parent.name, "title": board["title"], "kind": board.get("kind", "demo"),
                              "scenes": len(board["scenes"]), "updated": path.stat().st_mtime})
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(items, key=lambda item: item["updated"], reverse=True)

    @app.post("/api/projects", status_code=201)
    def create_project(body: dict):
        title = body.get("title", "Untitled film")
        if not isinstance(title, str) or not title.strip() or len(title) > 120:
            raise ValueError("Enter a film title of up to 120 characters.")
        board = new_board(title, body.get("template", "demo"))
        project_id = slug(title)[:65] + "-" + uuid.uuid4().hex[:8]
        root = projects / project_id
        (root / "assets").mkdir(parents=True)
        write_json(root / "showrig.json", board)
        (root / "STORYBOARD.md").write_text(markdown(board))
        return {"id": project_id, "board": board, "estimate": estimate(board)}

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str):
        root = project_path(project_id)
        board = json.loads((root / "showrig.json").read_text())
        missing = []
        for _, value in media_references(board):
            try:
                path = resolve_media(root, value)
                if not path.is_file() or not any(path.is_relative_to(p.resolve()) for p in allowed):
                    missing.append(value)
            except ValueError:
                missing.append(value)
        return {"id": project_id, "board": board, "estimate": estimate(board, root), "missing": missing,
                "outputs": {m: result_manifest(root, m) for m in ("preview", "final")}, "job": jobs.latest(project_id)}

    @app.put("/api/projects/{project_id}")
    def save_project(project_id: str, body: dict):
        root = project_path(project_id)
        editable(root)
        board = validate(body, root, allowed)
        try:
            with film_lock(root):
                write_json(root / "showrig.json", board)
                (root / "STORYBOARD.md").write_text(markdown(board))
        except SystemExit as exc:
            raise HTTPException(409, str(exc))
        return {"board": board, "estimate": estimate(board, root)}

    @app.post("/api/projects/{project_id}/assets")
    async def upload(project_id: str, file: UploadFile):
        root = project_path(project_id)
        editable(root)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in MEDIA_TYPES:
            raise ValueError("Choose a PNG, JPEG, WebP, video, or audio file.")
        folder = root / "assets"
        folder.mkdir(exist_ok=True)
        if not folder.resolve().is_relative_to(root):
            raise ValueError("The assets folder must stay inside this film folder.")
        path = folder / (slug(Path(file.filename).stem)[:50] + "-" + uuid.uuid4().hex[:8] + suffix)
        total = 0
        try:
            with path.open("wb") as target:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > UPLOAD_LIMIT:
                        raise ValueError("Each file must be smaller than 1 GB.")
                    target.write(chunk)
            from starlette.concurrency import run_in_threadpool
            info = await run_in_threadpool(probe, path)
            if not info["width"] and not info["audio"]:
                raise ValueError("This file contains no supported pictures or audio.")
        except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
            path.unlink(missing_ok=True)
            raise ValueError(f"Could not read this media file: {str(exc)[-300:]}")
        finally:
            await file.close()
        return {"path": str(path.relative_to(root)), "name": file.filename, "info": info}

    @app.get("/api/projects/{project_id}/media")
    def media(project_id: str, path: str):
        root = project_path(project_id)
        resolved = (root / path).resolve()
        if not resolved.is_relative_to(root / "assets") or not resolved.is_file() or resolved.suffix.lower() not in MEDIA_TYPES:
            raise HTTPException(404, "Media is unavailable. Upload a replacement if it moved.")
        return FileResponse(resolved)

    @app.post("/api/projects/{project_id}/render", status_code=202)
    def render(project_id: str, body: dict):
        root = project_path(project_id)
        mode = body.get("mode", "preview")
        if mode not in ("preview", "final"):
            raise ValueError("Choose preview or final export.")
        board = validate(json.loads((root / "showrig.json").read_text()), root, allowed, render=True)
        if board["voice"]["source"] == "tts" and not speech.get(board["voice"]["voice"], {}).get("ready"):
            raise ValueError("Check your selected offline voice in the Sound step before rendering.")
        if not capabilities()["ready"]:
            raise ValueError("Required video tools are unavailable. See the setup status.")
        if board["style"]["showcase3d"] and not tools.blender():
            raise ValueError("Blender is unavailable. Turn off the 3D showcase in Look.")
        try:
            return jobs.start(root, mode)
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str):
        try:
            return jobs.read(job_id)
        except FileNotFoundError:
            raise HTTPException(404, "Unknown render job.")

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        return jobs.cancel(job_id)

    @app.get("/api/jobs/{job_id}/log")
    def job_log(job_id: str):
        job_status(job_id)
        return FileResponse(jobs.root / f"{job_id}.log", media_type="text/plain", filename="showrig-render.log")

    @app.get("/api/projects/{project_id}/outputs/{mode}/{extension}")
    def output(project_id: str, mode: str, extension: str, download: bool = False):
        root = project_path(project_id)
        if mode not in ("preview", "final") or extension not in ("mp4", "fcproj", "srt"):
            raise HTTPException(404, "Unknown output.")
        manifest = result_manifest(root, mode)
        relative = (manifest or {}).get("files", {}).get(extension)
        path = (root / relative).resolve() if relative else None
        if not path or not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(404, "Render this film to create the requested output.")
        types = {"mp4": "video/mp4", "srt": "application/x-subrip", "fcproj": "application/json"}
        return FileResponse(path, media_type=types[extension], filename=path.name if download else None)

    @app.get("/api/projects/{project_id}/storyboard")
    def storyboard(project_id: str):
        return FileResponse(project_path(project_id) / "STORYBOARD.md", media_type="text/markdown", filename="STORYBOARD.md")

    @app.get("/")
    def home():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def serve(projects: Path, host: str, port: int | None, open_browser: bool) -> None:
    """Reserve a real homelab port and start the local studio."""
    import uvicorn
    if port is None:
        try:
            result = subprocess.run(["portbroker", "get", "--name", "showrig"], capture_output=True, text=True)
            if result.returncode:
                result = subprocess.run(["portbroker", "alloc", "--name", "showrig"], capture_output=True, text=True, check=True)
            port = int(result.stdout.strip())
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            raise SystemExit(f"Could not obtain a port from portbroker: {exc}. Run `portbroker alloc --name showrig` first.")
    if not 1 <= port <= 65535:
        raise SystemExit("Use a valid port reserved through portbroker.")
    address = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"Showrig studio: http://{address}:{port}\nFilm library: {projects.resolve()}", flush=True)
    if host == "0.0.0.0":
        try:
            addresses = subprocess.check_output(["hostname", "-I"], text=True).split()
            if addresses:
                print(f"On your network: http://{addresses[0]}:{port}", flush=True)
        except (OSError, subprocess.SubprocessError):
            pass
    if open_browser:
        import threading
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{address}:{port}")).start()
    uvicorn.run(create_app(projects, host, port), host=host, port=port, log_level="warning")
