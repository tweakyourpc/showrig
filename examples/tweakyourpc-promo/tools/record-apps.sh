#!/usr/bin/env bash
# Re-record the promo's app clips into ../media/. Optional: the clips already ship with the kit.
#
#   tools/record-apps.sh                      every clip
#   tools/record-apps.sh vertex-city textstrata   just these
#
# Clones (or updates) the projects into ~/.cache/showrig-promo/repos. That, the ENABLE word list,
# OpenStreetMap (cached after the first run) and Radio Browser are the only steps that need the
# internet. Every app then runs locally on a portbroker port with throwaway data:
#   game-night        the local test server (real game code, in-memory storage); two players, Four in a Row
#   wordwright        the same server with the ENABLE word list; Ann against the computer
#   textstrata        a fresh workspace built from TextStrata's own seed docs
#   vertex-city       the offline procedural city, frame-stepped (about 15 minutes on a CPU)
#   vertex-city-live  Midtown Manhattan from OpenStreetMap: local radio, a time-lapse into night
#   vertex-city-stars the same corner after dark: up over the roofs to click a star
#   temporal-lens     the real unpacked extension, annotating tools/pages/temporal-lens-chat.html
#
# The "made on this PC" clips (Blender, EffectCraft, FilmCraft) come from tools/record-ui.py instead.
set -euo pipefail

TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEDIA="$(cd "$TOOLS/../media" && pwd)"
CACHE="${PROMO_CACHE:-$HOME/.cache/showrig-promo}"
REPOS="$CACHE/repos"
CLIPS=("$@")
[[ ${#CLIPS[@]} -eq 0 ]] && CLIPS=(game-night wordwright textstrata vertex-city vertex-city-live vertex-city-stars temporal-lens)
declare -A OUT=([game-night]=game-night-play.mp4 [wordwright]=game-night-wordwright.mp4 [textstrata]=textstrata-tour.mp4
                [vertex-city]=vertex-city-flight.mp4 [vertex-city-live]=vertex-city-live.mp4 [vertex-city-stars]=vertex-city-stars.mp4
                [temporal-lens]=temporal-lens-live.mp4)
declare -A REPO=([game-night]=game-night [wordwright]=game-night [textstrata]=textstrata [vertex-city]=vertex-city
                 [vertex-city-live]=vertex-city [vertex-city-stars]=vertex-city [temporal-lens]=temporal-lens)
for clip in "${CLIPS[@]}"; do [[ -n "${OUT[$clip]:-}" ]] || { echo "unknown clip: $clip" >&2; exit 2; }; done

PIDS=()
cleanup() { for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT

port() { portbroker get --name "$1" 2>/dev/null || portbroker alloc --name "$1"; }
wait_for() {
  for _ in $(seq 100); do curl -fs --max-time 1 "$1/whoami" >/dev/null 2>&1 && return 0; sleep 0.2; done
  echo "server did not start: $1 (log: $CACHE/$2.log)" >&2; exit 1
}
fetch() {
  mkdir -p "$REPOS"
  if [[ -d "$REPOS/$1/.git" ]]; then git -C "$REPOS/$1" pull -q --ff-only || echo "  (offline? using the existing $1 clone)"
  else git clone -q --depth 1 "https://github.com/tweakyourpc/$1.git" "$REPOS/$1"; fi
}

for clip in "${CLIPS[@]}"; do
  echo "== $clip"
  fetch "${REPO[$clip]}"
  dir="$REPOS/${REPO[$clip]}"
  case "$clip" in
    game-night)
      PORT="$(port promo-game-night)"
      (cd "$dir" && exec node tools/dev_server.js --port "$PORT") >"$CACHE/$clip.log" 2>&1 & PIDS+=($!)
      URL="http://127.0.0.1:$PORT/"; wait_for "${URL%/}" "$clip"
      node "$TOOLS/record-apps.mjs" game-night --url "$URL" --out "$MEDIA/${OUT[$clip]}" ;;
    wordwright)
      WORDS="$CACHE/words/enable1.txt"
      [[ -s "$WORDS" ]] || { mkdir -p "$CACHE/words"
        curl -fsSL -o "$WORDS" https://raw.githubusercontent.com/dolph/dictionary/master/enable1.txt; }
      PORT="$(port promo-game-night)"
      (cd "$dir" && exec node tools/dev_server.js --port "$PORT" --words "$WORDS") >"$CACHE/$clip.log" 2>&1 & PIDS+=($!)
      URL="http://localhost:$PORT/"; wait_for "http://127.0.0.1:$PORT" "$clip"
      node "$TOOLS/record-apps.mjs" wordwright --url "$URL" --repo "$dir" --words "$WORDS" --out "$MEDIA/${OUT[$clip]}" ;;
    textstrata)
      PORT="$(port promo-textstrata)"
      store="$(mktemp -d "$CACHE/textstrata-store.XXXX")"
      (cd "$dir" && PYTHONPATH=src python3 -m textstrata --workspace "$store" init >/dev/null
       for f in seed/*.md docs/deterministic-acquisition.md docs/modular-architecture.md docs/wiki-links-and-renames.md docs/control-plane.md; do
         PYTHONPATH=src python3 -m textstrata --workspace "$store" ingest "$f" >/dev/null
       done)
      (cd "$dir" && PYTHONPATH=src TEXTSTRATA_HOST=127.0.0.1 TEXTSTRATA_PORT="$PORT" exec python3 -m textstrata --workspace "$store" web) \
        >"$CACHE/$clip.log" 2>&1 & PIDS+=($!)
      URL="http://127.0.0.1:$PORT/"; wait_for "${URL%/}" "$clip"
      node "$TOOLS/record-apps.mjs" textstrata --url "$URL" --out "$MEDIA/${OUT[$clip]}"
      cleanup; rm -rf "$store" ;;
    vertex-city|vertex-city-live|vertex-city-stars)
      PORT="$(port promo-vertex-city)"
      (cd "$dir" && PORT="$PORT" HOST=127.0.0.1 exec node dev-server.mjs) >"$CACHE/$clip.log" 2>&1 & PIDS+=($!)
      URL="http://127.0.0.1:$PORT/"; wait_for "${URL%/}" "$clip"
      node "$TOOLS/record-apps.mjs" "$clip" --url "$URL" --out "$MEDIA/${OUT[$clip]}" ;;
    temporal-lens)
      PORT="$(port promo-temporal-lens-chat)"
      (cd "$TOOLS/pages" && exec python3 -m http.server "$PORT" --bind 127.0.0.1) >"$CACHE/$clip.log" 2>&1 & PIDS+=($!)
      for _ in $(seq 50); do curl -fs --max-time 1 "http://127.0.0.1:$PORT/" >/dev/null && break; sleep 0.2; done
      node "$TOOLS/record-apps.mjs" temporal-lens --url "http://127.0.0.1:$PORT/temporal-lens-chat.html" \
        --extension "$dir" --out "$MEDIA/${OUT[$clip]}" ;;
  esac
  cleanup; PIDS=()
done
echo "Clips written to $MEDIA. Run ./build.sh to rebuild the film; only changed shots are redone."
