# Showrig

![Showrig: storyboard in, editable film out](docs/hero.jpg)

**A director's wizard for short films made entirely on your own machine.**

> **Work in progress.** Showrig is early and changing fast: every new film so far has needed something new
> from it. It works end to end (the [tweakyourpc promo](examples/tweakyourpc-promo) was built with it), but
> expect rough edges and breaking changes.

Showrig asks the questions a director and producer would answer: what kind of film, what it should
look like, who speaks, what plays underneath. You bring footage, recordings and music, or let Showrig
record web pages and generate them. It writes a storyboard for you to sign off. From there everything
is procedural:

| Step | Tool | Result |
|---|---|---|
| Footage | FFmpeg; headless Chromium on the GPU for scripted page recordings (typing, clicks, eased scrolls) | every shot at the film's size and frame rate |
| Voice | Kokoro-82M offline text to speech, or your own WAVs | levelled voice lines |
| Plan | Showrig | a frame-exact edit: each scene as long as its narration needs |
| 3D showcase | Blender EEVEE | your footage on floating, glowing screens: an opening arc, one establishing shot per segment, a closing wall |
| Titles | EffectCraft (ArtCraft) | title cards (rise or typewriter) and rolling credits, with alpha, each one an editable `.ecproj` |
| Music | Showrig's synthesizer, or your track | a score cut to length, ducked under the voice |
| Edit | FilmCraft (ArtCraft) | an editable `.fcproj`: picture, titles, notes, voice, music, captions |
| Render | FilmCraft, NVENC when there is a GPU | `.mp4` and `.srt` |

Nothing is uploaded. An optional AI pass (`showrig draft`) uses a local model through Ollama to suggest
narration before the offline build. It only fills empty fields, and you review what it wrote.

## Quick start

### Browser studio

```sh
pip install -e .
showrig web
```

This opens a local five-step wizard: **Purpose → Look → Story → Sound → Review**.
Choose a demo, showcase, announcement, or explainer; select a visual treatment; then
write your scenes and optionally add images, video clips, music, or recordings.
The studio saves your work as you go. Reorder or duplicate scenes, render a half-size
preview, and export a full-size MP4, editable FilmCraft project, and optional SRT captions.

Text alone is enough to make a film. New films use content-based timing and 1080p at
30 fps, with 2D titles and procedural music. Portrait and square layouts are available.
Uploaded clip audio is omitted; add narration and music in the Sound step. Images
start at zero; use the scene's minimum duration to keep them on screen longer.

All fonts, interface files, media processing, and music generation are local. The
normal workflow needs FFmpeg, ffprobe, FilmCraft, and EffectCraft. Blender is optional
for landscape 3D scenes. Kokoro speech is optional and is only enabled after a real
offline synthesis check for the selected voice. Models are never downloaded during
production; configure a prepared environment with `SHOWRIG_TTS_PYTHON`.

The launcher obtains its port from `portbroker` and binds to `0.0.0.0`, so another
device on your LAN can use the studio. If running under a process manager, or when
the broker must run separately:

```sh
PORT=$(portbroker get --name showrig || portbroker alloc --name showrig)
showrig web --port "$PORT" --no-open
```

Use `showrig web --projects /path/to/films` for a different film library. Existing
films in that folder appear automatically. Media outside the library or its sibling
`examples/` folder must be uploaded before the web studio can render it. Web captures
from legacy projects accept local HTML files only and block external requests.

Render jobs continue when you close the browser tab. Only one film renders at a time;
editing that film is paused until it finishes or you cancel. Closing the server cancels
its active render. Failed and cancelled jobs keep your last successful output.

The web studio stores immutable render workspaces under `work/builds/`, job logs under
the library's `.jobs/`, and successful export manifests under `out/`. Unchanged inputs
reuse their workspace. Each successful editable project refers to its retained build
assets, so keep `work/builds/` while using those projects. The MP4 and SRT are standalone.

### Terminal workflow

```sh
pip install -e .
showrig doctor                       # what's installed, and what each tool unlocks
showrig new films/launch             # the wizard
showrig draft films/launch           # optional: local model suggests missing narration
showrig make films/launch --draft    # fast first look
showrig make films/launch            # final quality; only changed pieces rebuild
```

Try the bundled example, which records two web pages and needs no footage of your own:

```sh
showrig new films/demo --answers examples/demo/answers.json
showrig make films/demo --draft
```

## A film folder

```
films/launch/
  showrig.json     the storyboard: every wizard answer; edit it by hand any time
  STORYBOARD.md    the same, readable, for sign-off
  assets/          your clips, recordings and music
  work/            generated pieces, rebuilt only when their inputs change
  out/             launch.fcproj, launch.mp4, launch.srt, versions/
```

Change a line of narration and `make` re-voices that line and recuts. Swap a clip and only that clip,
the 3D shots showing it, and the edit are redone. Previous FilmCraft projects are kept in
`out/versions/`.

## Post-production

The FilmCraft project is a normal project: open it, change anything, then `showrig render` to export
it again. Post modules work on that project in place, so hand edits survive:

```sh
showrig credits films/launch --line "Directed by=Your Name" --line "Music=Showrig score"
showrig render films/launch
```

## Storyboard reference

```jsonc
{
  "title": "Launch",
  "kind": "showreel",                       // showreel | demo | explainer | trailer
  "format": {"width": 1920, "height": 1080, "fps": 60},
  "style": {
    "accent": "#46d9b0", "background": "#070b14",
    "titles": "rise",                       // rise | typewriter | none
    "transitions": "cinematic",             // cinematic | simple | cuts
    "pushIn": 6,                            // % slow zoom across each footage shot
    "showcase3d": true,                     // Blender stage
    "quality": "final"                      // final | draft
  },
  "voice": {"source": "tts", "voice": "af_heart", "say": {"OKLCH": "O K L C H"}},   // tts | files | none
  "music": {"source": "procedural", "mood": "bright"},                              // procedural | file | none
  "captions": {"mode": "burn"},                                                     // burn | srt | none
  "scenes": [
    {"kind": "intro", "title": "Launch", "tagline": "...", "lines": ["..."]},
    {"kind": "segment", "title": "Feature", "tagline": "...", "subtitle": "example.com",
     "shots": [{"file": "assets/feature.mp4", "in": 1.5, "weight": 2},
               {"capture": {"url": "https://example.com", "scale": 1.25,
                            "actions": ["wait 1", "type #search showrig", "press Enter", "scroll 1200 5"]}}],
     "lines": ["..."], "note": "Demo data"},
    {"kind": "card", "title": "Chapter two", "lines": ["..."]},
    {"kind": "outro", "title": "Launch", "lines": ["..."]}
  ],
  "credits": {"enabled": false, "lines": [["Directed by", "..."]]}
}
```

With `"voice": {"source": "files"}`, each scene gives one recording per line in `"voice": [...]`; the
lines' text still drives the captions.

## Configuration

Tools are found on `PATH` and in `~/Work/ArtCraft`. Override with `FILMCRAFT_CLI`, `EFFECTCRAFT_CLI`,
`BLENDER`, `NODE`, `SHOWRIG_PLAYWRIGHT`, `SHOWRIG_TTS_PYTHON` (a Python with `kokoro` installed),
`ARTCRAFT_HOME` and `OLLAMA_HOST`.

## Status

0.1, a working prototype. Known limits:

- The 3D showcase is framed for landscape films.
- EffectCraft does not render text-animator range selectors yet, so titles animate whole lines
  (the typewriter style keys the text itself).
- Only one post module so far (credits).

## Extending and checking the studio

Wizard templates and look presets live in `showrig/studio.py`; the browser reads their
catalog rather than keeping a second list. The responsive title renderer is
`showrig/assets/studio-title.jsx`. Existing CLI storyboards keep their original timing
unless they opt into `"timing": "content"`. An optional scene `duration` sets a minimum,
never a cutoff for narration. `style.design` selects the new title treatment.

Run the fast checks with `workspace-quality-gate` or:

```sh
python3 -m unittest discover -s tests
node --check showrig/static/app.js
```

Run real render integration tests with `SHOWRIG_RENDER_TESTS=1 python3 -m unittest tests.test_render -v`.
They create explicitly synthetic fixtures in `/tmp`, exercise three formats, uploads,
recorded audio, captions, failed exports, and cancellation, and print the artifact folder.

For browser verification, start a separate test library with
`showrig web --projects /tmp/showrig-browser-tests/films --no-open`, then run
`node scripts/browser-check.mjs`. It uses the broker reservation, blocks outside
requests, and saves desktop/mobile screenshots in `/tmp/showrig-browser-check`.
It requires locally installed Playwright and Chromium. Set `SHOWRIG_PLAYWRIGHT` if the
package is outside the global npm directory. The browser checks need an execution
environment that permits Chromium and local network connections.

## Credits

Idea author and orchestrator: **Christopher Davis** ([github.com/tweakyourpc](https://github.com/tweakyourpc)).
See [AUTHORS.md](AUTHORS.md). MIT License.
