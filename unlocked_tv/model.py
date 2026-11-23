"""Remote navigation and app lifecycle independent of the graphics backend."""

from __future__ import annotations

from pathlib import Path
import time
import zipfile

from .store import COLORS, THEMES


class Model:
    def __init__(self, store, player):
        self.store, self.player = store, player
        self.screen = "home"
        self.selection = 0
        self.stack = []
        self.entries = []
        self.message = ""
        self.message_until = 0
        self.pending_package = None
        self.pending_app = None
        self.slideshow_paused = False
        self.photo_index = 0
        self.photo_tick = time.monotonic()
        self.return_after_player = ("home", 0)
        self.move_id = None

    def toast(self, message):
        self.message, self.message_until = message, time.monotonic() + 5

    def home(self):
        self.player.stop()
        self.screen, self.selection, self.stack = "home", 0, []
        self.move_id = None

    def open(self, screen):
        self.stack.append((self.screen, self.selection))
        self.screen, self.selection = screen, 0
        if screen in {"videos", "photos", "packages"}:
            self.entries = self.store.media(screen)
        if screen == "photos":
            self.photo_index = 0
            self.photo_tick = time.monotonic()

    def back(self):
        if self.screen == "playing":
            self.player.stop()
            self.screen, self.selection = self.return_after_player
        elif self.screen == "slideshow":
            self.screen = "photos"
            self.selection = self.photo_index
        elif self.stack:
            self.screen, self.selection = self.stack.pop()
            if self.screen in {"videos", "photos", "packages"}:
                self.entries = self.store.media(self.screen)
        else:
            self.home()
        self.move_id = None

    def rows(self):
        settings = self.store.settings
        if self.screen == "home":
            return self.store.apps()
        if self.screen in {"videos", "photos", "packages"}:
            return self.entries
        if self.screen == "settings":
            return [{"name": "Theme", "value": settings["theme"]}, {"name": "Home Order"},
                    {"name": "Shortcuts"}, {"name": "Apps"}, {"name": "Media Folders"},
                    {"name": "Slideshow", "value": f"{settings['slideshow_seconds']} Seconds"},
                    {"name": "System"}]
        if self.screen == "order":
            return self.store.apps()
        if self.screen == "shortcuts":
            apps = {app["id"]: app["name"] for app in self.store.apps()}
            return [{"name": name, "color": COLORS[i], "value": apps.get(settings["shortcuts"][i], "Unassigned")}
                    for i, name in enumerate(["Blue", "Orange", "Green", "Red", "Yellow", "Purple"])]
        if self.screen == "apps":
            return [{"name": "Install App", "id": "install"},
                    *[app for app in self.store.apps() if app["type"] == "native"]]
        if self.screen == "folders":
            return [{"name": str(path)} for path in self.store.mounted_roots()]
        if self.screen in {"install", "remove"}:
            return [{"name": "Cancel"}, {"name": "Install" if self.screen == "install" else "Remove"}]
        return []

    def cycle(self, delta):
        if self.screen == "settings" and self.selection == 0:
            themes = list(THEMES)
            self.store.save(theme=themes[(themes.index(self.store.settings["theme"]) + delta) % len(themes)])
        elif self.screen == "settings" and self.selection == 5:
            self.store.save(slideshow_seconds=max(2, min(120, self.store.settings["slideshow_seconds"] + delta)))
        elif self.screen == "shortcuts":
            choices = [None, *[app["id"] for app in self.store.apps()]]
            slots = list(self.store.settings["shortcuts"])
            current = choices.index(slots[self.selection]) if slots[self.selection] in choices else 0
            slots[self.selection] = choices[(current + delta) % len(choices)]
            self.store.save(shortcuts=slots)

    def launch(self, app_id):
        app = next((item for item in self.store.apps() if item["id"] == app_id), None)
        if not app:
            self.toast("Shortcut Unassigned")
            return
        if self.player.active:
            self.home()
        if app["type"] == "native":
            self.return_after_player = (self.screen, self.selection)
            self.player.native(app)
            self.screen = "playing"
        else:
            self.open(app["type"])

    def activate(self):
        rows = self.rows()
        if not rows:
            return
        self.selection = min(self.selection, len(rows) - 1)
        row = rows[self.selection]
        if self.screen == "home":
            self.launch(row["id"])
        elif self.screen == "videos":
            self.return_after_player = (self.screen, self.selection)
            self.player.play(row["path"], row["name"], self.store.settings["volume"])
            self.screen = "playing"
        elif self.screen == "photos":
            self.photo_index = self.selection
            self.screen = "slideshow"
            self.slideshow_paused = False
            self.photo_tick = time.monotonic()
        elif self.screen == "settings":
            destination = [None, "order", "shortcuts", "apps", "folders", None, "system"][self.selection]
            if destination:
                self.open(destination)
            else:
                self.cycle(1)
        elif self.screen == "order":
            self.move_id = None if self.move_id else row["id"]
        elif self.screen == "shortcuts":
            self.cycle(1)
        elif self.screen == "apps":
            if row["id"] == "install":
                self.open("packages")
            else:
                self.pending_app = row
                self.open("remove")
        elif self.screen == "packages":
            self.pending_package = (Path(row["path"]), self.store.inspect_package(Path(row["path"])))
            self.open("install")
        elif self.screen == "install":
            if self.selection == 1:
                app = self.store.install(self.pending_package[0])
                self.toast(f"{app['name']} Installed")
            self.back()
        elif self.screen == "remove":
            if self.selection == 1:
                self.store.uninstall(self.pending_app["id"])
            self.back()

    def action(self, action):
        try:
            self._action(action)
        except (ValueError, OSError, zipfile.BadZipFile) as error:
            self.toast(str(error))

    def _action(self, action):
        if action == "home":
            self.home()
            return
        if action == "back":
            self.back()
            return
        if action == "apps":
            self.home()
            return
        if action.startswith("shortcut_"):
            slot = int(action.rsplit("_", 1)[1]) - 1
            if 0 <= slot < 6:
                self.launch(self.store.settings["shortcuts"][slot])
            return
        if action in {"volume_up", "volume_down"}:
            value = max(0, min(100, self.store.settings["volume"] + (5 if action == "volume_up" else -5)))
            self.store.save(volume=value)
            self.player.command("set_property", "volume", value)
            self.toast(f"Volume {value}")
            return
        if action == "mute":
            self.player.command("cycle", "mute")
            return
        if self.screen == "playing":
            if self.player.kind == "native":
                self.player.input(action)
                return
            if action in {"playpause", "select"}:
                self.player.command("cycle", "pause")
            elif action in {"left", "rewind", "right", "forward"}:
                self.player.command("seek", -10 if action in {"left", "rewind"} else 10, "relative")
            return
        if self.screen == "slideshow":
            if action in {"playpause", "select"}:
                self.slideshow_paused = not self.slideshow_paused
            elif action in {"right", "left"} and self.entries:
                self.photo_index = (self.photo_index + (1 if action == "right" else -1)) % len(self.entries)
                self.photo_tick = time.monotonic()
            return
        if action == "select":
            self.activate()
            return
        if action in {"left", "right"} and (self.screen == "shortcuts" or self.screen == "settings"):
            self.cycle(-1 if action == "left" else 1)
            return
        rows = self.rows()
        if not rows:
            return
        if action not in {"left", "right", "up", "down", "page_up", "page_down"}:
            return
        delta = {"left": -1, "right": 1, "up": -4 if self.screen == "home" else -1,
                 "down": 4 if self.screen == "home" else 1, "page_up": -6, "page_down": 6}[action]
        next_index = max(0, min(len(rows) - 1, self.selection + delta))
        if self.screen == "order" and self.move_id:
            order = [app["id"] for app in rows]
            order[self.selection], order[next_index] = order[next_index], order[self.selection]
            self.store.save(home_order=order)
        self.selection = next_index

    def tick(self):
        if self.screen == "playing":
            result = self.player.poll()
            if result is not None:
                self.screen, self.selection = self.return_after_player
                if result != 0:
                    self.toast("Playback Failed" if self.player.kind == "video" else "App Closed Unexpectedly")
        if self.screen == "slideshow" and self.entries and not self.slideshow_paused:
            if time.monotonic() - self.photo_tick >= self.store.settings["slideshow_seconds"]:
                self.photo_index = (self.photo_index + 1) % len(self.entries)
                self.photo_tick = time.monotonic()

    def status(self):
        rows = self.rows()
        selected = rows[self.selection] if rows and self.selection < len(rows) else None
        return {"screen": self.screen, "selection": self.selection, "selected": selected,
                "theme": self.store.settings["theme"], "shortcuts": self.store.settings["shortcuts"],
                "apps": [app["id"] for app in self.store.apps()], "playing": self.player.active,
                "player_kind": self.player.kind, "message": self.message if time.monotonic() < self.message_until else ""}
