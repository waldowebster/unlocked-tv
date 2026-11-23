#!/bin/bash
set -e
runtime="$HOME/.local/opt/unlocked-tv-runtime"
arch="$(dpkg-architecture -qDEB_HOST_MULTIARCH 2>/dev/null || echo aarch64-linux-gnu)"
export PATH="$runtime/usr/bin:$HOME/.local/bin:$PATH"
export PYTHONPATH="$HOME/.local/opt/unlocked-tv/current:$runtime/usr/lib/python3/dist-packages${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$runtime/usr/lib/$arch:$runtime/lib/$arch:$runtime/usr/lib/$arch/pulseaudio:$runtime/usr/lib/$arch/blas:$runtime/usr/lib/$arch/lapack${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
if [ -d "$runtime/usr/lib/$arch/dri" ]; then export LIBGL_DRIVERS_PATH="$runtime/usr/lib/$arch/dri"; fi
if [ -d "$runtime/usr/lib/$arch/gbm" ]; then export GBM_BACKENDS_PATH="$runtime/usr/lib/$arch/gbm"; fi
if [ -f "$runtime/usr/share/glvnd/egl_vendor.d/50_mesa.json" ]; then export __EGL_VENDOR_LIBRARY_FILENAMES="$runtime/usr/share/glvnd/egl_vendor.d/50_mesa.json"; fi
export UNLOCKED_TV_RUNTIME="$runtime"
if [ -f "$runtime/etc/fonts/fonts.conf" ]; then export FONTCONFIG_FILE="$runtime/etc/fonts/fonts.conf"; export FONTCONFIG_PATH="$runtime/etc/fonts"; fi
export PYGAME_HIDE_SUPPORT_PROMPT=1
exec "$@"
