# tweakyourpc promo

A Showrig kit for a promo film. It introduces Christopher Davis and six of his projects: Game Night, TextStrata, Vertex City, Wordsmith Studio 2, Temporal Lens and portbroker. Then it shows how the film itself was made: Blender, the ArtCraft apps and AI agents on one PC. It closes with rolling credits and an invitation to the GitHub profile. Everything the build needs is in this folder, and the build runs offline from the terminal.

## Build

```sh
./build.sh --check     # preflight: tools, media, and an offline voice test
./build.sh --draft     # fast first look (half-size Blender renders)
./build.sh             # the real thing: 1920x1080, 30 fps
./build.sh --open      # ...and open the result in FilmCraft
```

The film lands in `../../films/tweakyourpc-promo/`, so it also appears in the Showrig web studio. Rebuilds are incremental: change one scene and only that scene's pieces are made again.

Other switches:

- `--no-voice`: no narration, so Kokoro isn't needed
- `--no-3d`: no Blender
- `--until STAGE`: stop after `footage`, `voice`, `plan`, `titles`, `stage`, `music`, `assemble` or `render`
- `--film DIR`: build somewhere else

On this machine Blender renders on the CPU. The first full-quality build spends most of its time on the eight 3D shots. Later builds reuse them unless the storyboard changes what they show.

## The film, scene by scene

| Scene | What it shows |
|---|---|
| `hello` | The GitHub avatar beside who Christopher is and how he works |
| `intro` | Blender's arc of the six project screens, with the title in the dark band below them |
| six projects | A 3D establishing shot, then the real apps at work, with a short lower-third title |
| `made-here` | Blender, EffectCraft and FilmCraft working on this very film |
| `why-local` | The tool calls behind the build, and TextStrata: why local knowledge made it quick |
| `credits` | A rolling credits list: hardware, tools, AI collaborators, the open-source teams |
| `outro` | The wall of screens, the avatar and github.com/tweakyourpc |

The making-of segments set `showcase: false`, so the 3D arc and wall show only the six projects.

## What the build makes, and where to reuse it

| Piece | Where | Open with |
|---|---|---|
| Finished film | `out/tweakyourpc.mp4` | any player |
| Editable cut | `out/tweakyourpc.fcproj` | FilmCraft: tracks V1 picture, V2 titles, V3 images, A1 voice, A2 music |
| 3D shots | `work/stage/*.mp4` and `*.blend` | FilmCraft clips; reopen the scenes in Blender to restage and re-render |
| Title cards, credits | `work/titles/*.ecproj` and `*.mov` | EffectCraft projects; the `.mov` files carry alpha |
| Footage, voice, score | `work/footage/`, `work/voice/`, `work/music.wav` | anything |

After editing the cut in FilmCraft, save it and export again from the terminal:

```sh
showrig render ../../films/tweakyourpc-promo
```

Keep `work/` with the film: the FilmCraft project points at the clips inside it.

## Editing the film

Everything lives in `storyboard.json`:

- `scenes[].lines`: the narration. Each scene is as long as its words need; `gap` sets the pause between lines.
- `scenes[].title`, `tagline`, `subtitle`: the typewriter titles. `titlePlace: "low"` puts a full-screen title in the lower part of the frame. `image` sets a picture on the left (the avatar on `hello` and `outro`), placed on FilmCraft's V3 track so you can move or swap it there.
- `scenes[].shots`: the pictures for each project. `weight` shares the screen time, `in` starts a clip later, and `hero` picks the shot shown on that project's floating 3D screen.
- `credits.lines`: `["Role", "Name"]` is a pair, `["", "Name"]` is a centred name, and `["Heading"]` starts a section.
- `voice.say`: how Kokoro pronounces names (`tweakyourpc` is read as "tweak your P C").
- `style.titleHold`: how many seconds a project's lower third stays up before the footage plays clean.
- `captions.mode` is `none`. Narration and titles carry the words, and players would otherwise pick up a sidecar `.srt`. Set it to `srt` or `burn` to bring captions back.

The Wordsmith, portbroker and tool-call shots are captured during the build from `pages/`, with every network request blocked. Edit their `actions` (`type`, `click`, `scroll`, `wait`) to change what happens on screen.

## The media

- `media/avatar.png`: the GitHub avatar, cut to a circle with a ring in the film's accent colour.
- `media/*.png`: the projects' README hero images.
- `media/game-night-wordwright.mp4`: Ann plays Wordwright against the computer on Game Night's local test server, with the real ENABLE word list. Her words come from the game's own move search; she places every tile by tapping.
- `media/game-night-play.mp4`: Ann and Sam play Four in a Row from two browsers.
- `media/textstrata-tour.mp4`: a throwaway TextStrata workspace built from its own seed docs.
- `media/vertex-city-live.mp4`: Midtown Manhattan from OpenStreetMap at 42nd and Fifth. It shows local radio, a time-lapse from late afternoon into night and a click on a star.
- `media/vertex-city-flight.mp4`: the offline procedural city in its visual styles. Both Vertex City clips are recorded on a virtual clock, so motion stays smooth without a GPU.
- `media/temporal-lens-live.mp4`: the real extension annotating a demo chat thread (`tools/pages/temporal-lens-chat.html`).
- `media/blender-ui.mp4`, `effectcraft-ui.mp4`, `filmcraft-ui.mp4`: the apps' own windows working on this film. They show the intro's Blender scene, the Game Night title and the FilmCraft edit.
- `pages/wordsmith/`: a copy of Wordsmith Studio 2.
- `pages/portbroker/`: the real portbroker dashboard, fed a saved snapshot from a throwaway registry of sample services.
- `pages/agent-terminal/`: the real commands from this film's build logs, replayed as a terminal session.

## Recording the clips again

```sh
tools/record-apps.sh                  # the app clips (needs the internet once, see below)
tools/record-apps.sh wordwright       # just one
tools/record-ui.py                    # the Blender, EffectCraft and FilmCraft clips (offline)
tools/make-terminal-page.py           # the tool-call page, from the latest build's logs
```

`record-apps.sh` clones the projects into `~/.cache/showrig-promo`. It runs each one locally on a portbroker port and writes new clips into `media/`. The internet is needed for:

- the clones
- the Wordwright word list
- Vertex City's map, which is cached after the first run
- its radio station list

`record-ui.py` and `make-terminal-page.py` read a finished build, so run them after `./build.sh --draft`, then build again.

## Rendering the 3D shots on another computer

The eight Blender shots are the slow part of a full-quality build on a CPU. To render them on a machine with a real GPU:

```sh
./build.sh --draft                    # once, so the plan and the screen videos exist
tools/stage-pack.py export            # writes ../tweakyourpc-stage-pack (jobs, screen videos, stage script)
```

Copy `tweakyourpc-stage-pack/` to the other computer. It needs only Blender 4.x (Linux, Windows or macOS), and EEVEE uses its GPU automatically:

```sh
cd tweakyourpc-stage-pack
blender -b --python render_all.py     # every shot to rendered/<scene>.mp4, plus a reopenable .blend
```

It skips shots that are already rendered, so you can stop it and start it again. Copy the folder back, then:

```sh
tools/stage-pack.py import ../tweakyourpc-stage-pack
./build.sh --open                     # reuses the imported shots; only the edit and final render remain
```

The import refuses any shot that no longer matches the film, for example if the storyboard changed what a screen shows after the export.

## Sharing

```sh
tools/social.sh                       # web copy + thumbnails into ~/Videos/Projects/2026-10-25 tweakyourpc promo
```

It writes `tweakyourpc-promo-web.mp4`: H.264 with the index at the front, about a quarter of the master's size, and fine for LinkedIn, YouTube or a meetup laptop. It also writes three 1280×720 thumbnails: the avatar card, the six-project arc and the closing invite. Re-run it after every build; it only reads the film.
