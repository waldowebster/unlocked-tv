"""Read supported remote keys without grabbing devices or recording text input."""
import queue
import select
import threading
import time


class RemoteInput:
    def __init__(self, events: queue.Queue):
        self.events = events
        self.stop = threading.Event()
        self.count = 0
        self.thread = None

    def start(self):
        try:
            import evdev  # noqa: F401
        except ImportError:
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        import evdev
        codes = evdev.ecodes
        names = {"KEY_UP": "up", "KEY_DOWN": "down", "KEY_LEFT": "left", "KEY_RIGHT": "right",
                 "KEY_ENTER": "select", "KEY_KPENTER": "select", "KEY_OK": "select",
                 "KEY_ESC": "back", "KEY_BACKSPACE": "back", "KEY_BACK": "back",
                 "KEY_HOME": "home", "KEY_HOMEPAGE": "home", "KEY_MENU": "apps",
                 "KEY_PLAYPAUSE": "playpause", "KEY_SPACE": "playpause", "KEY_PLAY": "playpause",
                 "KEY_REWIND": "rewind", "KEY_FASTFORWARD": "forward",
                 "KEY_VOLUMEUP": "volume_up", "KEY_VOLUMEDOWN": "volume_down", "KEY_MUTE": "mute",
                 "KEY_PAGEUP": "page_up", "KEY_PAGEDOWN": "page_down",
                 "KEY_BLUE": "shortcut_1", "KEY_RED": "shortcut_4", "KEY_GREEN": "shortcut_3", "KEY_YELLOW": "shortcut_5"}
        names.update({f"KEY_F{i}": f"shortcut_{i}" for i in range(1, 7)})
        mapping = {getattr(codes, name): action for name, action in names.items() if hasattr(codes, name)}
        devices = {}
        last_scan = 0
        try:
            while not self.stop.is_set():
                if time.monotonic() - last_scan > 2:
                    for path in evdev.list_devices():
                        if path not in devices:
                            try:
                                device = evdev.InputDevice(path)
                                if codes.EV_KEY in device.capabilities():
                                    devices[path] = device
                                else:
                                    device.close()
                            except OSError:
                                pass
                    last_scan = time.monotonic()
                    self.count = len(devices)
                if not devices:
                    self.stop.wait(0.2)
                    continue
                ready, _, _ = select.select(list(devices.values()), [], [], 0.2)
                for device in ready:
                    try:
                        for event in device.read():
                            if event.type == codes.EV_KEY and event.value in {1, 2}:
                                action = mapping.get(event.code)
                                if action and (event.value == 1 or action in {"up", "down", "left", "right", "volume_up", "volume_down"}):
                                    self.events.put(action)
                    except OSError:
                        devices.pop(device.path, None)
                        device.close()
        finally:
            for device in devices.values():
                device.close()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=1)
