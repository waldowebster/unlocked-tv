"""A native ten-foot UI: large type, visible focus, no desktop or browser runtime."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import queue
import signal
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

from . import __version__
from .input import RemoteInput
from .model import Model
from .runtime import CEC, ControlServer, Player
from .store import COLORS, THEMES


KEYS = {pygame.K_UP: "up", pygame.K_DOWN: "down", pygame.K_LEFT: "left", pygame.K_RIGHT: "right",
        pygame.K_RETURN: "select", pygame.K_KP_ENTER: "select", pygame.K_ESCAPE: "back", pygame.K_BACKSPACE: "back",
        pygame.K_HOME: "home", pygame.K_SPACE: "playpause", pygame.K_PAGEUP: "page_up", pygame.K_PAGEDOWN: "page_down",
        pygame.K_EQUALS: "volume_up", pygame.K_PLUS: "volume_up", pygame.K_MINUS: "volume_down", pygame.K_m: "mute"}
KEYS.update({getattr(pygame, f"K_F{i}"): f"shortcut_{i}" for i in range(1, 7)})


class View:
    def __init__(self):
        self.canvas = pygame.Surface((1280, 720))
        self.fonts = {}
        self.image_key, self.image = None, None
        runtime = Path(os.environ.get("UNLOCKED_TV_RUNTIME", "/nonexistent"))
        options = [runtime / "usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                   Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                   Path("/System/Library/Fonts/Supplemental/Arial.ttf")]
        self.font_path = next((str(path) for path in options if path.is_file()), None)

    def text(self, value, size, x, y, color, bold=False, width=None):
        key = size, bold
        if key not in self.fonts:
            font = pygame.font.Font(self.font_path, size)
            font.set_bold(bold)
            self.fonts[key] = font
        font = self.fonts[key]
        value = str(value)
        if width:
            while value and font.size(value)[0] > width:
                value = value[:-2].rstrip("…") + "…"
        self.canvas.blit(font.render(value, True, color), (x, y))

    def icon(self, name, x, y, color, size=64):
        surface = self.canvas
        s = size / 64
        def p(a, b):
            return (round(x + a * s), round(y + b * s))
        line = max(2, round(3 * s))
        if name == "play":
            pygame.draw.polygon(surface, color, [p(21, 12), p(52, 32), p(21, 52)], line)
        elif name == "photo":
            pygame.draw.rect(surface, color, (*p(9, 12), round(46*s), round(40*s)), line, border_radius=round(5*s))
            pygame.draw.circle(surface, color, p(42, 24), round(4*s))
            pygame.draw.lines(surface, color, False, [p(11, 44), p(25, 29), p(37, 41), p(44, 35), p(54, 46)], line)
        elif name == "clock":
            pygame.draw.circle(surface, color, p(32, 32), round(23*s), line)
            pygame.draw.lines(surface, color, False, [p(32, 17), p(32, 32), p(44, 39)], line)
        elif name == "settings":
            for row, knob in [(17, 24), (32, 43), (47, 29)]:
                pygame.draw.line(surface, color, p(10, row), p(54, row), line)
                pygame.draw.circle(surface, color, p(knob, row), round(5*s))
        else:
            for a in [13, 36]:
                for b in [13, 36]:
                    pygame.draw.rect(surface, color, (*p(a, b), round(15*s), round(15*s)), line, border_radius=round(3*s))

    def draw(self, model, diagnostics=None):
        theme = THEMES[model.store.settings["theme"]]
        bg, surface, text, muted, accent = [pygame.Color(theme[key]) for key in ("bg", "surface", "text", "muted", "accent")]
        self.canvas.fill(bg)
        titles = {"home": "Home", "videos": "Videos", "photos": "Photos", "clock": "Clock",
                  "settings": "Settings", "order": "Home Order", "shortcuts": "Shortcuts", "apps": "Apps",
                  "folders": "Media Folders", "packages": "Install App", "system": "System",
                  "install": "Install App", "remove": "Remove App", "playing": model.player.title}
        if model.screen == "slideshow":
            self.draw_photo(model)
        elif model.screen == "clock":
            now = datetime.now()
            value = now.strftime("%I:%M").lstrip("0")
            self.text(value, 152, 1280//2 - 230, 225, text)
            self.text(now.strftime("%A, %B %d"), 28, 450, 422, muted)
        else:
            self.text("UNLOCKED", 16, 64, 40, muted, True)
            self.text(datetime.now().strftime("%I:%M %p").lstrip("0"), 21, 1090, 42, muted)
            self.text(titles.get(model.screen, model.screen.title()), 48, 64, 78, text, True, 1080)
            if model.screen == "home":
                self.draw_home(model, surface, text, muted, accent)
            elif model.screen == "system":
                details = [("Version", __version__), ("Device", os.uname().nodename),
                           ("Remote Input", (diagnostics or {}).get("cec", "Unavailable")),
                           ("Apps", len(model.store.apps())), ("Storage", str(model.store.root))]
                for i, (label, value) in enumerate(details):
                    self.text(label, 25, 80, 198 + i*70, muted)
                    self.text(value, 25, 360, 198 + i*70, text, width=820)
            elif model.screen in {"install", "remove"}:
                app = model.pending_package[1] if model.screen == "install" else model.pending_app
                self.text(app["name"], 36, 80, 210, text, True)
                # A concrete trust decision for executable apps, not decorative helper copy.
                if model.screen == "install":
                    self.text("Runs Code As Your User", 24, 80, 275, muted)
                for i, label in enumerate(["Cancel", "Install" if model.screen == "install" else "Remove"]):
                    rect = pygame.Rect(80 + i*290, 380, 260, 76)
                    pygame.draw.rect(self.canvas, surface, rect, border_radius=12)
                    if i == model.selection:
                        pygame.draw.rect(self.canvas, accent, rect, 3, border_radius=12)
                    self.text(label, 27, rect.x+28, rect.y+20, text)
            elif model.screen == "playing":
                self.text("Opening…", 28, 80, 220, muted)
            else:
                self.draw_list(model, surface, text, muted, accent)
        if time.monotonic() < model.message_until:
            pygame.draw.rect(self.canvas, surface, (240, 602, 800, 68), border_radius=12)
            self.text(model.message, 23, 268, 621, text, width=744)
        return self.canvas

    def draw_home(self, model, surface, text, muted, accent):
        apps = model.store.apps()
        first = max(0, model.selection // 4 - 1) * 4
        card_height = 182 if len(apps) > 4 else 248
        top = 179 if len(apps) > 4 else 224
        for i, app in enumerate(apps[first:first+8], first):
            index = i - first
            rect = pygame.Rect(64 + (index % 4)*294, top + (index // 4)*(card_height+20), 270, card_height)
            pygame.draw.rect(self.canvas, surface, rect, border_radius=18)
            if i == model.selection:
                pygame.draw.rect(self.canvas, accent, rect.inflate(8, 8), 3, border_radius=21)
            self.icon(app["icon"], rect.x+25, rect.y+25, pygame.Color(app["color"]), 66)
            self.text(app["name"], 27, rect.x+26, rect.bottom-61, text, True, rect.width-50)
        names = {app["id"]: app["name"] for app in apps}
        for i, app_id in enumerate(model.store.settings["shortcuts"]):
            x = 64 + i*196
            pygame.draw.rect(self.canvas, pygame.Color(COLORS[i]), (x, 647, 12, 12), border_radius=4)
            self.text(names.get(app_id, ""), 17, x+22, 640, muted, width=163)

    def draw_list(self, model, surface, text, muted, accent):
        rows = model.rows()
        if not rows:
            empty = {"videos": "No Videos", "photos": "No Photos", "packages": "No App Packages", "folders": "No Media Folders"}
            self.text(empty.get(model.screen, "Empty"), 30, 80, 240, muted)
            return
        first = max(0, model.selection - 5)
        for i, row in enumerate(rows[first:first+6], first):
            y = 178 + (i-first)*73
            rect = pygame.Rect(64, y, 1152, 65)
            if i == model.selection:
                pygame.draw.rect(self.canvas, surface, rect, border_radius=12)
                pygame.draw.rect(self.canvas, accent, rect, 2, border_radius=12)
            x = 88
            if "color" in row:
                pygame.draw.circle(self.canvas, pygame.Color(row["color"]), (99, y+32), 7)
                x = 122
            name = row["name"]
            if model.screen == "order" and model.move_id == row.get("id"):
                name = "↕  " + name
            self.text(name, 25, x, y+16, text, width=785 if row.get("value") else 1080)
            if row.get("value"):
                self.text(row["value"], 23, 886, y+18, muted, width=300)
        if len(rows) > 6:
            self.text(f"{model.selection+1} / {len(rows)}", 18, 1110, 650, muted)

    def draw_photo(self, model):
        if not model.entries:
            return
        path = model.entries[model.photo_index]["path"]
        if path != self.image_key:
            self.image = None
            self.image_key = path
            try:
                image = pygame.image.load(path)
                width, height = image.get_size()
                ratio = min(1280/width, 720/height)
                self.image = pygame.transform.smoothscale(image, (max(1, int(width*ratio)), max(1, int(height*ratio))))
            except (pygame.error, OSError, ValueError):
                model.toast("Unable To Open Photo")
        if self.image:
            self.canvas.blit(self.image, ((1280-self.image.get_width())//2, (720-self.image.get_height())//2))


def run(store, headless=False, windowed=False, kiosk=False):
    if headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    if kiosk and not headless:
        os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_caption("Unlocked TV")
    pygame.key.set_repeat(350, 120)
    pygame.mouse.set_visible(windowed)
    def display():
        return pygame.display.set_mode((1280, 720) if headless or windowed else (0, 0), pygame.RESIZABLE if windowed else (0 if headless else pygame.FULLSCREEN))
    screen = display()
    player = Player(store.root, headless=headless)
    model = Model(store, player)
    view = View()
    controls = ControlServer(store.root / "control.sock")
    events = queue.Queue()
    cec = CEC(events)
    remote = RemoteInput(events)
    if kiosk:
        remote.start()
        if store.settings["cec_enabled"]:
            cec.start()
    if store.warnings:
        model.toast("Settings Recovered")
    running = True
    released = False
    last_signature = None
    ticks = pygame.time.Clock()
    def stop(_signum, _frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while running:
            def release_display():
                nonlocal released
                if kiosk and not headless and not released:
                    pygame.display.quit()
                    released = True
            while not controls.requests.empty():
                request, response = controls.requests.get_nowait()
                try:
                    action = request.get("action")
                    if action == "input":
                        events.put(request["key"])
                    elif action == "launch":
                        if any(app["id"] == request["id"] and app["type"] == "native" for app in store.apps()):
                            release_display()
                        model.launch(request["id"])
                    elif action == "settings":
                        store.save(**request["values"])
                    elif action == "reload":
                        store.settings = store.load()
                        model.home()
                    elif action == "screenshot":
                        pygame.image.save(view.draw(model), request["path"])
                    elif action == "player":
                        result = player.command(*request["command"])
                        response.put({"data": result})
                        continue
                    elif action == "quit":
                        running = False
                    elif action != "status":
                        raise ValueError("Unknown control action")
                    response.put({**model.status(), "pid": os.getpid(), "cec": cec.status,
                                  "input_devices": remote.count, "headless": headless,
                                  "display_driver": "released" if released else pygame.display.get_driver()})
                except Exception as error:
                    response.put({"error": str(error)})
            # A KMS app must relinquish the display before mpv or a native app owns it.
            def handle(action):
                nonlocal released
                will_launch = ((model.screen == "videos" and action == "select" and model.rows()) or
                               (model.screen == "home" and action == "select" and model.rows()[model.selection]["type"] == "native") or
                               (action.startswith("shortcut_") and any(app["id"] == store.settings["shortcuts"][int(action[-1])-1] and app["type"] == "native" for app in store.apps())))
                if kiosk and not headless and will_launch and not released:
                    release_display()
                model.action(action)
            if not released:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN and not (kiosk and remote.count):
                        action = KEYS.get(event.key)
                        if action:
                            handle(action)
                    elif event.type == pygame.MOUSEBUTTONDOWN and windowed and model.screen == "home":
                        mx, my = event.pos
                        mx, my = mx * 1280/screen.get_width(), my * 720/screen.get_height()
                        top = 179 if len(store.apps()) > 4 else 224
                        height = 182 if len(store.apps()) > 4 else 248
                        col, row = int((mx-64)//294), int((my-top)//(height+20))
                        index = row*4+col
                        if 0 <= col < 4 and row >= 0 and 0 <= index < len(store.apps()):
                            model.selection = index
                            handle("select")
            while not events.empty():
                handle(events.get_nowait())
            model.tick()
            if released and not player.active:
                pygame.display.init()
                screen = display()
                released = False
                last_signature = None
            signature = json.dumps(model.status(), sort_keys=True) + str(int(time.time())) + str(model.photo_index) + str(model.move_id)
            if not released and signature != last_signature:
                frame = view.draw(model, {"cec": cec.status})
                screen.blit(frame if screen.get_size() == (1280, 720) else pygame.transform.smoothscale(frame, screen.get_size()), (0, 0))
                pygame.display.flip()
                last_signature = signature
            ticks.tick(30)
    finally:
        player.stop()
        cec.close()
        remote.close()
        controls.close()
        pygame.quit()
