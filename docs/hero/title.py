"""Set the title and screen labels over the rendered hero scene.

python3 title.py <scene.png> <out.jpg> [social.jpg]
  reads <scene.png>.json (each screen's top-left corner, written by hero_scene.py)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = Path("/usr/share/fonts/opentype/inter")
MONO = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
LABELS = [("STORYBOARD", "Showrig studio"), ("TITLES", "EffectCraft"), ("3D STAGE", "Blender"),
          ("EDIT", "FilmCraft"), ("FILM", "MP4 + project")]
COLORS = ["#4fd1a5", "#ff5fae", "#f5a524", "#a78bfa", "#3fd6e0"]


def font(name: str, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), round(size))


def main() -> None:
    scene, out = Path(sys.argv[1]), Path(sys.argv[2])
    img = Image.open(scene).convert("RGB")
    w, h = img.size
    u = w / 2560
    spots = json.loads(Path(f"{scene}.json").read_text())

    # a soft shadow keeps the type clean over the glow
    shade = Image.new("L", img.size, 0)
    ImageDraw.Draw(shade).rectangle((0, 0, w * .62, h * .40), fill=150)
    shade = shade.filter(ImageFilter.GaussianBlur(160 * u))
    img = Image.composite(Image.new("RGB", img.size, "#060c0a"), img, shade)
    d = ImageDraw.Draw(img)

    x = 150 * u
    word = font("InterDisplay-Bold.otf", 176 * u)
    d.text((x, 96 * u), "showrig", font=word, fill="#f4f7f3")
    dot_x = x + d.textlength("showrig", font=word) + 4 * u
    d.text((dot_x, 96 * u), ".", font=word, fill=COLORS[0])
    d.text((x + 6 * u, 330 * u), "Storyboard in. Editable film out.", font=font("Inter-Medium.otf", 64 * u),
           fill="#e4ece6")
    d.text((x + 8 * u, 424 * u),
           "One storyboard drives Blender, EffectCraft, FilmCraft and Kokoro. Offline, on your own machine.",
           font=font("Inter-Regular.otf", 31 * u), fill="#8fa59b")

    small, tool = ImageFont.truetype(str(MONO), round(17 * u)), font("Inter-Medium.otf", 21 * u)
    for (label, name), spot, color in zip(LABELS, spots, COLORS):
        lx, ly = spot["x"] * w + 4 * u, spot["y"] * h - 66 * u
        d.text((lx, ly), label, font=small, fill=color)
        d.text((lx, ly + 24 * u), name, font=tool, fill="#c9d4ce")

    img.save(out, quality=92, optimize=True, progressive=True)
    if len(sys.argv) > 3:  # GitHub's social preview: 1280 x 640, under 1 MB
        img.resize((1280, 640), Image.LANCZOS).save(sys.argv[3], quality=90, optimize=True)


if __name__ == "__main__":
    main()
