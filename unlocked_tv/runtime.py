"""Local-only control, isolated player process, and optional HDMI-CEC input."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import signal
import socket
import subprocess
import sys
import threading
import time


def socket_request(path: Path, message: dict, timeout: float = 1.0):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(str(path))
        connection.sendall(json.dumps(message).encode() + b"\n")
        data = b""
        while b"\n" not in data and len(data) < 65536:
            chunk = connection.recv(4096)
            if not chunk:
                break
            data += chunk
        return json.loads(data.split(b"\n", 1)[0])


class ControlServer:
    """A mode-0600 Unix socket. Requests are executed on the GUI thread."""

    def __init__(self, path: Path):
        self.path = path
        self.requests = queue.Queue()
        self.stop = threading.Event()
        if path.exists():
            try:
                socket_request(path, {"action": "status"}, 0.3)
            except (OSError, ValueError):
                path.unlink()
            else:
                raise RuntimeError("Unlocked TV is already running")
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(path))
        os.chmod(path, 0o600)
        self.server.listen(8)
        self.server.settimeout(0.2)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while not self.stop.is_set():
            try:
                connection, _ = self.server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with connection:
                connection.settimeout(2)
                try:
                    data = b""
                    while b"\n" not in data and len(data) < 8192:
                        chunk = connection.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    request = json.loads(data.split(b"\n", 1)[0])
                    if not isinstance(request, dict):
                        raise ValueError("Request must be an object")
                    response = queue.Queue(maxsize=1)
                    self.requests.put((request, response))
                    result = response.get(timeout=4)
                except (ValueError, OSError, queue.Empty) as error:
                    result = {"error": str(error) or "Request timed out"}
                try:
                    connection.sendall(json.dumps(result).encode() + b"\n")
                except OSError:
                    pass

    def close(self):
        self.stop.set()
        self.server.close()
        self.thread.join(timeout=1)
        self.path.unlink(missing_ok=True)


MPV_KEYS = """ESC quit-watch-later
BS quit-watch-later
HOME quit-watch-later
ENTER cycle pause
SPACE cycle pause
LEFT seek -10
RIGHT seek 10
UP add volume 5
DOWN add volume -5
m cycle mute
q quit-watch-later
PLAYPAUSE cycle pause
STOP quit-watch-later
"""


class Player:
    def __init__(self, root: Path, headless=False):
        self.root = root
        self.headless = headless
        self.process = None
        self.kind = None
        self.target = None
        self.title = ""
        self.socket = root / "mpv.sock"
        self.log = None
        self.last_exit = None
        self.input_path = root / "mpv-input.conf"
        self.input_path.write_text(MPV_KEYS)

    @property
    def active(self):
        return self.process is not None and self.process.poll() is None

    def play(self, path: str, title: str, volume: int):
        self.stop()
        self.socket.unlink(missing_ok=True)
        command = [
            "mpv", "--no-config", "--no-terminal", "--fullscreen", "--force-window=yes",
            "--keep-open=no", "--hwdec=auto", "--cache=yes", "--cache-secs=5",
            "--demuxer-max-bytes=32MiB", "--demuxer-max-back-bytes=8MiB",
            "--save-position-on-quit=yes", "--resume-playback=yes",
            f"--watch-later-directory={self.root / 'resume'}",
            f"--input-ipc-server={self.socket}", f"--input-conf={self.input_path}",
            f"--volume={volume}", "--volume-max=100", "--title=Unlocked TV Player",
        ]
        if self.headless:
            command += ["--vo=null", "--ao=null"]
        elif os.environ.get("SDL_VIDEODRIVER") == "kmsdrm":
            command += ["--vo=gpu", "--gpu-context=drm", "--opengl-es=yes", "--ao=alsa"]
        command += ["--", path]
        self._launch(command, "video", path, title)

    def native(self, app: dict):
        self.stop()
        directory = Path(app["directory"]).resolve()
        entry = (directory / app["entry"]).resolve()
        if not entry.is_relative_to(directory) or not entry.is_file():
            raise ValueError("App entry is unavailable")
        data = self.root / "app-data" / app["id"]
        data.mkdir(exist_ok=True)
        env = {**os.environ, "UNLOCKED_APP_DATA": str(data), "UNLOCKED_TV_SOCKET": str(self.root / "control.sock")}
        env["UNLOCKED_APP_INPUT"] = "stdin"
        self._launch([sys.executable, str(entry)], "native", app["id"], app["name"], cwd=directory, env=env)

    def _launch(self, command, kind, target, title, **kwargs):
        self.log = (self.root / "logs" / "last-app.log").open("w")
        env = kwargs.pop("env", dict(os.environ))
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
        try:
            self.process = subprocess.Popen([sys.executable, "-m", "unlocked_tv.child", *command], stdin=subprocess.PIPE if kind == "native" else subprocess.DEVNULL, stdout=self.log,
                                            stderr=subprocess.STDOUT, start_new_session=True,
                                            env=env, **kwargs)
        except Exception:
            self.log.close()
            self.log = None
            raise
        self.kind, self.target, self.title = kind, target, title
        if self.process.stdin:
            os.set_blocking(self.process.stdin.fileno(), False)
        self.last_exit = None

    def input(self, action):
        if self.kind == "native" and self.active:
            try:
                os.write(self.process.stdin.fileno(), json.dumps({"action": action}).encode() + b"\n")
            except (OSError, ValueError):
                pass

    def command(self, *args):
        if self.kind != "video" or not self.active:
            return None
        try:
            # mpv can emit asynchronous events before its command response.
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(0.2)
                connection.connect(str(self.socket))
                connection.sendall(json.dumps({"command": list(args), "request_id": 17}).encode() + b"\n")
                with connection.makefile("rb") as stream:
                    for _ in range(10):
                        message = json.loads(stream.readline(65536))
                        if message.get("request_id") == 17:
                            return message.get("data")
        except (OSError, ValueError):
            return None

    def poll(self):
        if self.process is None or self.process.poll() is None:
            return None
        code = self.process.returncode
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        self.last_exit = code
        if self.process.stdin:
            self.process.stdin.close()
        self.process = None
        if self.log:
            self.log.close()
            self.log = None
        return code

    def stop(self):
        if self.active:
            if self.kind == "video":
                self.command("quit-watch-later")
            else:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                self.process.wait(timeout=0.8)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=1)
        self.poll()


class CEC:
    """Translate libCEC's pressed-key notifications to the shell's action vocabulary."""

    KEYS = {0x00: "select", 0x01: "up", 0x02: "down", 0x03: "left", 0x04: "right",
            0x09: "home", 0x0D: "back", 0x30: "page_up", 0x31: "page_down",
            0x41: "volume_up", 0x42: "volume_down", 0x43: "mute",
            0x44: "playpause", 0x45: "back", 0x46: "playpause", 0x48: "rewind", 0x49: "forward",
            0x71: "shortcut_1", 0x72: "shortcut_4", 0x73: "shortcut_3", 0x74: "shortcut_5"}

    def __init__(self, events: queue.Queue):
        self.events = events
        self.process = None
        self.status = "Unavailable"
        self.last_key = (None, 0.0)

    def start(self):
        if not Path("/dev/cec0").exists():
            return
        try:
            self.process = subprocess.Popen(["cec-client", "-d", "8", "-t", "p", "-o", "Unlocked TV"],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, text=True)
        except OSError:
            return
        self.status = "Listening"
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.process.stdout:
            match = re.search(r"key pressed:.*\(([0-9a-fA-F]+)\)", line)
            if not match:
                continue
            action = self.KEYS.get(int(match[1], 16))
            now = time.monotonic()
            if action and (action != self.last_key[0] or now - self.last_key[1] >= 0.15):
                self.events.put(action)
                self.last_key = action, now
        self.status = "Disconnected"

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
