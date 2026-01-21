import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, Footer, Input, Label, OptionList, RichLog, Static
from textual.widgets.option_list import Option


class WPScanTUI(App):
    """Textual TUI wrapper around the WPScan CLI."""

    CSS = """
Screen {
    background: transparent;
    color: inherit;
}

#banner {
    background: transparent;
    border: tall grey35;
    padding: 0 2;
    height: 3;
    content-align: left middle;
}

#title {
    color: inherit;
    text-style: bold;
}

#subtitle {
    color: inherit;
    margin-left: 3;
}

#body {
    layout: horizontal;
    height: 1fr;
    padding: 1 1 0 1;
    border-top: tall grey20;
}

#right {
    width: 58%;
    min-width: 48;
    padding-left: 1;
    padding-right: 0;
}

#form {
    width: 42%;
    min-width: 40;
    max-width: 54;
    padding: 1 2;
    border: tall grey35;
    background: transparent;
}

#log {
    border: tall grey35;
    background: transparent;
    margin: 0;
    padding: 1 1 0 1;
}

#history_panel {
    border: tall grey35;
    background: transparent;
    padding: 1;
    height: 14;
    margin-top: 1;
}

#history_list {
    height: 10;
    margin-top: 1;
}

Input, Checkbox {
    margin-bottom: 1;
}

.section-title {
    color: inherit;
    text-style: bold;
    margin-top: 1;
    margin-bottom: 0;
}

Button {
    margin-right: 1;
    background: transparent;
    color: inherit;
    text-style: bold;
    border: tall grey30;
}

Button.-success {
    border: tall green;
}

Button.-error {
    border: tall red;
}

#status {
    margin-top: 1;
    color: inherit;
}
    """

    BINDINGS = [
        Binding("ctrl+s", "run_scan", "Run"),
        Binding("ctrl+c", "stop_scan", "Stop"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.process: asyncio.subprocess.Process | None = None
        self.output_task: asyncio.Task | None = None
        self.history: list[dict] = []
        self.current_output: list[str] = []
        self.current_target: str = ""
        self.current_cmd: str = ""

    def history_path(self) -> Path:
        return Path.home() / ".local" / "state" / "wpscan-tui" / "history.json"

    def compose(self) -> ComposeResult:
        with Horizontal(id="banner"):
            yield Static("  WPScan TUI", id="title")
            yield Static("Lazy-style controls, stream view, quick flags", id="subtitle")
        with Horizontal(id="body"):
            with Vertical(id="form"):
                yield Label("WPScan Target", classes="section-title")
                yield Input(placeholder="https://example.com", id="target")
                yield Label("API Token (optional)", classes="section-title")
                yield Input(password=True, placeholder="token", id="token")

                yield Label("Enumerate", classes="section-title")
                yield Checkbox("Users (-e u)", id="enum_users", value=True)
                yield Checkbox("Plugins (-e p)", id="enum_plugins")
                yield Checkbox("Themes (-e t)", id="enum_themes")

                yield Label("Flags", classes="section-title")
                yield Checkbox("Random user-agent", id="random_ua", value=True)
                yield Checkbox("Verbose output", id="verbose")
                yield Checkbox("Ignore main redirect (--ignore-main-redirect)", id="ignore_main_redirect")
                yield Checkbox("Skip DB update (--no-update)", id="no_update", value=True)
                yield Checkbox("Ignore TLS errors", id="ignore_tls")
                yield Checkbox("Force even if WP not detected", id="force")
                yield Checkbox("Plain output (no colour)", id="no_color", value=False)

                yield Label("Extra arguments (advanced)", classes="section-title")
                yield Input(placeholder="--detection-mode aggressive", id="extra_args")

                with Horizontal():
                    yield Button("Run Scan", id="run", variant="success")
                    yield Button("Stop", id="stop", variant="error", disabled=True)

                self.status_label = Static("Ready.", id="status")
                yield self.status_label

            with Vertical(id="right"):
                yield RichLog(id="log", highlight=True, markup=True, wrap=True)
                with Vertical(id="history_panel"):
                    yield Label("History (select and Enter to view)", classes="section-title")
                    yield OptionList(id="history_list")
                    with Horizontal():
                        yield Button("View", id="view_history")
                        yield Button("Clear", id="clear_history", variant="error")
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
            self.history = []
            self.save_history()
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
            return

        wpscan_path = shutil.which("wpscan")
        if not wpscan_path:
            self.set_status("wpscan not found in PATH. Install it first.", error=True)
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
            cmd += extra.split()

        token = token_input.value.strip()
        if token:
            cmd += ["--api-token", token]

        self.current_target = target
        self.current_cmd = " ".join(cmd)
        self.current_output = []

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
        else:
            self.set_status(final)
        if self.current_target and self.current_output:
            self.add_history_entry(
                target=self.current_target,
                command=self.current_cmd,
                exit_code=exit_code,
                output=self.current_output,
            )

    def set_status(self, text: str, *, error: bool = False) -> None:
        prefix = "[red]" if error else "[green]"
        self.status_label.update(f"{prefix}{text}")

    async def on_key(self, event: events.Key) -> None:
        if event.key == "escape" and self.process:
            await self.action_stop_scan()

    async def on_exit(self) -> None:
        if self.process:
            await self.action_stop_scan()

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
        for item in self.history:
            status = "ok" if (item.get("exit_code") in (None, 0)) else f"err {item.get('exit_code')}"
            label = f"{item.get('timestamp','')} | {status} | {item.get('target','')}"
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


def run() -> None:
    WPScanTUI().run()


if __name__ == "__main__":
    run()
