#!/bin/bash
# Install an already-reviewed source release into the owner's account.
set -euo pipefail
source_dir="$(cd "$(dirname "$0")/.." && pwd)"
base="$HOME/.local/opt/unlocked-tv"
release="$(date +%Y%m%d-%H%M%S)"
data="$HOME/.local/share/unlocked-tv"
mkdir -p "$base/releases/$release" "$HOME/.local/bin" "$HOME/.config/systemd/user"
cp -R "$source_dir/unlocked_tv" "$source_dir/scripts" "$source_dir/assets" "$source_dir/examples" "$source_dir/tests" "$source_dir/README.md" "$source_dir/LICENSE" "$base/releases/$release/"
if [ -L "$base/current" ]; then readlink "$base/current" > "$base/previous-release"; fi
ln -s "releases/$release" "$base/current.new"
mv -Tf "$base/current.new" "$base/current"
cp "$source_dir/scripts/runtime-env.sh" "$HOME/.local/bin/unlocked-tv-env"
chmod 755 "$HOME/.local/bin/unlocked-tv-env"
cat > "$HOME/.local/bin/unlocked-tv" <<'ENTRY'
#!/bin/bash
exec "$HOME/.local/bin/unlocked-tv-env" python3 -m unlocked_tv "$@"
ENTRY
chmod 755 "$HOME/.local/bin/unlocked-tv"
"$HOME/.local/bin/unlocked-tv" settings >/dev/null
mkdir -p "$data/media" "$data/packages"
for file in "$source_dir/assets/"*; do
    [ -f "$file" ] && cp -n "$file" "$data/media/" || true
done
"$HOME/.local/bin/unlocked-tv-env" python3 "$source_dir/scripts/package-example.py" "$data/packages/counter.zip"
cat > "$HOME/.config/systemd/user/unlocked-tv.service" <<'UNIT'
[Unit]
Description=Unlocked TV Native Session

[Service]
Type=simple
ExecStart=%h/.local/bin/unlocked-tv-env /usr/bin/python3 %h/.local/opt/unlocked-tv/current/scripts/session.py
Restart=on-failure
RestartSec=5
KillMode=control-group
TimeoutStopSec=8
NoNewPrivileges=yes
UMask=0077
StandardOutput=append:%h/.local/share/unlocked-tv/logs/session.log
StandardError=inherit

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable unlocked-tv.service
systemctl --user restart unlocked-tv.service
echo "INSTALLED $base/releases/$release"
systemctl --user --no-pager status unlocked-tv.service
