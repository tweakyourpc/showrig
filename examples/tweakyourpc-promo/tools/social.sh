#!/usr/bin/env bash
# Make sharing copies of the finished film: a web-sized MP4 and three thumbnails.
#
#   tools/social.sh [OUT_DIR] [FILM_MP4]
#     OUT_DIR   default: ~/Videos/Projects/2026-10-25 tweakyourpc promo (the library folder)
#     FILM_MP4  default: <showrig>/films/tweakyourpc-promo/out/tweakyourpc.mp4
#
# The web copy is H.264 (CRF 23) with 160k AAC and the index up front, so it starts playing while it
# uploads or streams: about a quarter of the master's size, well under LinkedIn's 5 GB / 10 minute
# limit. Thumbnails are 1280x720 frames: the avatar card, the six-project arc and the closing invite.
# Runs at low priority, reads the film only, and works offline. Re-run it after a new build.
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$HOME/Videos/Projects/2026-10-25 tweakyourpc promo}"
FILM="${2:-$(cd "$KIT/../.." && pwd)/films/tweakyourpc-promo/out/tweakyourpc.mp4}"
[[ -f "$FILM" ]] || { echo "film not found: $FILM (run ./build.sh first)" >&2; exit 1; }
mkdir -p "$OUT"

WEB="$OUT/tweakyourpc-promo-web.mp4"
echo "web copy → $WEB"
nice -n 19 ffmpeg -v error -stats -y -i "$FILM" -c:v libx264 -profile:v high -preset slow -crf 23 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -movflags +faststart "$WEB"

# name, time (s): settled moments, away from transitions
for shot in hello:6 six-projects:29 ending:265; do
  name="${shot%%:*}" at="${shot##*:}"
  nice -n 19 ffmpeg -v error -y -ss "$at" -i "$FILM" -frames:v 1 -vf scale=1280:720:flags=lanczos -q:v 2 \
    "$OUT/thumbnail-$name.jpg"
done

size() { du -h "$1" | cut -f1; }
echo "done: $(size "$WEB") web copy (master $(size "$FILM")), thumbnails in $OUT"
