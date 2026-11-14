# i3 for BSD

Monochrome i3 desktop for **FreeBSD, GhostBSD, OpenBSD and NetBSD**, with a Settings window (`SUPER + ALT + M`) for displays and brightness, power modes (power saver, balanced, performance), the wallpaper (and a wallpaper slideshow), network adapters and addresses, the proxy, the look (rounded corners, a 12- or 24-hour clock) and the keys. The cursor is [Capitaine Cursors](assets/cursors).

## Install

First install bash and git:

| System | Run |
|---|---|
| FreeBSD | `su root -c 'pkg install -y bash git'` |
| GhostBSD | `sudo pkg install -y bash git` |
| OpenBSD | `su root -c 'pkg_add bash git'` |
| NetBSD | `su root -c 'pkgin -y install bash git'` |

Then:

```sh
git clone https://github.com/OmitGhostly/i3-bsd.git
cd i3-bsd
./install.sh
```

Afterwards, log out and pick **i3** at the login screen (GhostBSD: the session menu), or type `startx` on a console. OpenBSD's xenodm and NetBSD's xdm start it through `~/.xsession`, which the installer writes (a file you already have is left alone).

Volume, brightness and battery use the system's own tools (`mixer`, `sndioctl`, `mixerctl`; `backlight`, `xbacklight`, `wsconsctl`; `acpi`, `apm`, `envstat`). NetBSD has no polybar package, so it uses i3's own bar. The Settings window shows your network adapters and addresses and sets the proxy; joining Wi-Fi, VPNs, sound and Bluetooth point to the system's own tools (FreeBSD and GhostBSD: NetworkMgr in the tray). Touchpad swipes need Touchégg, which only runs on Linux.

Power modes (Settings > Power) use powerd on FreeBSD and GhostBSD and `hw.perfpolicy` on OpenBSD; changing them needs a doas or sudo rule that lets you run `sysrc` and `service` (FreeBSD) or `sysctl` (OpenBSD) without a password. NetBSD has no such setting.

To shut down or sleep from the power menu, join the `operator` group (FreeBSD, NetBSD) or add a doas rule such as `permit nopass :wheel cmd shutdown`.

The terminal is Ghostty where your system packages it, else kitty. The file manager is [yazi](https://yazi-rs.github.io) where it is packaged, opened in the terminal; Thunar stays installed, and Settings > Keybindings switches between them.

## Updates

A line in your crontab looks every 30 minutes whether packages were installed or updated (`pkg`, `pkg_add`, `pkgin`); then you get a notification when a newer version of this config is on GitHub. Nothing changes until you install it:

```sh
i3dots-update
```

What you set in the Settings window is kept. Files you edited by hand in `~/.config` (the Ghostty config, the i3 config...) are replaced, and `i3dots-update --undo` puts back the version from before. Your own Ghostty settings belong in `~/.config/ghostty-local.conf`: Ghostty reads it last, and updates never touch it.

| Command | Does |
|---|---|
| `i3dots-update --check` | only say whether there is a newer version |
| `i3dots-update --status` | the installed version, and a newer one if there is |
| `i3dots-update --undo` | go back to the config from before the last update |
| `i3dots-update --off` / `--on` | no more checks / checks again |

## Uninstall

```sh
./uninstall.sh
```

| Option | Does |
|---|---|
| `--yes` | no questions: config, i3 and added programs |
| `--config-only` | config only, keep i3 and programs |
| `--all-programs` | also offer programs you already had |
| `--no-restore` | don't restore your old configs |
| `--force` | remove i3 even if it's your only desktop |
| `--dry-run` | show, change nothing |

## Keybinds

`SUPER` = Windows key. `SUPER + H` shows this list.

### Apps

| Key | Action |
|---|---|
| `SUPER + D` | App launcher (rofi) |
| `SUPER + Enter` | Open terminal |
| `SUPER + E` | File manager (yazi, in the terminal) |
| `SUPER + B` | Open default browser |
| `SUPER + C` | SSH session manager |
| `SUPER + H` | Help / cheat sheet |
| `SUPER + SHIFT + K` | Search keybinds |
| `SUPER + S` | Web search |
| `SUPER + A` | Window switcher (overview replacement) |
| `SUPER + CTRL + S` | Window switcher |
| `SUPER + ALT + E` | Emoji menu |
| `SUPER + ALT + C` | Calculator |
| `SUPER + ALT + V` | Clipboard manager |
| `SUPER + SHIFT + M` | Online music |
| `SUPER + SHIFT + E` | Quick settings menu |
| `SUPER + CTRL + R` | Rofi theme selector |
| `SUPER + CTRL + SHIFT + R` | Rofi theme selector (modified) |
| `SUPER + CTRL + K` | Kitty theme selector |
| `SUPER + SHIFT + O` | Change oh-my-zsh theme |
| `SUPER + ALT + R` | Refresh bar, colors, menus |
| `SUPER + SHIFT + Enter` | Drop-down terminal |
| `SUPER + ALT + D` | Display layout tool (arandr) |
| `SUPER + ALT + M` | Settings window (network: Wi-Fi, Ethernet, IP and DNS, VPN, proxy; Bluetooth, sound, displays and brightness, appearance, colors, themes, mouse and cursor, keybinds) |

### Look

| Key | Action |
|---|---|
| `SUPER + W` | Select wallpaper |
| `CTRL + ALT + W` | Random wallpaper |
| `SUPER + ALT + O` | Toggle compositor (blur/rounding/shadows) |
| `SUPER + CTRL + O` | Toggle active window opacity |
| `SUPER + SHIFT + G` | Toggle game mode |
| `SUPER + N` | Toggle night light |
| `SUPER + CTRL + ALT + B` | Toggle bar on/off |
| `SUPER + SHIFT + N` | Notification history |

### Session

| Key | Action |
|---|---|
| `SUPER + Q` | Close active window |
| `SUPER + SHIFT + Q` | Terminate active process |
| `CTRL + ALT + L` | Lock screen |
| `CTRL + ALT + P` | Power menu |
| `CTRL + ALT + Delete` | Exit / power menu |
| `SUPER + SHIFT + C` | Reload i3 config |
| `SUPER + SHIFT + R` | Restart i3 in place |

### Screenshots

| Key | Action |
|---|---|
| `SUPER + Print` | Screenshot now |
| `SUPER + SHIFT + Print` | Screenshot (area) |
| `SUPER + CTRL + Print` | Screenshot in 5s |
| `SUPER + CTRL + SHIFT + Print` | Screenshot in 10s |
| `ALT + Print` | Screenshot active window |
| `SUPER + SHIFT + S` | Screenshot + annotate |
| `SUPER + F6` | Screenshot now (F6) |
| `SUPER + SHIFT + F6` | Screenshot area (F6) |
| `SUPER + CTRL + F6` | Screenshot in 5s (F6) |
| `SUPER + ALT + F6` | Screenshot in 10s (F6) |
| `ALT + F6` | Screenshot active window (F6) |
| `ALT + SHIFT + S` | Region screenshot |

### Windows

| Key | Action |
|---|---|
| `SUPER + SHIFT + F` | Fullscreen |
| `SUPER + F` | Fullscreen (maximize) |
| `SUPER + Space` | Toggle floating |
| `SUPER + CTRL + Space` | Floating: standard size, centered |
| `SUPER + ALT + L` | Toggle layout (split/tabbed/stacking) |
| `SUPER + ALT + 1` | Layout: side by side (the normal split layout) |
| `SUPER + ALT + 2` | Layout: stacking |
| `SUPER + ALT + 3` | Layout: tabbed (monocle-like) |
| `SUPER + G` | Toggle group (tabbed/split) |
| `SUPER + SHIFT + I` | Toggle split direction |
| `SUPER + ALT + T` | Toggle spiral tiling like Hyprland (on) / classic side by side (off) |
| `SUPER + CTRL + H` | Focus parent container (group) |
| `SUPER + CTRL + J` | Focus child container |
| `SUPER + \` | Split next window horizontally |
| `SUPER + -` | Split next window vertically |
| `SUPER + SHIFT + T` | Toggle sticky |
| `SUPER + SHIFT + Space` | Focus: switch tiling/floating |
| `SUPER + J` | Focus next |
| `SUPER + K` | Focus previous |
| `ALT + Tab` | Focus next (alt-tab) |
| `ALT + SHIFT + Tab` | Focus previous (alt-shift-tab) |
| `SUPER + ←` | Focus left |
| `SUPER + ↓` | Focus down |
| `SUPER + ↑` | Focus up |
| `SUPER + →` | Focus right |
| `SUPER + CTRL + ←` | Move window left |
| `SUPER + CTRL + ↓` | Move window down |
| `SUPER + CTRL + ↑` | Move window up |
| `SUPER + CTRL + →` | Move window right |
| `SUPER + SHIFT + ←` | Resize: narrower |
| `SUPER + SHIFT + →` | Resize: wider |
| `SUPER + SHIFT + ↑` | Resize: shorter |
| `SUPER + SHIFT + ↓` | Resize: taller |
| `SUPER + SHIFT + U` | Move to scratchpad (special workspace) |
| `SUPER + U` | Toggle scratchpad (special workspace) |

### Workspaces

| Key | Action |
|---|---|
| `SUPER + 1 … 0` | Workspace 1 - 10 |
| `SUPER + SHIFT + 1 … 0` | Move to workspace 1 - 10 (follow) |
| `SUPER + CTRL + 1 … 0` | Move silently to workspace 1 - 10 |
| `SUPER + Tab` | Next workspace |
| `SUPER + SHIFT + Tab` | Previous workspace |
| `SUPER + .` | Next workspace (.) |
| `SUPER + ,` | Previous workspace (,) |
| `SUPER + scroll down` | Next workspace (scroll) |
| `SUPER + scroll up` | Previous workspace (scroll) |
| `SUPER + SHIFT + ]` | Move to next workspace (follow) |
| `SUPER + SHIFT + [` | Move to previous workspace (follow) |
| `SUPER + CTRL + ]` | Move silently to next workspace |
| `SUPER + CTRL + [` | Move silently to previous workspace |
| `SUPER + CTRL + F9` | Workspace to left monitor |
| `SUPER + CTRL + F10` | Workspace to right monitor |
| `SUPER + CTRL + F11` | Workspace to upper monitor |
| `SUPER + CTRL + F12` | Workspace to lower monitor |

### Media

| Key | Action |
|---|---|
| `Volume up key` | Volume up |
| `Volume down key` | Volume down |
| `ALT + Volume up key` | Volume up (precise) |
| `ALT + Volume down key` | Volume down (precise) |
| `Mute key` | Toggle mute |
| `Mic mute key` | Toggle mic mute |
| `Play key` | Play/pause |
| `Pause key` | Pause |
| `Next track key` | Next track |
| `Previous track key` | Previous track |
| `Stop key` | Stop |
| `Brightness up key` | Brightness up |
| `Brightness down key` | Brightness down |
| `CTRL + ALT + =` | Brightness up (kbd) |
| `CTRL + ALT + -` | Brightness down (kbd) |
| `CTRL + ALT + Numpad +` | Brightness up (numpad) |
| `CTRL + ALT + Numpad -` | Brightness down (numpad) |
| `Keyboard light up key` | Keyboard backlight up |
| `Keyboard light down key` | Keyboard backlight down |
| `Keyboard light key` | Keyboard backlight cycle |
| `Touchpad key` | Toggle touchpad |
| `Wi-Fi key` | Airplane mode |
| `Airplane key` | Airplane mode (rfkill key) |
| `Sleep key` | Sleep |

## Files

| Repo | Installed to | What |
|---|---|---|
| `config/i3/` | `~/.config/i3/` | i3, scripts, Settings |
| `config/polybar/` | `~/.config/polybar/` | bar |
| `config/picom/` | `~/.config/picom/` | compositor |
| `config/dunst/` | `~/.config/dunst/` | notifications |
| `config/ghostty/` | `~/.config/ghostty/` | terminal |
| `config/kitty/` | `~/.config/kitty/` | terminal |
| `config/yazi/` | `~/.config/yazi/` | file manager colours |
| `config/fastfetch/` | `~/.config/fastfetch/` | greeting |
| `config/cava/` | `~/.config/cava/` | visualiser |
| `config/touchegg/` | `~/.config/touchegg/` | gestures |
| `config/swappy/` | `~/.config/swappy/` | screenshot editor |
| `config/gtk-3.0/` | `~/.config/gtk-3.0/` | dark GTK |
| `wallpapers/` | `~/Pictures/wallpapers/` | wallpapers |
| `assets/cursors/` | `~/.local/share/icons/capitaine-cursors` | cursor (LGPL-3.0) |
| `uninstall.sh` | `~/.local/bin/i3dots-uninstall` | uninstaller |
| `tools/` | - | dev tools |

GPL-3.0 · based on [Hyprland-Dots](https://github.com/LinuxBeginnings/Hyprland-Dots)
