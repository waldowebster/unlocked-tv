#!/bin/bash
set -euo pipefail
base="$HOME/.local/opt/unlocked-tv"
previous="$(cat "$base/previous-release")"
case "$previous" in releases/*) ;; *) echo 'Invalid previous release'; exit 1;; esac
[ -d "$base/$previous" ] || { echo 'Previous release unavailable'; exit 1; }
current="$(readlink "$base/current")"
ln -s "$previous" "$base/current.rollback"
mv -Tf "$base/current.rollback" "$base/current"
printf '%s\n' "$current" > "$base/previous-release"
systemctl --user restart unlocked-tv.service
systemctl --user --no-pager status unlocked-tv.service
