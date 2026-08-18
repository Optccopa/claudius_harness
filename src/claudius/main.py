"""
Main CLI assistant, run with `claudius "hello"`
"""
import argparse
import datetime
import inspect
import json
import os
from pathlib import Path
import shutil

import anthropic
from dotenv import load_dotenv
import httpx
from platformdirs import user_data_dir
import questionary as qt
from rich.console import Console as RichConsole
from rich.markdown import Markdown
from rich.theme import Theme

from claudius import tools

SILENT = [
    "read_file",
    "ask_user_question"
]

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

stats = {
    "session_input_tokens": 0,
    "session_output_tokens": 0
}

session = httpx.Client()

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


    def renderable(self, msg, **kwargs):  self._rich.print(msg, **kwargs)

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

class Settings:
    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent.parent.parent

        self.claudius_dir = Path(user_data_dir(".claudius", appauthor=False))

        self.claudius_dir.mkdir(exist_ok=True, parents=True)

        self.env_file = self.claudius_dir / ".env"

        if not self.env_file.exists():
            example = self.base_dir / "example.env"
            self.env_file.write_text(
                example.read_text(encoding="utf-8") if example.exists()
                else "ANTHROPIC_API_KEY=\nOPENROUTER_API_KEY=\nMODEL=claude-sonnet-5\n",
                encoding="utf-8",
            )
            raise SystemExit(
                f"{self.env_file} must have either OPENROUTER_API_KEY or ANTHROPIC_API_KEY defined"
            )

        load_dotenv(self.env_file)

        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

        self.model = os.getenv("MODEL") or "claude-sonnet-5"

        self.mode = "manual"

        self.system_file = self.base_dir / "SYSTEM.md"

        self.chats_dir = self.claudius_dir / "chats"

        self.chats_dir.mkdir(exist_ok=True, parents=True)


settings = Settings()

class Messages:
    def __init__(self):
        self.messages = []

    def sys_prompt(self) -> str:
        now = datetime.datetime.now()

        time = now.strftime("%Y-%m-%d %I:%M %p")

        with open(settings.system_file, encoding="utf-8") as f:
            system = f.read()

        system = system.replace("{model}", settings.model)
        system = system.replace("{time}", time)
        system = system.replace("{dir}", str(Path().absolute().resolve()))

        return system

    def save(self, path: Path) -> None:
        def to_dict(b):
            return b if isinstance(b, dict) else b.model_dump(mode="json", exclude_none=True)

        out = [
            {"role": m["role"],
            "content": m["content"] if isinstance(m["content"], str)
                        else [to_dict(b) for b in m["content"]]}
            for m in self.messages
        ]

        path = Path(path)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def save_exc(self, exc: str, snapshot: int):
        """Saves and deletes current context"""
        now = datetime.datetime.now()
        path = Path(f"{settings.chats_dir}/chat-{exc}-{now.strftime("%H-%M-%S")}.json")

        self.save(path)

        del messages.messages[snapshot:]

        console.success(f"Saved messages as {path.absolute()}")

    def load(self, path: Path):
        self.messages = json.loads(Path(path).read_text())

class Tools:
    def __init__(self):
        self.named_tool_functions = {
            name: fn
            for name, fn in inspect.getmembers(tools, inspect.isfunction)
            if fn.__module__ == tools.__name__ and not name.startswith("_")
        }

    def tools(self) -> list:
        return tools.tools

messages = Messages()

_tools = Tools()

class Client:
    def __init__(self):
        self._anthropic = None
        self._openrouter = None

    def client(self, source: str | None = None):
        if source == "anthropic" or "/" not in settings.model:
            if not settings.anthropic_api_key:
                raise ValueError("Failed loading anthropic api key, set ANTHROPIC_API_KEY in .env")

            if not self._anthropic:
                self._anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key)

            return self._anthropic

        elif "/" in settings.model:
            if not settings.openrouter_api_key:
                raise ValueError("Failed loading openrouter api key, set OPENROUTER_API_KEY in .env")

            if not self._openrouter:
                self._openrouter = anthropic.Anthropic(
                    api_key=settings.openrouter_api_key,
                    base_url="https://openrouter.ai/api",
                    max_retries=0
                )

                console.dim(f"Loaded {settings.model}")

            return self._openrouter

        else:
            raise ValueError(f"Invalid model: {settings.model}, please enter a valid model by using /model or changing the .env file")

client = Client()

class CommandHandler:
    def _model(self):
        console.dim(f"Current model: {settings.model}")
        try:
            r = session.get(
                "https://openrouter.ai/api/v1/models",
                params={
                    "sort": "intelligence-high-to-low",
                    "min_tool_success_rate": "0.01",
                    "supported_parameters": "tools"
                }
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            console.error(f"Failed fetching openrouter models: {e}")
            return

        free, paid = [], []
        for m in r.json()["data"]:
            if m["id"].endswith(":batch"):
                continue
            p = m.get("pricing", {})
            is_free = not any(float(p.get(k) or 0) for k in ("prompt", "completion", "request"))
            if "claude" in m["id"]:
                continue # Claude models already listed on anthropic endpoint
            (free if is_free else paid).append(m["id"])

        choices = [
            qt.Separator("---Anthropic---"),
            *[qt.Choice(title=m.display_name, value=m.id) for m in client.client("anthropic").models.list()][:5],
            qt.Separator("---Paid---"),
            *[qt.Choice(title=m, value=m) for m in paid[:5]],
            qt.Separator("---Free---"),
            *[qt.Choice(title=m, value=m) for m in free[:5]],
        ]

        settings.model = console.select("Select a model", choices=choices)

    def _mode(self, args: str | None):
        if args:
            settings.mode = args or "manual"
            console.success(f"Changed mode to {settings.mode}")
        else:
            console.info(f"Current mode: {settings.mode} (available: 'manual', 'auto')")

    def _tools(self):
        tools = _tools.tools()

        if not tools:
            console.dim("No tools registered")
            return

        width = max(len(t["name"]) for t in tools)
        for t in tools:
            desc = t.get("description") or "Description not found"
            console.info(f"  {t['name']:<{width}}  [dim]{desc}")

    def _save(self, args: str | None):
        messages.save(f"{settings.chats_dir}/chat-{args}.json")
        console.success("Saved messages")

    def _load(self, args: str | None):
        messages.load(f"{settings.chats_dir}/chat-{args}.json")
        console.success("Loaded messages")

    def parse(self, user_input: str = "/") -> bool:
        cmd, _, args = user_input.removeprefix("/").partition(" ")
        cmd = cmd.lower()
        args = args.strip()

        if cmd == "model":
            return self._model()

        elif cmd == "tools":
            self._tools()

        elif cmd == "save":
            self._save(args=args)

        elif cmd == "load":
            self._load(args=args)

        elif cmd == "mode":
            self._mode(args=args)

        else:
            console.error(f"Command not found: {cmd}")

class Assistant:
    def __init__(self):
        self.handler = CommandHandler()

    def chat(self, first: str | None = None):
        while True:
            try:
                if first:
                    user_input, first = first, None
                else:
                    user_input = console.input() # Default 'you:'

                if user_input is None:
                    break

                if user_input.startswith("/"):
                    self.handler.parse(user_input)
                    continue
            except (EOFError, KeyboardInterrupt):
                break

            snapshot = len(messages.messages)

            messages.messages.append({"role": "user", "content": user_input})

            try:
                while True:
                    parts = []
                    final = None
                    try:
                        with client.client().messages.stream(
                            model=settings.model,
                            max_tokens=8192,
                            system=messages.sys_prompt(),
                            tools=_tools.tools(),
                            messages=messages.messages
                        ) as stream:
                            buf = ""
                            code_lines = None
                            for text in stream.text_stream:
                                parts.append(text)
                                buf += text
                                while "\n" in buf:
                                    line, _, buf = buf.partition("\n")
                                    fence = line.strip().startswith("```")
                                    if code_lines is None:
                                        if fence:
                                            code_lines = [line]
                                            console.raw_line(line)
                                        else:
                                            console.line(line)
                                    else:
                                        code_lines.append(line)
                                        console.raw_line(line)
                                        if fence:
                                            console.clear_lines(len(code_lines))
                                            console.renderable(Markdown("\n".join(code_lines), style="body"))
                                            code_lines = None
                                console.partial(buf)
                            if code_lines is not None:
                                code_lines.append(buf)
                                console.raw_line(buf)
                                console.clear_lines(len(code_lines))
                                console.renderable(Markdown("\n".join(code_lines), style="body"))
                            elif buf:
                                console.line(buf)
                            else:
                                print()
                            final = stream.get_final_message()
                    except KeyboardInterrupt:
                        pass

                    if final is None:
                        partial = "".join(parts).strip()
                        if partial:
                            messages.messages.append({
                                "role": "assistant",
                                "content": partial + "\n\n[interrupted]",
                            })
                        else:
                            del messages.messages[snapshot:]
                        console.dim(" interrupted")
                        break

                    if final.stop_reason == "max_tokens":
                        console.warn("    hit max_tokens, reply truncated")

                    messages.messages.append({"role": "assistant", "content": final.content})

                    for block in final.content:
                        t = block.type

                        if t == "server_tool_use":
                            if block.name == "web_search":
                                console.dim(f"  ▪ search  {block.input.get('query','')}")
                            continue

                        if t == "web_search_tool_result":
                            n = len(block.content) if isinstance(block.content, list) else 0
                            console.dim(f"    ↳ {n} results")
                            continue

                    if final.stop_reason != "tool_use":
                        break

                    results = []
                    aborted = False
                    for block in final.content:
                        t = block.type

                        if t == "thinking":
                            continue

                        if t != "tool_use":
                            continue

                        if aborted:
                            results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": "interrupted by user.",
                                "is_error": True,
                            })
                            continue

                        args = ", ".join(f"{k}={v!r}" for k, v in block.input.items())
                        suffix = f"with {args[:80]}" if block.input else ""
                        console.dim(f"  ▪ {block.name} {suffix}")

                        try:
                            output = _tools.named_tool_functions[block.name](**block.input, mode=settings.mode)
                            is_error = False
                        except KeyboardInterrupt:
                            output, is_error, aborted = "Interrupted by user.", True, True
                        except TypeError as e:
                            output = f"{e}. Check the tool's input_schema for exact parameter names."
                            is_error = True
                        except Exception as e:
                            output, is_error = f"{type(e).__name__}: {e}", True

                        if block.name not in SILENT: # Ignore large dumps from readfile / reprinting ask_user_question
                            console.tool_result(output, is_error)

                        results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(output),
                            "is_error": is_error,
                        })

                    messages.messages.append({"role": "user", "content": results})

                    if aborted:
                        break

                print()

            except anthropic.APIConnectionError as e:
                console.error(e.message)
                messages.save_exc(type(e).__name__, snapshot)

            except anthropic.RateLimitError as e:
                console.error(e.message)
                messages.save_exc(type(e).__name__, snapshot)

            except anthropic.APIStatusError as e:
                console.error(e.body["error"]["message"])
                messages.save_exc(type(e).__name__, snapshot)
                continue

            except ValueError as e:
                console.error(e)
                messages.save_exc(type(e).__name__, snapshot)
                continue

            if final:
                u = final.usage

                stats['session_input_tokens'] += u.input_tokens
                stats['session_output_tokens'] += u.output_tokens

                cost = (
                    stats['session_input_tokens'] * 2
                    + stats['session_output_tokens'] * 10) / 1_000_000

                console.dim(f"{settings.model} · {settings.mode} · session: ${cost:.3f} ($2, $10)")

def main():
    parser = argparse.ArgumentParser(
        prog="claudius",
        description="Runs the claudius cli (claudecode like)"
    )
    parser.add_argument("user_input", nargs="?")
    args = parser.parse_args()
    Assistant().chat(args.user_input)

if __name__ == "__main__":
    main()
