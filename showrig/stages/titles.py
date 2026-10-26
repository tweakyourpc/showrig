"""Title cards and credits, scripted in EffectCraft and rendered as ProRes 4444 with alpha.

Each card keeps its .ecproj next to the .mov, so any title can be opened and reworked in EffectCraft.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from functools import cache

from .. import tools
from ..project import Film, run

MONO = ("JetBrainsMono-Bold", "JetBrainsMonoNF-Bold", "JetBrainsMonoNL-Bold", "NotoSansMono-Bold",
        "DejaVuSansMono-Bold", "Adwaita-Mono-Bold", "NimbusMonoPS-Bold")


@cache
def mono_font() -> str:
    """The first bold monospace face this machine has, by PostScript name, for typewriter titles."""
    if shutil.which("fc-list"):
        have = set(subprocess.run(["fc-list", ":", "postscriptname"], capture_output=True, text=True).stdout
                   .replace(":postscriptname=", "").split())
        for name in MONO:
            if name in have:
                return name
    return MONO[0]


def spec(film: Film, title: dict) -> tuple[str, dict]:
    base = {"width": film.fmt["width"], "height": film.fmt["height"], "fps": film.fmt["fps"],
            "secs": round(title["duration"], 3)}
    if title["layout"] == "credits":
        c = film.board["credits"]
        return "credits.jsx", {**base, "title": c.get("title", film.board["title"]), "lines": c["lines"],
                               "color": film.style["accent"],
                               "font": mono_font() if film.style.get("design") == "terminal" else None}
    scene = next(s for s in film.board["scenes"] if s["id"] == title["scene"])
    template = "studio-title.jsx" if film.style.get("design") else "title.jsx"
    return template, {**base, "name": scene["title"], "tagline": scene.get("tagline", ""),
                         "subtitle": scene.get("subtitle", ""), "color": scene.get("color", film.style["accent"]),
                         "layout": title["layout"], "style": film.style["titles"], "mono": mono_font(),
                         "design": film.style.get("design", "clean"), "place": scene.get("titlePlace", "center"),
                         "inset": .44 if scene.get("image") else 0}


def build(film: Film, plan: dict) -> None:
    out = film.work / "titles"
    out.mkdir(parents=True, exist_ok=True)
    cli = tools.effectcraft()
    for title in plan["titles"]:
        template, data = spec(film, title)
        mov = out / f"{title['scene']}.mov"
        source = (tools.ASSETS / template).read_text()
        key = film.fingerprint(data, source)
        if film.fresh(mov, key):
            continue
        if not cli:
            raise SystemExit("title cards need the EffectCraft CLI (set EFFECTCRAFT_CLI), or set style.titles to none")
        var = "CREDITS" if template == "credits.jsx" else "TITLE"
        jsx = out / f"{title['scene']}.jsx"
        jsx.write_text(f"var {var} = {json.dumps(data)};\n{source}")
        project = out / f"{title['scene']}.ecproj"
        project.unlink(missing_ok=True)
        run([cli, "--empty", "--save-as", project, "script", jsx], film.log(f"title-{title['scene']}.log"))
        run([cli, "--project", project, "--gpu", "render", "--out", mov, "--format", "prores", "--prores", "4444",
             "--channels", "rgba", "--quality", "best", "--audio", "off"], film.log(f"title-{title['scene']}-render.log"))
        film.stamp(mov, key)
        print(f"  title {title['scene']} ({data.get('style', 'credits')}, {data['secs']:.1f}s)")
