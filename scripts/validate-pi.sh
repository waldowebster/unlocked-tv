#!/bin/bash
set -euo pipefail
source_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$source_dir"
report="$HOME/unlocked-tv-validation"
mkdir -p "$report"
export PYTHONPATH="$source_dir${PYTHONPATH:+:$PYTHONPATH}"
"$HOME/.local/bin/unlocked-tv-env" python3 scripts/probe-graphics.py > "$report/graphics.json"
"$HOME/.local/bin/unlocked-tv-env" python3 -m unittest discover -s tests -v > "$report/unit.log" 2>&1
"$HOME/.local/bin/unlocked-tv-env" python3 scripts/test-e2e.py "$report" > "$report/e2e.log" 2>&1
"$HOME/.local/bin/unlocked-tv-env" python3 - <<'PY' > "$report/hardware.json"
import ctypes, json, os
from pathlib import Path
sdl = ctypes.CDLL('libSDL2-2.0.so.0')
sdl.SDL_GetVideoDriver.restype = ctypes.c_char_p
print(json.dumps({'drivers':[sdl.SDL_GetVideoDriver(i).decode() for i in range(sdl.SDL_GetNumVideoDrivers())], 'devices':{str(p):{'read':os.access(p,os.R_OK),'write':os.access(p,os.W_OK)} for p in [Path('/dev/dri/card0'),Path('/dev/dri/renderD128'),Path('/dev/cec0')]}, 'hdmi':{str(p):p.read_text().strip() for p in Path('/sys/class/drm').glob('*HDMI*/status')}}, indent=2))
PY
cat "$report/report.json"
cat "$report/hardware.json"
cat "$report/graphics.json"
