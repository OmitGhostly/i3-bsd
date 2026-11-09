#!/usr/bin/env python3
"""Draws the notification icons (volume, microphone, brightness) in config/i3/icons/: plain white shapes on a
transparent background, 256x256 - the same look as dunst's other icons here. Needs python3-cairo (pycairo).

  python3 tools/make_icons.py            writes the PNGs next to the other icons
"""
import math
import os
import sys

import cairo

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "i3", "icons")
SIZE = 256


def canvas():
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, SIZE, SIZE)
    cr = cairo.Context(surf)
    cr.set_source_rgb(1, 1, 1)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    return surf, cr


def speaker(cr, dx=0):
    """The speaker: a box with a cone. dx slides it sideways (to make room for the waves or the cross)."""
    cr.move_to(34 + dx, 100)
    cr.line_to(78 + dx, 100)
    cr.line_to(124 + dx, 60)
    cr.line_to(124 + dx, 196)
    cr.line_to(78 + dx, 156)
    cr.line_to(34 + dx, 156)
    cr.close_path()
    cr.set_line_width(14)
    cr.fill_preserve()
    cr.stroke()


def wave(cr, radius, dx=0):
    cr.set_line_width(15)
    cr.arc(124 + dx, 128, radius, -math.radians(42), math.radians(42))
    cr.stroke()


def volume(waves):
    surf, cr = canvas()
    speaker(cr)
    for r in (50, 86)[:waves]:
        wave(cr, r)
    return surf


def volume_mute():
    surf, cr = canvas()
    speaker(cr)
    cr.set_line_width(15)
    for a, b in (((166, 98), (222, 158)), ((222, 98), (166, 158))):
        cr.move_to(*a)
        cr.line_to(*b)
        cr.stroke()
    return surf


def microphone(muted):
    surf, cr = canvas()
    cr.set_line_width(14)
    cr.arc(128, 80, 30, math.pi, 0)                    # the capsule
    cr.line_to(158, 120)
    cr.arc(128, 120, 30, 0, math.pi)
    cr.close_path()
    cr.fill_preserve()
    cr.stroke()
    cr.arc(128, 120, 56, 0, math.pi)                   # the holder
    cr.stroke()
    cr.move_to(128, 176)
    cr.line_to(128, 214)
    cr.move_to(94, 214)
    cr.line_to(162, 214)
    cr.stroke()
    if muted:                                          # a slash with a gap around it
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.set_line_width(38)
        cr.move_to(50, 40)
        cr.line_to(210, 216)
        cr.stroke()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_line_width(15)
        cr.move_to(50, 40)
        cr.line_to(210, 216)
        cr.stroke()
    return surf


def brightness(level):
    """A sun: eight rays and a circle that is filled up to `level` percent."""
    surf, cr = canvas()
    cr.set_line_width(14)
    for i in range(8):
        a = math.radians(45 * i)
        cr.move_to(128 + 68 * math.cos(a), 128 + 68 * math.sin(a))
        cr.line_to(128 + 98 * math.cos(a), 128 + 98 * math.sin(a))
        cr.stroke()
    cr.set_line_width(13)
    cr.arc(128, 128, 40, 0, 2 * math.pi)
    cr.stroke()
    if level >= 100:
        cr.arc(128, 128, 40, 0, 2 * math.pi)
        cr.fill()
    else:
        cr.save()
        cr.arc(128, 128, 40, 0, 2 * math.pi)
        cr.clip()
        top = 168 - 80 * level / 100.0
        cr.rectangle(80, top, 96, 200 - top)
        cr.fill()
        cr.restore()
    return surf


ICONS = {"volume-low": lambda: volume(0), "volume-mid": lambda: volume(1), "volume-high": lambda: volume(2),
         "volume-mute": volume_mute, "microphone": lambda: microphone(False),
         "microphone-mute": lambda: microphone(True)}
for pct in (20, 40, 60, 80, 100):
    ICONS["brightness-%d" % pct] = (lambda p=pct: brightness(p))


def main():
    for name, draw in ICONS.items():
        path = os.path.join(OUT, name + ".png")
        draw().write_to_png(path)
        print("wrote", os.path.normpath(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
