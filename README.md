# Unlocked TV

An editable, MIT-licensed TV shell for Raspberry Pi, built on Raspberry Pi OS rather than a replacement Linux distribution.
The MVP targets a Pi Zero 2 W and uses Python, Pygame/SDL, mpv, and optional HDMI-CEC.

## Included

- Remote-first Home with Videos, Photos, Clock, and Settings.
- Local video playback and direct HTTP/HTTPS media streams, with pause, seek, volume, and saved playback position.
- Photo slideshows, three themes, editable Home ordering, and six programmable app shortcuts.
- Installable native Python apps with a sample Counter app.
- Atomic settings persistence, retained app backups, and recovery when an app exits or crashes.
- A user service that waits for HDMI and launches the TV interface.

The code, settings, media, and apps remain on the owner's microSD card.
Power down before swapping the microSD card.
USB media is discovered under already-mounted `/media/$USER` or `/run/media/$USER` paths, or through configured folders.
This MVP does not automatically mount unmounted drives, provide a browser/app store, or implement commercial DRM streaming services.
Native app ZIPs are limited to 20 MB and 500 files; media files are not subject to that package limit.

## Development

Python 3.11 or newer is required.
Use a virtual environment on macOS or Linux:

```sh
python3 -m venv .venv
.venv/bin/pip install -e . ruff
.venv/bin/python scripts/make-assets.py
.venv/bin/python -m unlocked_tv run --windowed
```

Asset generation additionally requires FFmpeg on PATH.
The included images and test video are original procedural assets produced by that script.
Video playback requires mpv on PATH.
On the Pi, use the Debian-provided `python3-pygame` instead of installing the development wheel.

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check unlocked_tv scripts tests
.venv/bin/python scripts/test-e2e.py artifacts/local-e2e
```

The E2E script starts the actual GUI and child app processes against temporary user data.
When mpv is available it tests H.264/AAC decoding, pause, seeking, volume, and resume using null audio/video output.
It writes screenshots and a JSON report.
That test cannot verify physical HDMI, speaker output, hardware decoding performance, or a physical remote.

## Controls

| Input | Action |
| --- | --- |
| D-pad / arrow keys | Navigate; Left/Right seek during video |
| Enter | Select; pause/resume video |
| Back / Escape / Backspace | Back; stop an active app or video |
| Home | Home and stop the active app |
| Space / Play-Pause | Pause/resume |
| Volume keys | Volume |
| M | Mute |
| F1 through F6 | Blue, Orange, Green, Red, Yellow, Purple shortcuts |

In Settings, use Left/Right to change Theme or a shortcut assignment.
In Home Order, select an item, move it with Up/Down, then select again to finish.
The six physical buttons can eventually emit F1-F6 through USB/Bluetooth HID firmware.
The printed remote is still a nonfunctional shape prototype.
HDMI-CEC supports navigation and the standard four colored keys when the display supports them; it does not supply six independent colored keys.

## Pi Installation

The existing Pi has Raspberry Pi OS Lite (Debian 13, aarch64), a working Connect session, existing video/input permissions, and user lingering enabled.
This installation preserves that OS and Connect setup.
No sudo password is needed for the user-owned installation path:

```sh
bash scripts/prepare-runtime.sh
bash scripts/install-user.sh
```

The first script downloads dependencies from the Pi's configured authenticated apt repositories and extracts them under `~/.local/opt/unlocked-tv-runtime`.
It does not install system packages or run package maintainer scripts.
This runtime is not maintained automatically by system apt upgrades; rerun the preparation script and verify after dependency updates.
It assumes an existing Raspberry Pi OS kernel, KMS graphics driver, device permissions, and Python interpreter.
Keep the distribution's repositories and package lists current through normal administrator maintenance.

The installer creates timestamped releases under `~/.local/opt/unlocked-tv/releases`, a `current` symlink, and `~/.local/bin/unlocked-tv`.
It enables `unlocked-tv.service` in the existing user's systemd session.
Without HDMI, the service waits instead of opening a display.
With HDMI connected it attempts a fullscreen SDL KMS/DRM session, releasing the display to mpv or a native app when launched.
Physical display acceptance remains required on the actual monitor.

```sh
systemctl --user status unlocked-tv.service
tail -80 ~/.local/share/unlocked-tv/logs/session.log
systemctl --user restart unlocked-tv.service
systemctl --user disable --now unlocked-tv.service
```

The last command stops and disables the prototype without removing files or changing Connect.
For a release rollback after a later update:

```sh
bash ~/.local/opt/unlocked-tv/current/scripts/rollback-user.sh
```

## Customization And Media

State defaults to `~/.local/share/unlocked-tv`, overridable with `--data PATH` or `UNLOCKED_TV_HOME`.

| Path | Contents |
| --- | --- |
| `settings.json` | Theme, Home order, six shortcuts, media folders, streams, volume |
| `media/` | Local videos and photos |
| `packages/` | App ZIPs available to install from Settings |
| `apps/` | Installed native apps |
| `app-data/` | Persistent data for each app |
| `backups/` | Replaced/removed apps and recovered invalid settings |
| `resume/` | mpv saved playback positions |
| `logs/last-app.log` | Most recent child process output |
| `logs/session.log` | Display startup and service diagnostics |

```sh
~/.local/bin/unlocked-tv settings
~/.local/bin/unlocked-tv settings --set '{"theme":"Forest"}'
~/.local/bin/unlocked-tv add-folder /absolute/path/to/mounted/media
~/.local/bin/unlocked-tv add-stream "My Stream" https://example.com/video.mp4
~/.local/bin/unlocked-tv status
```

CLI edits notify the running interface and return it Home.
The control API is a mode-0600 local Unix socket, not a network service.

## Native Apps

Create a ZIP containing `manifest.json` and `main.py` at its root:

```json
{
  "schema_version": 1,
  "id": "counter",
  "name": "Counter",
  "type": "native",
  "runtime": "python3",
  "entry": "main.py",
  "color": "#E0A178"
}
```

```sh
python3 scripts/package-example.py counter.zip
~/.local/bin/unlocked-tv install counter.zip --trust-code
```

Alternatively put the ZIP in `packages/` or a scanned media folder, then choose Settings > Apps > Install App.
Installation requires an explicit confirmation and does not launch the app automatically.
Packages are checked for unsafe paths, links, reserved IDs, and size limits before staged installation.
Apps execute as the owner and are trusted code, not a security sandbox.
Linux child processes cannot gain new privileges, but can access files and network resources available to that user.
Do not install packages from an author you do not trust.

`UNLOCKED_APP_DATA` identifies the app's persistent writable folder.
`UNLOCKED_APP_INPUT=stdin` supplies newline-delimited JSON actions such as `{"action":"right"}` and `{"action":"select"}` on standard input.
Use that input stream rather than processing the same physical keyboard event twice.
Home and Back are handled by the shell and terminate the child, so apps should save ongoing changes and handle SIGTERM.
The sample Counter demonstrates this contract.
App stdout/stderr goes to `logs/last-app.log`.
Custom dependencies must be compatible with the Pi's architecture and runtime; arbitrary desktop or Android apps are not supported.

## Layout

- `unlocked_tv/`: persistence, app lifecycle, input adapters, navigation model, and native interface.
- `scripts/`: runtime preparation, installation, service entry, asset generation, packaging, and E2E checks.
- `examples/counter/`: complete installable app.
- `assets/`: sample media.
- `tests/`: focused persistence, package safety, and navigation tests.
- `artifacts/`: ignored screenshots, transfer files, and validation reports.

## First Monitor Check

Connect a monitor with the Pi powered and wait for Home.
Verify readable full-screen layout, navigation with a USB keyboard or HDMI-CEC remote, and Welcome video audio/playback.
Then verify Back/Home returns from video and an installed Counter app.
Check a real boot with HDMI connected and unplug/replug recovery before treating this as an appliance.
The Zero 2 W's 512 MB memory and codec support constrain app complexity and video formats; hardware playback performance has to be measured on the attached display.
