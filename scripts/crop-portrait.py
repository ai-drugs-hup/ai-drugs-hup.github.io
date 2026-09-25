#!/usr/bin/env python3
"""Crop a portrait to a square framed on the face, then web-size it.

Args: name fx fy side [out]

`name` is either a bare name, meaning resources/images/originals/members/<name>.jpg,
or a path to any image — which is how a single face is lifted out of a group
photograph. fx/fy are the face centre as fractions of the whole image; `side` is
the crop's edge length as a fraction of the image HEIGHT. `out` names the output
file when the source is not named after the person.

The window is clamped inside the image, so a face near an edge shifts the window
rather than producing a short crop.
"""
import pathlib
import subprocess, sys

name, fx, fy, side = sys.argv[1], *map(float, sys.argv[2:5])
# A bare name means the usual place for supplied portraits; a path with a
# separator in it means that exact file, which is how a face is lifted out of a
# group photograph.
src = name if "/" in name else f"resources/images/originals/members/{name}.jpg"
# An optional 5th argument names the output, needed when the source file is
# not named after the person — a group photograph, for instance.
out = sys.argv[5] if len(sys.argv) > 5 else pathlib.Path(name).stem
dst = f"assets/img/team/{out}.jpg"
w, h = map(int, subprocess.run(["identify", "-format", "%w %h", src],
                               capture_output=True, text=True, check=True).stdout.split())
s = min(int(side * h), w, h)
ox = min(max(int(fx * w - s / 2), 0), w - s)
oy = min(max(int(fy * h - s / 2), 0), h - s)
subprocess.run(["convert", src, "-auto-orient", "-crop", f"{s}x{s}+{ox}+{oy}", "+repage",
                "-resize", "480x480", "-strip", "-quality", "82",
                "-interlace", "Plane", dst], check=True)
out = subprocess.run(["identify", "-format", "%wx%h %b", dst],
                     capture_output=True, text=True, check=True).stdout
print(f"{out:<14} src {w}x{h}  window {s}px @ {ox},{oy}  ->  {out}")
