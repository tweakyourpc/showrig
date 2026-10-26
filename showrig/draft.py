"""The optional AI pass: a local model suggests narration and taglines for scenes that have none.

It runs once, before the offline build, through Ollama on this machine. It only fills empty
fields, marks what it wrote, and leaves the storyboard for you to read and edit.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .board import markdown
from .project import Film

HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
PROMPT = """You write narration for a short {kind} film titled "{film}".
Scene {n} of {total} is a {scene_kind} titled "{title}"{tagline}.{context}
Reply with JSON only: {{"tagline": "under 8 words", "lines": ["2 or 3 short spoken sentences"]}}.
Plain, concrete, no hype words, no exclamation marks."""


def ask(model: str, prompt: str) -> dict:
    host = HOST if "://" in HOST else f"http://{HOST}"
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json", "think": False,
                       "options": {"temperature": 0.6}}).encode()
    req = urllib.request.Request(f"{host}/api/generate", body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(json.loads(r.read())["response"])
    except urllib.error.URLError as e:
        raise SystemExit(f"Ollama is not reachable at {host} ({e.reason}); start it with `ollama serve`")


def draft(film: Film, model: str) -> None:
    scenes = film.board["scenes"]
    filled = 0
    for n, s in enumerate(scenes, 1):
        if s["lines"] and s.get("tagline"):
            continue
        context = f" Notes from the director: {s['brief']}." if s.get("brief") else ""
        reply = ask(model, PROMPT.format(kind=film.board["kind"], film=film.board["title"], n=n, total=len(scenes),
                                         scene_kind=s["kind"], title=s["title"], context=context,
                                         tagline=f' ("{s["tagline"]}")' if s.get("tagline") else ""))
        if not s.get("tagline") and reply.get("tagline"):
            s["tagline"] = reply["tagline"].strip()
        if not s["lines"] and reply.get("lines"):
            s["lines"] = [str(x).strip() for x in reply["lines"] if str(x).strip()]
        s["drafted"] = model
        filled += 1
        print(f"  {s['id']}: {s.get('tagline', '')}")
        for line in s["lines"]:
            print(f"    > {line}")
    film.save()
    (film.root / "STORYBOARD.md").write_text(markdown(film.board))
    print(f"\ndrafted {filled} scene(s) with {model}. Read STORYBOARD.md and edit showrig.json before `showrig make`.")
