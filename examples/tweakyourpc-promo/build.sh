#!/usr/bin/env bash
# Build the tweakyourpc promo with Showrig, entirely offline.
#
#   ./build.sh                 full-quality 1080p film (Blender 3D, voice, music, titles, captions)
#   ./build.sh --draft         fast first look: half-size Blender renders
#   ./build.sh --no-voice      text only: no Kokoro narration (captions keep the script)
#   ./build.sh --no-3d         skip Blender: moving gradient backdrops instead of the 3D stage
#   ./build.sh --until plan    stop after a stage: footage voice plan titles stage music assemble render
#   ./build.sh --film DIR      build somewhere else (default: <showrig>/films/tweakyourpc-promo)
#   ./build.sh --open          open the finished FilmCraft project when done
#   ./build.sh --check         preflight only: tools, media, voice
#
# Rebuilding is incremental: unchanged footage, voice, titles, and Blender shots are reused.
# Nothing here downloads anything. Media lives in media/ and pages/; refresh the recorded app
# clips (online, optional) with tools/record-apps.sh.
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHOWRIG_ROOT="$(cd "$KIT/../.." && pwd)"
FILM="$SHOWRIG_ROOT/films/tweakyourpc-promo"
DRAFT=0 VOICE=1 THREE_D=1 OPEN=0 CHECK_ONLY=0 UNTIL=render

while [[ $# -gt 0 ]]; do
  case "$1" in
    --draft) DRAFT=1 ;;
    --no-voice) VOICE=0 ;;
    --no-3d) THREE_D=0 ;;
    --open) OPEN=1 ;;
    --check) CHECK_ONLY=1 ;;
    --until) UNTIL="${2:?--until needs a stage}"; shift ;;
    --film) FILM="$(realpath -m "${2:?--film needs a directory}")"; shift ;;
    -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
ok() { printf '  \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '  \033[33mnote\033[0m  %s\n' "$*"; }
fail() { printf '  \033[31mmissing\033[0m %s\n' "$*"; FAILED=1; }

# Everything below runs without a network. These make sure nothing even tries.
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 PYTHONUNBUFFERED=1

if command -v showrig >/dev/null 2>&1 && showrig --version >/dev/null 2>&1; then
  SHOWRIG=(showrig)
else
  SHOWRIG=(python3 -m showrig)
  export PYTHONPATH="$SHOWRIG_ROOT${PYTHONPATH:+:$PYTHONPATH}"
fi

bold "Preflight"
FAILED=0
TOOLS="$(cd "$SHOWRIG_ROOT" && python3 - <<'EOF'
from showrig import tools
for name, found in (("ffmpeg", tools._first("ffmpeg")), ("ffprobe", tools._first("ffprobe")),
                    ("filmcraft", tools.filmcraft()), ("effectcraft", tools.effectcraft()),
                    ("blender", tools.blender()), ("node", tools.node()), ("playwright", tools.playwright()),
                    ("tts", tools.tts_python())):
    print(f"{name}={found or ''}")
EOF
)"
tool() { sed -n "s/^$1=//p" <<<"$TOOLS"; }
for t in ffmpeg ffprobe filmcraft effectcraft; do
  [[ -n "$(tool $t)" ]] && ok "$t  $(tool $t)" || fail "$t (required)"
done
[[ -n "$(tool node)" && -n "$(tool playwright)" ]] && ok "node + Playwright  (offline page captures)" \
  || fail "node + Playwright (required for the Wordsmith and portbroker captures)"
if [[ $THREE_D == 1 ]]; then
  if [[ -n "$(tool blender)" ]]; then ok "blender  $(tool blender)"
  else warn "Blender not found: building with --no-3d"; THREE_D=0; fi
fi

if [[ $VOICE == 1 ]]; then
  VOICE_NAME="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['voice']['voice'])" "$KIT/storyboard.json")"
  if [[ -z "$(tool tts)" ]]; then
    warn "Kokoro is not installed: building without narration (captions keep every line)"; VOICE=0
  elif "$(tool tts)" "$SHOWRIG_ROOT/showrig/assets/tts_kokoro.py" --check "$VOICE_NAME" >/dev/null 2>&1; then
    ok "Kokoro voice $VOICE_NAME  (offline synthesis check passed)"
  else
    warn "Kokoro could not speak $VOICE_NAME offline: building without narration"; VOICE=0
  fi
fi

MISSING_MEDIA="$(python3 - "$KIT/storyboard.json" <<'EOF'
import json, sys
from pathlib import Path
kit = Path(sys.argv[1]).parent
board = json.loads(Path(sys.argv[1]).read_text())
for scene in board["scenes"]:
    paths = [shot.get("file") or shot.get("capture", {}).get("url") for shot in scene.get("shots", [])]
    for path in paths + ([scene["image"]["file"]] if scene.get("image") else []):
        if not (kit / path).is_file():
            print(f"{scene['id']}: {path}")
EOF
)"
if [[ -n "$MISSING_MEDIA" ]]; then
  while read -r line; do fail "media $line"; done <<<"$MISSING_MEDIA"
  echo "        Re-record app clips with tools/record-apps.sh (needs the internet once, to clone the projects)."
else
  ok "media  $(ls "$KIT/media" | wc -l) files in media/, captures in pages/"
fi

if [[ $FAILED == 1 ]]; then echo; echo "Preflight failed. Run 'showrig doctor' for install hints." >&2; exit 1; fi
[[ $CHECK_ONLY == 1 ]] && { echo; bold "Ready to build."; exit 0; }

echo
bold "Storyboard → $FILM"
mkdir -p "$(dirname "$FILM")"
(cd "$SHOWRIG_ROOT" && python3 - "$KIT/storyboard.json" "$FILM" "$VOICE" "$THREE_D" <<'EOF'
import sys
from pathlib import Path
from showrig.cli import answers
from showrig.wizard import create
storyboard, film, voice, three_d = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] == "1", sys.argv[4] == "1"
board = answers(storyboard)            # media paths become absolute, so the film folder can live anywhere
if not voice:
    board["voice"]["source"] = "none"
board["style"]["showcase3d"] = three_d
create(film, board, force=True)
EOF
) | sed 's/^/  /'

MODE="final quality"
ARGS=(make "$FILM" --until "$UNTIL")
[[ $DRAFT == 1 ]] && { ARGS+=(--draft); MODE="draft"; }
echo
bold "Building ($MODE$([[ $VOICE == 0 ]] && echo ', no narration')$([[ $THREE_D == 0 ]] && echo ', no 3D'))"
[[ $THREE_D == 1 && $DRAFT == 0 ]] && echo "  Blender renders on the CPU here; a full-quality first build takes a while. Later builds reuse every unchanged shot."
LOG="$FILM/build.log"
START=$SECONDS
set +e
"${SHOWRIG[@]}" "${ARGS[@]}" 2>&1 | tee "$LOG"
STATUS=${PIPESTATUS[0]}
set -e
if [[ $STATUS != 0 ]]; then
  echo; echo "Build failed after $(( (SECONDS - START) / 60 ))m. Full log: $LOG" >&2
  echo "Fix the problem and run ./build.sh again; finished stages are reused." >&2
  exit "$STATUS"
fi

NAME="$(cd "$SHOWRIG_ROOT" && python3 -c 'import sys; from pathlib import Path; from showrig.project import Film
print(Film.load(Path(sys.argv[1])).name)' "$FILM")"  # outputs are named after the film's title
echo
bold "Done in $(( (SECONDS - START) / 60 ))m $(( (SECONDS - START) % 60 ))s"
if [[ $UNTIL == render ]]; then
  echo "  Film:       $FILM/out/$NAME.mp4"
fi
[[ -f "$FILM/out/$NAME.fcproj" ]] && echo "  FilmCraft:  $FILM/out/$NAME.fcproj   (editable timeline: V1 picture, V2 titles, V3 images, A1 voice, A2 music)"
[[ -f "$FILM/out/$NAME.srt" ]] && echo "  Captions:   $FILM/out/$NAME.srt"
shopt -s nullglob
blends=("$FILM"/work/stage/*.blend) stage=("$FILM"/work/stage/*.mp4) titles=("$FILM"/work/titles/*.ecproj)
(( ${#stage[@]} )) && echo "  Blender:    ${#stage[@]} rendered shots in work/stage/ (.mp4), ${#blends[@]} reopenable scenes (.blend)"
(( ${#titles[@]} )) && echo "  Titles:     ${#titles[@]} EffectCraft projects in work/titles/ (.ecproj, rendered .mov with alpha)"
echo "  Pieces:     work/footage/ (normalized clips)  work/voice/ (narration)  work/music.wav (score)"
echo
echo "  Edit the cut in FilmCraft, save, then re-export from the terminal:"
echo "    ${SHOWRIG[*]} render \"$FILM\""
echo "  Change words, timing, or shots in $KIT/storyboard.json and run ./build.sh again."

if [[ $OPEN == 1 && -f "$FILM/out/$NAME.fcproj" ]]; then
  APP="${FILMCRAFT_APP:-$(ls -t "$HOME"/Applications/filmcraft-*.AppImage 2>/dev/null | head -1)}"
  if [[ -n "$APP" ]]; then nohup "$APP" "$FILM/out/$NAME.fcproj" >/dev/null 2>&1 &
  else xdg-open "$FILM/out/$NAME.fcproj" >/dev/null 2>&1 & fi
fi
