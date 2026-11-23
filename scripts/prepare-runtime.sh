#!/bin/bash
# User-owned runtime assembled from the Pi's configured, authenticated apt repositories.
# Does not install system packages, run maintainer scripts, or require sudo.
set -euo pipefail
script_dir="$(cd "$(dirname "$0")" && pwd)"
runtime="$HOME/.local/opt/unlocked-tv-runtime"
cache="$HOME/.cache/unlocked-tv-debs"
mkdir -p "$runtime" "$cache"
packages=(python3-pygame python3-evdev mpv cec-utils libegl-mesa0 libgles2 libgbm1 libgl1-mesa-dri fonts-dejavu-core)
apt-get -s --no-install-recommends install "${packages[@]}" > "$cache/plan.txt"
mapfile -t missing < <(awk '/^Inst / {print $2}' "$cache/plan.txt")
echo "Runtime packages to download: ${#missing[@]}"
if ((${#missing[@]})); then
    cd "$cache"
    apt-get download "${missing[@]}"
    for package in ./*.deb; do dpkg-deb -x "$package" "$runtime"; done
fi
cp "$cache/plan.txt" "$runtime/package-plan.txt"
mkdir -p "$HOME/.local/bin"
cp "$script_dir/runtime-env.sh" "$HOME/.local/bin/unlocked-tv-env"
chmod 755 "$HOME/.local/bin/unlocked-tv-env"
"$HOME/.local/bin/unlocked-tv-env" python3 -c 'import pygame, evdev; print("PYGAME", pygame.version.ver); print("NATIVE_RUNTIME_READY")'
"$HOME/.local/bin/unlocked-tv-env" mpv --version | head -3
