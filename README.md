# WPScan TUI

![WPScan TUI](image_readme_01.png)

Textual TUI inspired by “lazy*” tools to run WPScan comfortably: forms, handy presets, colored output, and session history.

## Requirements
- WPScan available in `PATH` (Arch: `paru -S wpscan` or `yay -S wpscan`).
- Python ≥ 3.10.
- For isolated install: `pipx` (recommended) or a virtualenv.

## Installation
Arch enforces PEP 668 (“externally managed”); avoid global `pip install .`. To always get the latest GitHub version, install via pipx from git.

```bash
# Option 1 – latest via pipx from GitHub
pipx install git+https://github.com/Chaos-Tic/WPscan-TUI.git

# Option 2 – pipx from local clone
pipx install .

# Option 3 – local virtualenv
python -m venv .venv
source .venv/bin/activate
pip install .

# Option 4 – system (not recommended)
pip install --break-system-packages .
```

## Run
```bash
wpscan-tui
```

### Shortcuts
- `Ctrl+S`: start scan
- `Ctrl+C`: stop current scan
- `Ctrl+Q`: quit (purges history)
- Enter on a history row: reload output into the log

## Main features
- Fields for target (`--url`) and API token.
- Checkboxes ready to use:
  - Enumerate users / plugins / themes (`-e u,p,t`).
  - Random user-agent, verbose, force, ignore TLS errors, ignore main redirect (`--ignore-main-redirect`).
  - DB update disabled by default (`--no-update`).
  - Colored output or plain mode.
- “Extra arguments” field to pass any WPScan flag (e.g. `--detection-mode aggressive`).
- Live colored log (stdout+stderr merged) with status chips and progress bar.
- Session history (50 max) stored at `~/.local/state/wpscan-tui/history.json`; auto-purged on exit or via Clear.
- Wayland / Hyprland: works in terminal; if colors look limited, export `COLORTERM=truecolor` before launching.
- Clear status feedback (success / exit code in red if non-zero).

## Example workflow
1. Enter target URL (e.g., `https://example.com`).
2. Keep “No update” checked for a fast start.
3. Check “Ignore main redirect” if the domain redirects elsewhere.
4. Enable “Verbose” or add `--detection-mode aggressive` in “Extra arguments” if needed.
5. `Ctrl+S` to launch; watch the log on the left.
6. After completion, pick the history row and hit Enter to replay output.

## Troubleshooting
- `wpscan not found`: install WPScan and ensure `PATH`.
- PEP 668 / “externally-managed”: use pipx or a venv (see Installation).
- Non-zero exit: status shows “Scan finished with exit code X”; check log for details.
- Color issues: enable “Plain output”.

## Development
```bash
pip install -e .
textual run --dev wpscan_tui.app:WPScanTUI
```
WPScan runs fine outside devserver; live reload helps styling.

## License
MIT.
