#!/usr/bin/env python3
"""Write pages/agent-terminal/index.html: the real tool calls behind this film, replayed in a terminal.

  tools/make-terminal-page.py [FILM_DIR]        default: <showrig>/films/tweakyourpc-promo

Every command and output line comes from the film's own build logs (work/logs), in the order the
build ran them: the voice, the EffectCraft titles, the Blender stage, the FilmCraft edit and export.
Paths are shortened for reading. The page types the session out over about 25 seconds when it is
opened, and needs nothing from the network.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
LOGS = ["voice-tts", "title-hello", "title-hello-render", "title-game-night-render", "blender-intro", "blender-made-here",
        "fc-01-create", "fc-02-import", "fc-03-place", "fc-04-motion-transitions", "render"]
SKIP = re.compile(r"^(WARNING|Read prefs|Blender \d|  warnings\.|/.*UserWarning|\{$|\}$|\s*\"[a-z]+\": \[\]?,?$)")


def tidy(text: str, film: Path) -> str:
    text = text.replace(str(film), "~/films/" + film.name)
    text = re.sub(r"/\S*/(blender_stage|tts_kokoro)\.py", r"\1.py", text)
    text = re.sub(r"/\S*/bin/(filmcraft-cli|effectcraft-cli|python|blender)\b", r"\1", text)
    text = re.sub(r"--settings \{.*", "--settings '{\"loudness\": -16 LUFS, …}'", text)
    return text if len(text) <= 150 else text[:149] + "…"


def session(film: Path) -> list[tuple[str, str]]:
    lines = []
    for name in LOGS:
        log = film / "work" / "logs" / f"{name}.log"
        if not log.exists():
            continue
        rows = [r for r in log.read_text(errors="replace").splitlines() if r.strip() and not SKIP.match(r)]
        if not rows or not rows[0].startswith("$ "):
            continue
        lines.append(("cmd", tidy(rows[0][2:], film)))
        lines += [("out", tidy(r, film)) for r in rows[1:4]]
    text = json.dumps(lines)
    if re.search(r"showrig", text, re.I):
        raise SystemExit("a log line still names the build tool; extend tidy() before publishing the page")
    return lines


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Tool calls</title>
<style>
  html, body {{ margin: 0; height: 100%; background: #0b1714; }}
  body {{ display: grid; place-items: center; font: 17px/1.55 "JetBrains Mono", "Noto Sans Mono", "DejaVu Sans Mono", monospace; }}
  .term {{ width: 1680px; height: 900px; background: #0f1d19; border: 1px solid #24433a; border-radius: 14px;
          box-shadow: 0 0 80px #46d9b022; display: flex; flex-direction: column; overflow: hidden; }}
  .bar {{ padding: 14px 20px; color: #7f9c93; border-bottom: 1px solid #24433a; display: flex; gap: 10px; align-items: center; }}
  .dot {{ width: 12px; height: 12px; border-radius: 50%; background: #2c4a41; }}
  .bar b {{ color: #cfe6de; font-weight: 600; margin-left: 10px; }}
  .log {{ flex: 1; padding: 18px 26px; overflow: hidden; display: flex; flex-direction: column; justify-content: flex-end; }}
  .cmd {{ color: #e8f3ef; margin-top: 10px; white-space: pre-wrap; }}
  .cmd::before {{ content: "$ "; color: #46d9b0; }}
  .out {{ color: #8fb3a7; white-space: pre-wrap; }}
  .cursor {{ display: inline-block; width: .6em; height: 1.1em; background: #46d9b0; vertical-align: text-bottom; }}
</style></head>
<body><div class="term"><div class="bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span>
<b>~/films/{film}</b><span>tool calls, from the build logs</span></div><div class="log" id="log"></div></div>
<script>
const LINES = {lines};
const log = document.getElementById('log');
const cursor = Object.assign(document.createElement('span'), {{className: 'cursor'}});
const total = 25000, perChar = 6;
const budget = LINES.reduce((n, [kind, text]) => n + (kind === 'cmd' ? text.length * perChar : 0) + 120, 0);
const scale = total / budget;  // stretch or squeeze the replay to fill the shot
let i = 0;
function next() {{
  if (i >= LINES.length) {{ log.appendChild(cursor); return; }}
  const [kind, text] = LINES[i++];
  const row = Object.assign(document.createElement('div'), {{className: kind}});
  log.appendChild(row);
  while (log.children.length > 34) log.firstChild.remove();
  if (kind === 'out') {{ row.textContent = text; return setTimeout(next, 120 * scale); }}
  let n = 0;
  (function type() {{
    row.textContent = text.slice(0, ++n);
    row.appendChild(cursor);
    if (n < text.length) setTimeout(type, perChar * scale); else setTimeout(next, 260 * scale);
  }})();
}}
setTimeout(next, 400);
</script></body></html>
"""


def main() -> None:
    film = Path(sys.argv[1] if len(sys.argv) > 1 else KIT.parents[1] / "films" / "tweakyourpc-promo")
    lines = session(film)
    if not lines:
        raise SystemExit(f"no build logs in {film / 'work/logs'}: build the film first")
    out = KIT / "pages" / "agent-terminal" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(PAGE.format(film=html.escape(film.name), lines=json.dumps(lines)))
    print(f"wrote {out.relative_to(KIT)}: {len(lines)} lines from {film / 'work/logs'}")


if __name__ == "__main__":
    main()
