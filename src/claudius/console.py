import shutil

import questionary as qt
from rich.console import Console as RichConsole
from rich.theme import Theme
from rich.markdown import Markdown

COLORS = {
    "body":   "#e8e3d8",
    "accent": "#D97757",
    "dim":    "#8a8175",
    "user":   "#b9f2ff",
    "ok":     "#7fb069",
    "warn":   "#d9a75f",
    "err":    "#d9605a",

    "markdown.code": "#D97757"
}

class Console:
    def __init__(self):
        self._rich = RichConsole(
            theme=Theme(COLORS),
            highlight=False,
            width=min(shutil.get_terminal_size((80, 24)).columns, 100)
        )

    def _print(self, *values, sep: str = " ", end: str = "\n", style: str = "body") -> None:
        self._rich.print(*values, sep=sep, end=end, style=style)

    def input(self, prompt: str = "you:") -> str | None:
        try:
            return qt.text(prompt).unsafe_ask().strip()
        except (KeyboardInterrupt, EOFError):
            return None

    def select(self, prompt: str, choices: list):
        try:
            return qt.select(prompt, choices=choices).unsafe_ask()
        except (KeyboardInterrupt, EOFError):
            return None

    def confirm(self, prompt: str, default: bool = True) -> bool:
        try:
            return qt.confirm(prompt, default=default).unsafe_ask()
        except (KeyboardInterrupt, EOFError):
            return None

    def renderable(self, msg, **kwargs):
        self._rich.print(msg, **kwargs)

    def partial(self, text: str) -> None:
        width = self._rich.width
        show = text if len(text) < width else "…" + text[-(width - 2):]
        self._rich.file.write(f"\r\x1b[K{show}")
        self._rich.file.flush()

    def line(self, text: str) -> None:
        self._rich.file.write("\r\x1b[K")
        self._rich.print(Markdown(text, style="body"))

    def raw_line(self, text: str) -> None:
        self._rich.file.write("\r\x1b[K")
        self._rich.print(text, style="body", markup=False, highlight=False)

    def clear_lines(self, n: int) -> None:
        for _ in range(n):
            self._rich.file.write("\x1b[1A\x1b[K")
        self._rich.file.flush()

    def tool_result(self, output, is_error: bool = False,
                     max_lines: int = 12, max_chars: int = 2000) -> None:
        text = str(output).strip()
        if not text:
            return

        if len(text) > max_chars:
            text = text[:max_chars] + f"\n… [{len(text) - max_chars} more chars]"

        lines = text.splitlines()
        if len(lines) > max_lines:
            hidden = len(lines) - max_lines
            lines = lines[:max_lines] + [f"… [{hidden} more lines]"]

        style = "err" if is_error else "dim"
        for line in lines:
            self._print(f"    {line}", style=style)

    # semantics
    def info(self, msg):    self._print(msg, style="body")
    def success(self, msg): self._print(msg, style="ok")
    def warn(self, msg):    self._print(msg, style="warn")
    def error(self, msg):   self._print(msg, style="err")
    def dim(self, msg):     self._print(msg, style="dim")

console = Console()