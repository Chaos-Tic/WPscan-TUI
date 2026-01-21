import asyncio
import atexit
import json
import os
import shlex
import shutil
import signal
from datetime import datetime
from pathlib import Path

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Footer, Input, Label, OptionList, ProgressBar, RichLog, Static


class WPScanTUI(App):
    """Textual TUI wrapper around the WPScan CLI."""

    CSS = """
Screen {
    background: transparent;
    color: #ffffff;
}

#banner {
    background: transparent;
    padding: 0 2;
    height: 3;
    content-align: left middle;
}

#title { color: #7dd3fc; text-style: bold; }
#subtitle { color: #94a3b8; margin-left: 3; }

#body {
    layout: horizontal;
    height: 1fr;
    padding: 0 1 0 1;
    background: transparent;
}

#left {
    width: 58%;
    min-width: 54;
    padding-right: 1;
    layout: vertical;
    height: 1fr;
}

#control_panel {
    width: 42%;
    min-width: 38;
    max-width: 52;
    height: 1fr;
}

.card {
    background: transparent;
    border: solid #7d8ca3;
    padding: 1;
    margin-bottom: 1;
}

#enum_card {
    padding-bottom: 0;
    height: auto;
    min-height: 4;
}

#stats_card {
    background: transparent;
    border: solid #7d8ca3;
    padding: 1;
    margin-bottom: 0;
}

.pill {
    padding: 0 1;
    border: round #1f2937;
    background: #0b1220;
    color: #e5e7eb;
}
.pill.-accent { border: round #38bdf8; color: #38bdf8; }
.pill.-warn { border: round #f59e0b; color: #fbbf24; }
.pill.-error { border: round #ef4444; color: #fca5a5; }
.pill.-ok { border: round #22c55e; color: #86efac; }

#progress_row {
    height: 2;
    padding: 0 1;
    border: none;
    background: transparent;
    content-align: left middle;
}

ProgressBar {
    width: 1fr;
    color: #22c55e;
    background: rgba(255,255,255,0.08);
}

#log {
    border: none;
    background: transparent;
    margin: 0;
    padding: 0 0 0 0;
    height: 1fr;
    min-height: 14;
}

#history_panel {
    border: solid #7d8ca3;
    background: transparent;
    padding: 1;
    height: 10;
    min-height: 9;
    margin-top: 1;
}

#history_list { height: 7; margin-top: 1; }
#history_hint { color: #cbd5e1; }

OptionList {
    background: transparent;
    color: #e6eaf0;
    border: none;
}

Input, Checkbox {
    margin-bottom: 1;
    background: transparent;
    border: solid #7d8ca3;
    color: #e6eaf0;
}

.section-title {
    color: #e6eaf0;
    text-style: bold;
    margin-top: 0;
    margin-bottom: 0;
}

Button {
    margin-right: 1;
    background: #0b1220;
    color: #e6eaf0;
    text-style: bold;
    border: solid #7d8ca3;
}
Button.-success { border: round #22c55e; color: #22c55e; }
Button.-error { border: round #ef4444; color: #ef4444; }

#status {
    margin-top: 1;
    color: #e6eaf0;
}
    """

    BINDINGS = [
        Binding("ctrl+s", "run_scan", "Run"),
        Binding("ctrl+c", "stop_scan", "Stop"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        # Ensure sane colour support on Wayland/Hyprland terminals.
        os.environ.setdefault("TERM", "xterm-256color")
        if "HYPRLAND_INSTANCE_SIGNATURE" in os.environ:
            os.environ.setdefault("COLORTERM", "truecolor")
        self.process: asyncio.subprocess.Process | None = None
        self.output_task: asyncio.Task | None = None
        self.history: list[dict] = []
        self.current_output: list[str] = []
        self.current_target: str = ""
        self.current_cmd: str = ""
        self.start_time: datetime | None = None
        self.progress: ProgressBar | None = None
        self.progress_label: Static | None = None
        self.status_chip: Static | None = None
        self.elapsed_chip: Static | None = None
        self.code_chip: Static | None = None

        atexit.register(self.clear_history_storage)
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def history_path(self) -> Path:
        return Path.home() / ".local" / "state" / "wpscan-tui" / "history.json"

    def compose(self) -> ComposeResult:
        with Horizontal(id="banner"):
            yield Static("  WPScan TUI", id="title")
            yield Static("Lazy-style controls, stream view, quick flags", id="subtitle")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                with Vertical(id="stats_card"):
                    yield Label("Run status", classes="section-title")
                    with Horizontal():
                        self.status_chip = Static("Idle", classes="pill -accent", expand=False)
                        self.progress = ProgressBar(total=100)
                        self.progress_label = Static("0%", expand=False)
                        yield self.status_chip
                        yield self.progress
                        yield self.progress_label
                    with Horizontal():
                        yield Button("Run", id="run", variant="success")
                        yield Button("Stop", id="stop", variant="error", disabled=True)
                        self.status_label = Static("Ready", id="status")
                        yield self.status_label
                with Vertical(classes="card"):
                    yield Label("Live log", classes="section-title")
                    yield RichLog(id="log", highlight=True, markup=True, wrap=True)
                with Vertical(id="history_panel"):
                    yield Label("Session history", classes="section-title")
                    yield Label("Enter: replay • V: view button • Clear: purge", id="history_hint")
                    yield OptionList(id="history_list")
                    with Horizontal():
                        yield Button("View", id="view_history")
                        yield Button("Clear", id="clear_history", variant="error")
            with VerticalScroll(id="control_panel"):
                with Vertical(classes="card"):
                    yield Label("Target", classes="section-title")
                    yield Input(placeholder="https://example.com", id="target")
                    yield Label("API Token (optional)", classes="section-title")
                    yield Input(password=True, placeholder="token", id="token")
                with Vertical(classes="card", id="enum_card"):
                    yield Label("Enumerate", classes="section-title")
                    yield Checkbox("Users", id="enum_users", value=True)
                    yield Checkbox("Plugins", id="enum_plugins")
                    yield Checkbox("Themes", id="enum_themes")
                with Vertical(classes="card"):
                    yield Label("Flags", classes="section-title")
                    yield Checkbox("Random user-agent", id="random_ua", value=True)
                    yield Checkbox("Verbose output", id="verbose")
                    yield Checkbox("Ignore main redirect", id="ignore_main_redirect")
                    yield Checkbox("Skip DB update (--no-update)", id="no_update", value=True)
                    yield Checkbox("Ignore TLS errors", id="ignore_tls")
                    yield Checkbox("Force even if WP not detected", id="force")
                    yield Checkbox("Plain output (no colour)", id="no_color", value=False)
                with Vertical(classes="card"):
                    yield Label("Extra arguments (advanced)", classes="section-title")
                    yield Input(placeholder="--detection-mode aggressive", id="extra_args")
        yield Footer()

    async def on_mount(self) -> None:
        await self.load_history()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run":
            await self.action_run_scan()
        elif event.button.id == "stop":
            await self.action_stop_scan()
        elif event.button.id == "view_history":
            self.load_selected_history()
        elif event.button.id == "clear_history":
            self.clear_history_storage()
            self.refresh_history_list()

    async def action_run_scan(self) -> None:
        if self.process:
            return

        target_input = self.query_one("#target", Input)
        token_input = self.query_one("#token", Input)
        log = self.query_one(RichLog)
        run_btn = self.query_one("#run", Button)
        stop_btn = self.query_one("#stop", Button)

        target = target_input.value.strip()
        if not target:
            self.set_status("Enter a target URL before running.", error=True)
            self._reset_progress()
            return

        wpscan_path = shutil.which("wpscan")
        if not wpscan_path:
            self.set_status("wpscan not found in PATH. Install it first.", error=True)
            self._reset_progress()
            return

        cmd = [wpscan_path, "--url", target]

        enum_flags = []
        if self.query_one("#enum_users", Checkbox).value:
            enum_flags.append("u")
        if self.query_one("#enum_plugins", Checkbox).value:
            enum_flags.append("p")
        if self.query_one("#enum_themes", Checkbox).value:
            enum_flags.append("t")
        if enum_flags:
            cmd += ["--enumerate", ",".join(enum_flags)]

        if self.query_one("#random_ua", Checkbox).value:
            cmd.append("--random-user-agent")
        if self.query_one("#verbose", Checkbox).value:
            cmd.append("--verbose")
        if self.query_one("#ignore_main_redirect", Checkbox).value:
            cmd.append("--ignore-main-redirect")
        if self.query_one("#no_update", Checkbox).value:
            cmd.append("--no-update")
        if self.query_one("#ignore_tls", Checkbox).value:
            cmd.append("--disable-tls-checks")
        if self.query_one("#force", Checkbox).value:
            cmd.append("--force")
        if self.query_one("#no_color", Checkbox).value:
            cmd += ["--format", "cli-no-colour"]

        extra = self.query_one("#extra_args", Input).value.strip()
        if extra:
            try:
                cmd += shlex.split(extra)
            except ValueError:
                self.set_status("Extra arguments malformed (quotes?).", error=True)
                self._reset_progress()
                return

        token = token_input.value.strip()
        if token:
            cmd += ["--api-token", token]

        self.current_target = target
        self.current_cmd = " ".join(cmd)
        self.current_output = []
        self.start_time = datetime.now()
        self._update_progress(0, "Ready")
        self._update_chips(status="running", code="-")

        log.clear()
        log.write(f"[bold cyan]$ {' '.join(cmd)}[/bold cyan]")
        self.current_output.append(f"$ {' '.join(cmd)}")
        self.set_status("Scan running…")
        run_btn.disabled = True
        stop_btn.disabled = False

        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=Path.cwd(),
            )
        except FileNotFoundError:
            self.set_status("wpscan executable not found.", error=True)
            run_btn.disabled = False
            stop_btn.disabled = True
            return

        self.output_task = asyncio.create_task(self._stream_output(self.process, log))

    async def action_stop_scan(self) -> None:
        if not self.process:
            return
        self.set_status("Stopping scan…")
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=5)
        except asyncio.TimeoutError:
            self.process.kill()
        self._update_progress(0, "Cancelled")
        self._update_chips(status="cancelled", code="-")
        await self._finish_scan(message="Scan cancelled.", exit_code=self.process.returncode)

    async def _stream_output(self, process: asyncio.subprocess.Process, log: RichLog) -> None:
        assert process.stdout is not None
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            text = line.decode(errors="ignore").rstrip()
            log.write(text)
            self.current_output.append(text)
            if self.start_time:
                elapsed = (datetime.now() - self.start_time).total_seconds()
                pct = min(95, int(min(elapsed, 240) / 240 * 95))
                self._update_progress(pct, f"Running • {self._elapsed_text()}")
                self._update_chips(status="running")
        await process.wait()
        await self._finish_scan(exit_code=process.returncode)

    async def _finish_scan(self, message: str | None = None, exit_code: int | None = None) -> None:
        current = asyncio.current_task()
        if self.output_task and self.output_task is not current and not self.output_task.done():
            self.output_task.cancel()
        self.output_task = None
        self.process = None

        run_btn = self.query_one("#run", Button)
        stop_btn = self.query_one("#stop", Button)
        run_btn.disabled = False
        stop_btn.disabled = True

        final = message or "Scan finished."
        if exit_code is not None and exit_code != 0:
            final = f"Scan finished with exit code {exit_code}"
            self.set_status(final, error=True)
            self._update_progress(100, f"Failed • {self._elapsed_text()}")
            self._update_chips(status="failed", code=exit_code)
        else:
            self.set_status(final)
            if self.start_time:
                self._update_progress(100, f"Done • {self._elapsed_text()}")
            self._update_chips(status="done", code=exit_code if exit_code is not None else 0)
        if self.current_target and self.current_output:
            self.add_history_entry(
                target=self.current_target,
                command=self.current_cmd,
                exit_code=exit_code,
                output=self.current_output,
            )
        self.start_time = None

    def set_status(self, text: str, *, error: bool = False) -> None:
        prefix = "[red]" if error else "[green]"
        self.status_label.update(f"{prefix}{text}")
        if error:
            self._update_chips(status="error")

    def _elapsed_text(self) -> str:
        if not self.start_time:
            return "00:00"
        delta = datetime.now() - self.start_time
        mins, secs = divmod(int(delta.total_seconds()), 60)
        return f"{mins:02d}:{secs:02d}"

    def _update_chips(self, status: str | None = None, code: int | str | None = None) -> None:
        if status and self.status_chip:
            label = status.lower()
            css = "-accent"
            if label in {"running", "busy"}:
                css = "-warn"
            elif label in {"error", "failed"}:
                css = "-error"
            elif label in {"done", "ok"}:
                css = "-ok"
            self.status_chip.update(f"Status: {status}")
            self.status_chip.set_class(False, "-accent")
            self.status_chip.set_class(False, "-warn")
            self.status_chip.set_class(False, "-error")
            self.status_chip.set_class(False, "-ok")
            self.status_chip.set_class(True, css)
        if self.elapsed_chip:
            self.elapsed_chip.update(f"Elapsed {self._elapsed_text()}")
        if code is not None and self.code_chip:
            self.code_chip.update(f"Exit: {code if code != -1 else '…'}")

    def _update_progress(self, percent: int | None = None, label: str | None = None) -> None:
        if not self.progress or not self.progress_label:
            return
        if percent is not None:
            percent = max(0, min(100, percent))
            self.progress.update(total=100, progress=percent)
        self.progress_label.update(label or f"Elapsed {self._elapsed_text()}")

    def _reset_progress(self, label: str = "Idle") -> None:
        if not self.progress:
            return
        self.progress.update(total=100, progress=0)
        if self.progress_label:
            self.progress_label.update(label)

    async def on_key(self, event: events.Key) -> None:
        if event.key == "escape" and self.process:
            await self.action_stop_scan()

    async def on_exit(self) -> None:
        if self.process:
            await self.action_stop_scan()
        self.clear_history_storage()
        try:
            lst = self.query_one("#history_list", OptionList)
            lst.clear_options()
        except Exception:
            pass

    def _handle_signal(self, signum, frame) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()
        self.clear_history_storage()
        raise SystemExit(0)

    async def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.load_selected_history()

    # --- History helpers ---
    def add_history_entry(self, target: str, command: str, exit_code: int | None, output: list[str]) -> None:
        entry = {
            "target": target,
            "command": command,
            "exit_code": exit_code,
            "output": output,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        self.history.insert(0, entry)
        self.history = self.history[:50]
        self.save_history()
        self.refresh_history_list()

    def refresh_history_list(self) -> None:
        lst = self.query_one("#history_list", OptionList)
        lst.clear_options()
        for idx, item in enumerate(self.history, start=1):
            status = "ok" if (item.get("exit_code") in (None, 0)) else f"err {item.get('exit_code')}"
            target = item.get("target", "")[:50]
            label = f"{idx:02d} • {item.get('timestamp','')} • {status} • {target}"
            lst.add_option(label)

    def load_selected_history(self) -> None:
        lst = self.query_one("#history_list", OptionList)
        if lst.option_count == 0 or lst.highlighted is None:
            return
        idx = lst.highlighted
        if idx >= len(self.history):
            return
        item = self.history[idx]
        log = self.query_one(RichLog)
        log.clear()
        for line in item.get("output", []):
            log.write(line)
        self.set_status(f"Showing saved scan: {item.get('target','')}")

    async def load_history(self) -> None:
        path = self.history_path()
        if path.exists():
            try:
                data = json.loads(path.read_text())
                if isinstance(data, list):
                    self.history = data
            except Exception:
                self.history = []
        self.refresh_history_list()

    def save_history(self) -> None:
        path = self.history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(json.dumps(self.history, indent=2))
        except Exception:
            pass

    def clear_history_storage(self) -> None:
        """Remove history file and in-memory entries when quitting."""
        self.history = []
        path = self.history_path()
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            lst = self.query_one("#history_list", OptionList)
            lst.clear_options()
        except Exception:
            pass


def run() -> None:
    WPScanTUI().run()


if __name__ == "__main__":
    run()
