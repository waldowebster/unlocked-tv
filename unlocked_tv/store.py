"""Validated, atomic configuration and explicit owner-installed app packages."""

from __future__ import annotations

import copy
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import time
from urllib.parse import urlparse
import zipfile

BUILTINS = [
    {"id": "videos", "name": "Videos", "type": "videos", "icon": "play", "color": "#7199EB"},
    {"id": "photos", "name": "Photos", "type": "photos", "icon": "photo", "color": "#DEAB76"},
    {"id": "clock", "name": "Clock", "type": "clock", "icon": "clock", "color": "#91C7B1"},
    {"id": "settings", "name": "Settings", "type": "settings", "icon": "settings", "color": "#A69DC5"},
]
RESERVED = {app["id"] for app in BUILTINS}
COLORS = ["#436FEA", "#F18946", "#42B18C", "#E76178", "#E3C955", "#AD78D5"]
THEMES = {
    "Midnight": {"bg": "#11151D", "surface": "#1C2330", "text": "#F1F3F7", "muted": "#9BA8BD", "accent": "#A9C6FF"},
    "Mist": {"bg": "#EBEEE9", "surface": "#DAE0D8", "text": "#17251F", "muted": "#50645B", "accent": "#296B54"},
    "Forest": {"bg": "#111E1B", "surface": "#20352E", "text": "#EFF5EE", "muted": "#9CB9A8", "accent": "#A4D5A8"},
}
DEFAULTS = {
    "schema_version": 1,
    "theme": "Midnight",
    "home_order": [app["id"] for app in BUILTINS],
    "shortcuts": ["videos", "photos", "clock", None, None, "settings"],
    "media_roots": [],
    "streams": [],
    "slideshow_seconds": 8,
    "volume": 60,
    "cec_enabled": True,
}


def atomic_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as file:
            json.dump(data, file, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def validate_settings(data: dict) -> dict:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Unsupported settings version")
    value = copy.deepcopy(DEFAULTS)
    value.update(data)
    if value["theme"] not in THEMES:
        raise ValueError("Unknown theme")
    for key in ("home_order", "shortcuts", "media_roots", "streams"):
        if not isinstance(value[key], list):
            raise ValueError(f"{key} must be a list")
    if not all(isinstance(x, str) for x in value["home_order"]):
        raise ValueError("Invalid home order")
    if len(value["home_order"]) != len(set(value["home_order"])):
        raise ValueError("Duplicate home entries")
    if len(value["shortcuts"]) != 6 or not all(x is None or isinstance(x, str) for x in value["shortcuts"]):
        raise ValueError("Exactly six shortcut assignments are required")
    if not all(isinstance(x, str) and Path(x).is_absolute() for x in value["media_roots"]):
        raise ValueError("Media folders must be absolute paths")
    if not isinstance(value["volume"], int) or not 0 <= value["volume"] <= 100:
        raise ValueError("Volume must be between 0 and 100")
    if not isinstance(value["slideshow_seconds"], int) or not 2 <= value["slideshow_seconds"] <= 120:
        raise ValueError("Slideshow interval must be between 2 and 120 seconds")
    if not isinstance(value["cec_enabled"], bool):
        raise ValueError("CEC setting must be true or false")
    for stream in value["streams"]:
        if not isinstance(stream, dict) or not isinstance(stream.get("name"), str) or not stream["name"].strip():
            raise ValueError("Streams need a name")
        if not isinstance(stream.get("url"), str) or urlparse(stream["url"]).scheme not in {"http", "https"}:
            raise ValueError("Only HTTP(S) streams are supported")
    return value


def validate_manifest(data: dict) -> dict:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Unsupported app manifest")
    app_id = data.get("id", "")
    if not isinstance(app_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,47}", app_id) or app_id in RESERVED:
        raise ValueError("Invalid or reserved app ID")
    if not isinstance(data.get("name"), str) or not 1 <= len(data["name"].strip()) <= 40:
        raise ValueError("App name must contain 1 to 40 characters")
    if data.get("type") != "native" or data.get("runtime") != "python3":
        raise ValueError("This MVP supports native Python 3 app packages")
    entry = data.get("entry", "")
    if not isinstance(entry, str) or not entry.endswith(".py") or not safe_member(entry):
        raise ValueError("App entry must be a relative Python file")
    if not isinstance(data.get("color", "#A9C6FF"), str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", data.get("color", "#A9C6FF")):
        raise ValueError("Invalid app color")
    return {**data, "icon": "app", "color": data.get("color", "#A9C6FF")}


def safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name and ":" not in name and "\x00" not in name


class Store:
    def __init__(self, root: Path | None = None):
        self.root = (root or Path(os.environ.get("UNLOCKED_TV_HOME", "~/.local/share/unlocked-tv")).expanduser()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)
        for name in ("apps", "media", "packages", "resume", "backups", "logs", "app-data"):
            (self.root / name).mkdir(exist_ok=True)
        self.path = self.root / "settings.json"
        self.warnings: list[str] = []
        self.settings = self.load()

    def load(self):
        if self.path.exists():
            try:
                return validate_settings(json.loads(self.path.read_text()))
            except (ValueError, OSError, TypeError) as error:
                backup = self.root / "backups" / f"settings-invalid-{time.time_ns()}.json"
                shutil.copy2(self.path, backup)
                self.warnings.append(f"Settings recovered; original saved in {backup.name}: {error}")
        settings = copy.deepcopy(DEFAULTS)
        settings["media_roots"] = [str(self.root / "media")]
        atomic_json(self.path, settings)
        return settings

    def save(self, **changes):
        with (self.root / ".settings.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            current = validate_settings(json.loads(self.path.read_text()))
            updated = validate_settings({**current, **changes})
            atomic_json(self.path, updated)
            self.settings = updated

    def apps(self):
        apps = copy.deepcopy(BUILTINS)
        for path in sorted((self.root / "apps").glob("*/manifest.json")):
            try:
                app = validate_manifest(json.loads(path.read_text()))
                if app["id"] != path.parent.name:
                    continue
                app["directory"] = str(path.parent)
                apps.append(app)
            except (OSError, ValueError, TypeError):
                continue
        order = self.settings["home_order"]
        return sorted(apps, key=lambda app: order.index(app["id"]) if app["id"] in order else len(order))

    def mounted_roots(self):
        roots = [Path(x) for x in self.settings["media_roots"]]
        # Already-mounted USB media only. Never mount or execute inserted media silently.
        for base in (Path("/media") / os.environ.get("USER", "waldough"), Path("/run/media") / os.environ.get("USER", "waldough")):
            if base.is_dir():
                roots.extend(path for path in base.iterdir() if path.is_dir())
        return list(dict.fromkeys(path.resolve() for path in roots if path.is_dir()))

    def media(self, kind: str):
        extensions = {"videos": {".mp4", ".mkv", ".mov", ".webm", ".m4v", ".avi", ".ts"}, "photos": {".jpg", ".jpeg", ".png", ".webp"}, "packages": {".zip"}}[kind]
        roots = self.mounted_roots()
        if kind == "packages":
            roots.insert(0, self.root / "packages")
        entries, seen = [], set()
        for root in roots:
            for parent, directories, files in os.walk(root, followlinks=False):
                directories[:] = sorted(d for d in directories if not d.startswith("."))
                for name in sorted(files):
                    path = Path(parent) / name
                    if path.suffix.lower() not in extensions or path.is_symlink():
                        continue
                    resolved = str(path.resolve())
                    if resolved not in seen:
                        entries.append({"name": path.stem.replace("_", " "), "path": resolved})
                        seen.add(resolved)
                    if len(entries) >= 2000:
                        return entries
        if kind == "videos":
            entries.extend({"name": item["name"], "path": item["url"]} for item in self.settings["streams"])
        return entries

    def inspect_package(self, package: Path):
        with zipfile.ZipFile(package) as archive:
            infos = archive.infolist()
            if len(infos) > 500 or sum(info.file_size for info in infos) > 20 * 1024 * 1024:
                raise ValueError("App package exceeds the 20 MB / 500-file limit")
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ValueError("Duplicate paths in app package")
            for info in infos:
                mode = info.external_attr >> 16
                if not safe_member(info.filename) or stat.S_ISLNK(mode):
                    raise ValueError("Unsafe path or link in app package")
                if info.flag_bits & 1:
                    raise ValueError("Encrypted packages are unsupported")
            if "manifest.json" not in names:
                raise ValueError("Package needs manifest.json at its root")
            app = validate_manifest(json.loads(archive.read("manifest.json")))
            if app["entry"] not in names or archive.getinfo(app["entry"]).is_dir():
                raise ValueError("App entry is missing")
            return app

    def install(self, package: Path):
        app = self.inspect_package(package)
        # Fully validate and unpack before replacing the currently installed version.
        with tempfile.TemporaryDirectory(prefix=".install-", dir=self.root / "apps") as temp:
            with zipfile.ZipFile(package) as archive:
                archive.extractall(temp)
            target = self.root / "apps" / app["id"]
            backup = self.root / "backups" / f"{app['id']}-{time.time_ns()}"
            if target.exists():
                target.rename(backup)
            try:
                Path(temp).rename(target)
            except OSError:
                if backup.exists():
                    backup.rename(target)
                raise
        if app["id"] not in self.settings["home_order"]:
            self.save(home_order=[*self.settings["home_order"], app["id"]])
        return app

    def uninstall(self, app_id: str):
        if app_id in RESERVED or not re.fullmatch(r"[a-z][a-z0-9-]{1,47}", app_id):
            raise ValueError("Cannot remove a core app")
        target = self.root / "apps" / app_id
        if target.exists():
            target.rename(self.root / "backups" / f"removed-{app_id}-{time.time_ns()}")
        self.save(home_order=[x for x in self.settings["home_order"] if x != app_id],
                  shortcuts=[None if x == app_id else x for x in self.settings["shortcuts"]])
