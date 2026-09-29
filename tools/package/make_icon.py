#!/usr/bin/env python3
"""Generate the AutoCellLibX application icon (tools/package/AutoCellLibX.ico).

A dark navy rounded square with a cyan digital waveform trace -- "chip /
signal" at a glance, readable from 16 px up to the 256 px shell size.
"""
import os
from PIL import Image, ImageDraw

PKG = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(PKG, "AutoCellLibX.ico")
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
         (256, 256)]

NAVY_TOP = (13, 27, 46)
NAVY_BOT = (23, 42, 69)
ACCENT = (64, 196, 255)
ACCENT_DIM = (100, 160, 210)
WHITE = (235, 245, 255)


def _round_rect(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _draw(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = max(1, size // 32)
    r = size // 6
    # background with a subtle vertical gradient
    top = Image.new("RGBA", (size, size), NAVY_TOP)
    for y in range(size):
        t = y / max(1, size - 1)
        c = tuple(int(a + (b - a) * t) for a, b in zip(NAVY_TOP, NAVY_BOT))
        d.line([(0, y), (size, y)], fill=c)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [m, m, size - m, size - m], radius=r, fill=255)
    img.paste(top, (0, 0), mask)

    # waveform trace: a stepped digital signal across the face
    s = size
    pts = [(s * 0.10, s * 0.66), (s * 0.10, s * 0.42), (s * 0.30, s * 0.42),
           (s * 0.30, s * 0.66), (s * 0.50, s * 0.66), (s * 0.50, s * 0.30),
           (s * 0.70, s * 0.30), (s * 0.70, s * 0.66), (s * 0.90, s * 0.66)]
    w = max(2, s // 14)
    d.line(pts, fill=ACCENT, width=w, joint="curve")
    # contact/terminal squares at the turning points
    cw = max(3, s // 16)
    for (x, y) in pts:
        d.rounded_rectangle([x - cw / 2, y - cw / 2, x + cw / 2, y + cw / 2],
                            radius=cw / 4, fill=WHITE)
    # small ground rail along the bottom edge
    ry = s * 0.84
    d.line([(s * 0.10, ry), (s * 0.90, ry)], fill=ACCENT_DIM, width=w)
    for x in (s * 0.10, s * 0.30, s * 0.50, s * 0.70, s * 0.90):
        d.line([(x, ry), (x, ry + s * 0.06)], fill=ACCENT_DIM, width=w)
    return img


def main():
    imgs = [_draw(s) for s, _ in SIZES]
    imgs[-1].save(OUT, format="ICO", sizes=SIZES,
                  append_images=imgs[:-1])
    print("icon written: %s (%.1f KB)" % (OUT, os.path.getsize(OUT) / 1024.0))


if __name__ == "__main__":
    main()
