# Repository Guidelines

## General

- Never use the em dash; use a plain dash.
- Never add an agent as a commit co-author.
- Never manually edit generated files or CHANGELOG.md.
- In long Markdown documents, put each complete sentence on its own line.
- Prefer quality, simplicity, robustness, and maintainability when making technical decisions.
- Do not add visible UI helper text, captions, subtitles, or descriptions unless requested.
- Reproduce bugs through the user-facing workflow before fixing them.
- Inspect rendered UI carefully and fix relevant visual defects and test failures.

## Project

This is the Unlocked TV Python/Pygame project, separate from the sibling `3d-printer` workspace.
Read README.md for architecture, runtime installation, controls, app packaging, and validation.
Keep application code in `unlocked_tv/`, scripts in `scripts/`, tests in `tests/`, sample apps in `examples/`, and sample media in `assets/`.
Keep local runtimes, device reports, transfer artifacts, and caches untracked.

## Validation

```sh
.venv/bin/ruff check unlocked_tv scripts tests
.venv/bin/python -m unittest discover -s tests -v
bash -n scripts/*.sh
.venv/bin/python scripts/test-e2e.py artifacts/local-e2e
```

Run checks appropriate to the change.
Headless tests do not verify physical HDMI, audio output, or remote hardware.
Distinguish local source changes, Pi deployment, and physical device acceptance in handoffs.
Preserve Raspberry Pi Connect access and existing user data during device work.
