"""Owner-facing command line, sharing the same settings and app installer as the UI."""
import argparse
import json
from pathlib import Path
import sys

from .runtime import socket_request
from .store import Store


def main():
    parser = argparse.ArgumentParser(prog="unlocked-tv")
    parser.add_argument("--data", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--headless", action="store_true")
    run.add_argument("--windowed", action="store_true")
    run.add_argument("--kiosk", action="store_true")
    control = commands.add_parser("control")
    control.add_argument("request", help="JSON control request")
    commands.add_parser("status")
    commands.add_parser("apps")
    install = commands.add_parser("install")
    install.add_argument("package", type=Path)
    install.add_argument("--trust-code", action="store_true", help="Allow this app's Python code to run as your user")
    uninstall = commands.add_parser("remove")
    uninstall.add_argument("id")
    settings = commands.add_parser("settings")
    settings.add_argument("--set", dest="changes", help="JSON object with settings to change")
    media = commands.add_parser("add-folder")
    media.add_argument("path", type=Path)
    stream = commands.add_parser("add-stream")
    stream.add_argument("name")
    stream.add_argument("url")
    args = parser.parse_args()
    store = Store(args.data)
    def reload_running():
        try:
            socket_request(store.root / "control.sock", {"action": "reload"})
        except OSError:
            pass
    try:
        if args.command == "run":
            from .ui import run
            run(store, args.headless, args.windowed, args.kiosk)
            return
        if args.command in {"control", "status"}:
            result = socket_request(store.root / "control.sock", json.loads(args.request) if args.command == "control" else {"action": "status"}, timeout=5)
        elif args.command == "apps":
            result = store.apps()
        elif args.command == "install":
            if not args.trust_code:
                raise ValueError("Installing executable apps requires --trust-code")
            result = store.install(args.package)
            reload_running()
        elif args.command == "remove":
            store.uninstall(args.id)
            reload_running()
            result = {"removed": args.id}
        elif args.command == "settings":
            if args.changes:
                store.save(**json.loads(args.changes))
                reload_running()
            result = store.settings
        elif args.command == "add-folder":
            path = args.path.expanduser().resolve()
            if not path.is_dir():
                raise ValueError("Media folder does not exist")
            store.save(media_roots=list(dict.fromkeys([*store.settings["media_roots"], str(path)])))
            reload_running()
            result = store.settings
        else:
            store.save(streams=[*store.settings["streams"], {"name": args.name, "url": args.url}])
            reload_running()
            result = store.settings
        print(json.dumps(result, indent=2))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
