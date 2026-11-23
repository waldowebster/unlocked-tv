"""User-service entry: wait for HDMI, run the TV, and recover from display disconnects."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

running = True
child = None


def stop(signum, frame):
    global running
    running = False
    if child and child.poll() is None:
        child.terminate()


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
last_status = None
while running:
    connected = any(path.read_text().strip() == "connected" for path in Path("/sys/class/drm").glob("*-HDMI-*/status"))
    status = "HDMI Connected" if connected else "Waiting For HDMI"
    if status != last_status:
        print(status, flush=True)
        last_status = status
    if not connected:
        time.sleep(2)
        continue
    env = {**os.environ, "SDL_VIDEODRIVER": "kmsdrm", "SDL_KMSDRM_REQUIRE_DRM_MASTER": "1"}
    child = subprocess.Popen([sys.executable, "-m", "unlocked_tv", "run", "--kiosk"], env=env)
    code = child.wait()
    print(f"TV session exited ({code}); retrying in five seconds", flush=True)
    time.sleep(5)
