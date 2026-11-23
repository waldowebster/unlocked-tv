"""Exercise the real GUI event loop, app processes, and optional real mpv playback."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from unlocked_tv.runtime import socket_request  # noqa: E402
from unlocked_tv.store import Store  # noqa: E402

output = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "artifacts/e2e"
output.mkdir(parents=True, exist_ok=True)
checks = []
temporary = tempfile.TemporaryDirectory(prefix="utv-e2e-")
data = Path(temporary.name)
store = Store(data)
for path in (ROOT / "assets").iterdir():
    shutil.copy2(path, data / "media" / path.name)
subprocess.run([sys.executable, str(ROOT / "scripts/package-example.py"), str(data / "packages/counter.zip")], check=True)
env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""), "PYGAME_HIDE_SUPPORT_PROMPT": "1"}
log = (output / "gui.log").open("w")
process = None


def request(action, **values):
    response = socket_request(data / "control.sock", {"action": action, **values}, timeout=5)
    if "error" in response:
        raise AssertionError(response)
    return response


def wait_for(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = request("status")
            if predicate(last):
                return last
        except OSError:
            pass
        if process.poll() is not None:
            raise AssertionError(f"GUI exited {process.returncode}: {(output / 'gui.log').read_text()}")
        time.sleep(0.05)
    raise AssertionError(f"Timed out: {last}")


def key(name, times=1):
    for _ in range(times):
        request("input", key=name)
        time.sleep(0.08)


def wait_position(minimum, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = request("player", command=["get_property", "time-pos"])["data"]
        if isinstance(value, (float, int)) and value > minimum:
            return value
        time.sleep(0.1)
    raise AssertionError((data / "logs/last-app.log").read_text())


def start():
    global process
    process = subprocess.Popen([sys.executable, "-m", "unlocked_tv", "--data", str(data), "run", "--headless"],
                               env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    wait_for(lambda status: status["screen"] == "home")


def stop():
    if process and process.poll() is None:
        request("quit")
        process.wait(timeout=8)


try:
    start()
    request("screenshot", path=str(output / "home.png"))
    key("right", 3)
    key("select")
    wait_for(lambda status: status["screen"] == "settings")
    key("right")
    assert request("status")["theme"] == "Mist"
    request("screenshot", path=str(output / "settings-mist.png"))
    key("left")
    key("down")
    key("select")
    key("select")
    key("down")
    key("select")
    assert Store(data).settings["home_order"][:2] == ["photos", "videos"]
    key("back")
    key("down")
    key("select")
    before = request("status")["shortcuts"][0]
    key("right")
    assert request("status")["shortcuts"][0] != before
    request("screenshot", path=str(output / "shortcuts.png"))
    checks.append("D-pad navigation, theme, home ordering, shortcut editing")

    key("home")
    request("launch", id="settings")
    key("down", 3)
    key("select")
    key("select")
    key("select")
    assert request("status")["screen"] == "install"
    assert "counter" not in request("status")["apps"]
    request("screenshot", path=str(output / "install-confirmation.png"))
    key("right")
    key("select")
    assert "counter" in request("status")["apps"]
    assert not request("status")["playing"]
    key("home")
    request("launch", id="counter")
    wait_for(lambda status: status["playing"] and status["player_kind"] == "native")
    time.sleep(0.6)
    assert request("status")["playing"]
    key("right", 2)
    key("left")
    counter_path = data / "app-data/counter/counter.json"
    wait_for(lambda status: counter_path.exists() and json.loads(counter_path.read_text())["count"] == 1, timeout=15)
    key("home")
    wait_for(lambda status: status["screen"] == "home" and not status["playing"])
    checks.append("Explicit app installation, real native app launch, Home recovery")

    request("launch", id="photos")
    key("select")
    assert request("status")["screen"] == "slideshow"
    key("right")
    request("screenshot", path=str(output / "slideshow.png"))
    key("back")
    assert request("status")["screen"] == "photos"
    key("home")
    request("launch", id="clock")
    request("screenshot", path=str(output / "clock.png"))
    key("home")
    checks.append("Photo slideshow navigation, clock, Back/Home behavior")

    saved = Store(data).settings
    stop()
    start()
    assert request("status")["shortcuts"] == saved["shortcuts"]
    assert request("status")["apps"][:2] == ["photos", "videos"]
    checks.append("Settings and installed apps survive full process restart")

    if shutil.which("mpv"):
        request("launch", id="videos")
        key("select")
        wait_for(lambda status: status["playing"])
        deadline = time.monotonic() + 12
        position = None
        while time.monotonic() < deadline:
            position = request("player", command=["get_property", "time-pos"])["data"]
            if isinstance(position, (int, float)) and position > 0.2:
                break
            time.sleep(0.1)
        assert position and position > 0.2, (data / "logs/last-app.log").read_text()
        key("playpause")
        assert request("player", command=["get_property", "pause"])["data"] is True
        key("right")
        wait_position(8)
        key("volume_up")
        assert request("player", command=["get_property", "volume"])["data"] == 65
        key("back")
        wait_for(lambda status: status["screen"] == "videos" and not status["playing"])
        assert list((data / "resume").glob("*"))
        key("select")
        wait_position(8)
        key("home")
        checks.append("Real mpv H.264/AAC decode, pause, seek, volume, resume after relaunch")
    else:
        checks.append("Video check skipped: mpv unavailable on this test host")

    crash = data / "packages/crash.zip"
    with zipfile.ZipFile(crash, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"schema_version": 1, "id": "crash-test", "name": "Crash Test", "type": "native", "runtime": "python3", "entry": "main.py"}))
        archive.writestr("main.py", "raise SystemExit(7)\n")
    Store(data).install(crash)
    request("reload")
    request("launch", id="crash-test")
    wait_for(lambda status: status["screen"] == "home" and status["message"] == "App Closed Unexpectedly")
    checks.append("Crashed native app returns to a usable Home screen")
    final = request("status")
    report = {"passed": True, "checks": checks, "host": os.uname().nodename, "machine": os.uname().machine,
              "display": "SDL dummy (no HDMI/audio-device verification)", "final": final}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
finally:
    stop()
    if (data / "logs/last-app.log").exists():
        shutil.copy2(data / "logs/last-app.log", output / "last-app.log")
    log.close()
    temporary.cleanup()
