#!/usr/bin/env python3
"""Writes config/polybar/blocks.ini: the bar used by every bar style except Flat. Run it after changing an item's
format here:  python3 tools/make_blocks.py
Each item's colours, end glyphs and spacing come from style.ini ([barstyle] <item>-bg, -fg, -ul, -l, -lfg, -lbg,
-r, -rfg, -rbg, -gap), which the settings window writes for the chosen style each time the bar starts."""
import os

mods = [  # (module, [(format-name, format-string)], {extra key: value})
 ("playerctl", [("format", " <label> ")], {"label-foreground": "fg"}),
 # (network, pulseaudio, backlight, battery, cpu, memory: Platform.sh's text, see config.ini)
 ("network", [("format", " <label> ")], {}),
 ("bluetooth", [("format", " <label> ")], {}),
 ("pulseaudio", [("format", " <label> ")], {}),
 ("backlight", [("format", " <label> ")], {}),
 ("caffeine", [("format", " <label> ")], {"label-foreground": "fg"}),
 ("nightlight", [("format", " <label> ")], {"label-foreground": "fg"}),
 ("battery", [("format", " <label> ")], {}),
 ("cpu", [("format", " <label> ")], {}),
 ("memory", [("format", " <label> ")], {}),
 ("gpu", [("format", " <label> ")], {}),
 ("date", [("format", " <label> ")], {"label-foreground": "fg"}),
 ("powermenu", [("format", " %{T2}󰐥%{T-} ")], {}),
]
out = ["; The bar for every style except Flat (Settings > Appearance > Bar style). Each item's colours, end glyphs and",
       "; spacing come from style.ini [barstyle], which the settings window writes for the chosen style when the bar",
       "; starts. Written by tools/make_blocks.py in the repository: change that and run it, rather than editing this.",
       "",
       "[bar/blocks]",
       "inherit = bar/main",
       "module-margin = 0",
       "; the power button's block reaches the screen edge, like the workspace block on the left",
       "padding-right = 0",
       "font-2 = ${env:BAR_CAP_SPEC:FantasqueSansM Nerd Font Mono:size=27.277;5}",
       "modules-left = ${env:BAR_LEFT_B:b-i3}",
       "modules-right = ${env:BAR_RIGHT_B:" + " ".join("b-" + m for m, _f, _e in mods if m not in ("playerctl", "bluetooth")) + "}",
       "",
       "; the workspaces, shaped like the items on the right: separate blocks, or (pill / dark pill / powerline) one",
       "; strip with the block ends on the outside (ws-start / ws-end) and the workspace you are on a block inside it.",
       "; The whole labels (colours and end glyphs as format tags) come from style.ini; space only on the right, so",
       "; the first block meets the screen edge like the power button on the other side.",
       "; (No ${...:fallback}: polybar 3.7 would always use it.)",
       "[module/b-i3]",
       "type = internal/i3",
       "pin-workspaces = true",
       "show-urgent = true",
       "strip-wsnumbers = true",
       "index-sort = true",
       "enable-click = true",
       "enable-scroll = true",
       "wrapping-scroll = false",
       "format = <label-state><label-mode>",
       "format-prefix = ${barstyle.ws-start}",
       "format-suffix = ${barstyle.ws-end}",
       "format-suffix-margin-right = ${barstyle.ws-end-gap}",
       "label-mode = ${barstyle.ws-mode}",
       "label-mode-margin-right = ${barstyle.ws-gap}",
       "label-focused = ${barstyle.ws-focused}",
       "label-focused-underline = ${barstyle.ws-ul}",
       "label-focused-margin-right = ${barstyle.ws-gap}",
       "label-unfocused = ${barstyle.ws-unfocused}",
       "label-unfocused-margin-right = ${barstyle.ws-gap}",
       "label-visible = ${barstyle.ws-visible}",
       "label-visible-margin-right = ${barstyle.ws-gap}",
       "label-urgent = ${barstyle.ws-urgent}",
       "label-urgent-margin-right = ${barstyle.ws-gap}",
       "",
       "; the joined-up styles' workspaces: one strip whose ends are the first and last workspace's own (polybar's",
       "; module cannot tell which one is first or last). launch.sh falls back to b-i3 when python3 cannot run.",
       "[module/b-wsj]",
       "type = custom/script",
       "exec = ~/.config/i3/scripts/PolybarWorkspaces.py",
       "tail = true",
       "interval = 2",
       "format = <label>",
       "label = %output%",
       ""]
for m, fmts, extra in mods:
    k = "${barstyle.%s-%%s}" % m
    bg, fg = k % "bg", k % "fg"
    out.append("[module/b-%s]" % m)
    out.append("inherit = module/%s" % m)
    for name, text in fmts:
        out += ['%s = "%s"' % (name, text),
                "%s-background = %s" % (name, bg),
                "%s-foreground = %s" % (name, fg),
                "%s-underline = %s" % (name, k % "ul"),
                "%s-prefix = %s" % (name, k % "l"),
                "%s-prefix-font = 3" % name,
                "%s-prefix-foreground = %s" % (name, k % "lfg"),
                "%s-prefix-background = %s" % (name, k % "lbg"),
                "%s-suffix = %s" % (name, k % "r"),
                "%s-suffix-font = 3" % name,
                "%s-suffix-foreground = %s" % (name, k % "rfg"),
                "%s-suffix-background = %s" % (name, k % "rbg"),
                "%s-margin = %s" % (name, k % "gap"),
                "%s-offset = %s" % (name, k % "lead")]
    for k, v in extra.items():
        out.append("%s = %s" % (k, fg if v == "fg" else v))
    out.append("")
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "polybar", "blocks.ini"), "w").write("\n".join(out))
print("wrote blocks.ini:", len(out), "lines")
