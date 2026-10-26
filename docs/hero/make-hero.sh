#!/usr/bin/env bash
# Rebuild the README hero (docs/hero.jpg) and GitHub's social preview (docs/social-preview.jpg).
#
#   docs/hero/make-hero.sh [--draft]
#
# The five screens are docs/hero/screens/1-5*.jpg, storyboard first. Blender sets them on the film
# stage's glowing screens over a reflective floor; title.py adds the type. About a minute, offline.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUALITY=final
[[ ${1:-} == --draft ]] && QUALITY=draft
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

colors=("#4fd1a5" "#ff5fae" "#f5a524" "#8b5cf6" "#3fd6e0")
panels=() i=0
for img in "$HERE"/screens/[1-5]-*.jpg; do
  ffmpeg -v error -y -loop 1 -i "$img" -t 1 -r 30 -vf scale=1920:1080,format=yuv420p -c:v libx264 -crf 12 "$TMP/$i.mp4"
  panels+=("{\"video\": \"$TMP/$i.mp4\", \"color\": \"${colors[$i]}\"}")
  i=$((i + 1))
done
cat > "$TMP/job.json" <<EOF
{"width": 2560, "height": 1280, "quality": "$QUALITY", "background": "#0b1714",
 "cam": [-1.6, -10.6, 1.85], "target": [1.2, 3.0, 2.15], "lens": 33, "fstop": 5.6,
 "near": [3.3, -0.6, 1.25], "step": [-2.15, 3.5, 0], "turn": -14,
 "panels": [$(IFS=,; echo "${panels[*]}")]}
EOF
blender -b -P "$HERE/hero_scene.py" -- "$TMP/job.json" "$TMP/scene.png" > "$TMP/blender.log" 2>&1 \
  || { tail -20 "$TMP/blender.log" >&2; exit 1; }
python3 "$HERE/title.py" "$TMP/scene.png" "$HERE/../hero.jpg" "$HERE/../social-preview.jpg"
echo "wrote docs/hero.jpg and docs/social-preview.jpg"
