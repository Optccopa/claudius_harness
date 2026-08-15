import os
import datetime
import inspect
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv

from claudius import tools

import anthropic
import httpx
import questionary as qt
from rich.console import Console
from rich.markdown import Markdown
from rich.theme import Theme

load_dotenv()

stats = {
    "session_input_tokens": 0,
    "session_output_tokens": 0
}

theme = Theme({
    "body":   "#e8e3d8",
    "accent": "#D97757",
    "dim":    "#8a8175",
    "user":   "#b9f2ff",
    "ok":     "#7fb069",
    "warn":   "#d9a75f",
    "err":    "#d9605a",

    "markdown.code": "#D97757"
})

console = Console(theme=theme, highlight=False, width=200)

session = httpx.Client()

class Settings:
    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent.parent.parent

        load_dotenv(self.base_dir / ".env")

        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

        self.model = os.getenv("MODEL") or "claude-sonnet-5"

        self.mode = "manual"

        self.tools_file = Path("tools.py")
        self.system_file = self.base_dir / "SYSTEM.md"

        self.chats_dir = self.base_dir / "chats"
        self.chats_dir.mkdir(exist_ok=True)


settings = Settings()

class Messages:
    def __init__(self):
        self.messages = []

    def sys_prompt(self) -> str:
        now = datetime.datetime.now()

        time = now.strftime("%Y-%m-%d %I:%M %p")

        with open(settings.system_file) as f:
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
        if "/" not in settings.model or source == "anthropic":
            if not settings.anthropic_api_key:
                raise ValueError("Failed loading anthropic api key, set ANTHROPIC_API_KEY in .env")
            
            if not self._anthropic:
                self._anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key)

            return self._anthropic

        elif "/" in settings.model:
            if not settings.openrouter_api_key:
                raise ValueError("Failed loading openrouter api key, set OPENROUTER_API_KEY in .env")
            
            if not self._openrouter:
                self._openrouter = anthropic.Anthropic(api_key=settings.openrouter_api_key, base_url="https://openrouter.ai/api")
                console.print(f"[dim]Loaded {settings.model}[/]")
                
            return self._openrouter

        else:
            raise ValueError(f"Invalid model: {settings.model}, please enter a valid model by using /model or changing the .env file")

client = Client()

class CommandHandler:
    def _model(self):
        console.print(f"[ok]Current model: {settings.model}[/]")
        try:
            r = session.get(
                "https://openrouter.ai/api/v1/models",
                params={"sort": "intelligence-high-to-low"}
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            console.print(f"[err]Failed fetching openrouter models: {e}[/]")

        free, paid = [], []
        for m in r.json()["data"]:
            if m["id"].endswith(":batch"):
                continue
            p = m.get("pricing", {})
            is_free = not any(float(p.get(k) or 0) for k in ("prompt", "completion", "request"))
            (free if is_free else paid).append(m["id"])

        choices = [
            qt.Separator("---Anthropic---"),
            *[qt.Choice(title=m.display_name, value=m.id) for m in client.client("anthropic").models.list()],
            qt.Separator("---Paid---"),
            *[qt.Choice(title=m, value=m) for m in paid[:5]],
            qt.Separator("---Free---"),
            *[qt.Choice(title=m, value=m) for m in free[:5]],
        ]

        settings.model = qt.select("Select a model", choices=choices).ask()

    def _mode(self, args: str | None):
        if args:
            settings.mode = args or "manual"
            console.print(f"[ok]Changed mode to {settings.mode}[/]")
        else:
            console.print(f"[body]Current mode: {settings.mode} (available: 'manual', 'auto')[/]")

    def _tools(self):
        tools = _tools.tools()

        if not tools:
            console.print("[dim]No tools registered[/]")
            return

        width = max(len(t["name"]) for t in tools)
        for t in tools:
            desc = t.get("description") or "Description not found"
            console.print(f"  [body]{t['name']:<{width}}[/]  [dim]{desc}[/]")

    def _save(self, args: str | None):
        messages.save(f"{settings.chats_dir}/chat-{args}.json")
        console.print("[ok]Saved messages[/]")

    def _load(self, args: str | None):
        messages.load(f"{settings.chats_dir}/chat-{args}.json")
        console.print("[ok]Loaded messages[/]")
    
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
            console.print(f"[err]Command not found: {cmd}[/]")

class Assistant:
    def __init__(self):
        self.handler = CommandHandler()

    def chat(self, first: str | None = None):
        while True:
            try:
                if first:
                    user_input, first = first, None
                else:
                    user_input = str(qt.text("you:").ask()).strip()

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
                            for text in stream.text_stream:
                                parts.append(text)
                            final = stream.get_final_message()

                        if parts:
                            console.print(Markdown("".join(parts), style="body"))
                    except KeyboardInterrupt:
                        pass

                    print()
                    if final.stop_reason == "max_tokens":
                        console.print("[warn]    hit max_tokens, reply truncated[/]")

                    if final is None:
                        partial = "".join(parts).strip()
                        if partial:
                            messages.messages.append({
                                "role": "assistant",
                                "content": partial + "\n\n[interrupted]",
                            })
                        else:
                            del messages.messages[snapshot:]
                        console.print("[dim] interrupted[/]")
                        break

                    messages.messages.append({"role": "assistant", "content": final.content})

                    for block in final.content:
                        t = block.type

                        if t == "server_tool_use":
                            if block.name == "web_search":
                                console.print(f"[dim]  ▪ search  {block.input.get('query','')}[/]")
                            continue

                        if t == "web_search_tool_result":
                            n = len(block.content) if isinstance(block.content, list) else 0
                            console.print(f"[dim]    ↳ {n} results[/]")
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
                        console.print(f"[dim]  ▪ {block.name}  {suffix}[/]")

                        try:
                            output = _tools.named_tool_functions[block.name](**block.input, mode=settings.mode)
                            is_error = False
                        except KeyboardInterrupt:
                            output, is_error, aborted = "Interrupted by user.", True, True
                            console.print("\n[err]    \\ tool use interrupted[/]")
                        except TypeError as e:
                            output = f"{e}. Check the tool's input_schema for exact parameter names."
                            is_error = True
                        except Exception as e:
                            output, is_error = f"{type(e).__name__}: {e}", True

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
                console.print(f"[err]{e.message}[/]")
                del messages.messages[snapshot:]

            except anthropic.RateLimitError as e:
                console.print(f"[err]{e.message}[/]")
                del messages.messages[snapshot:]
            
            except anthropic.APIStatusError as e:
                console.print(f"[err]{e.body["error"]["message"]}[/]")
                del messages.messages[snapshot:]
                continue

            if final:
                u = final.usage

                stats['session_input_tokens'] += u.input_tokens
                stats['session_output_tokens'] += u.output_tokens

                cost = (
                    stats['session_input_tokens'] * 2
                    + stats['session_output_tokens'] * 10) / 1_000_000

                console.print(f"[dim]{settings.model} · {settings.mode} · session: ${cost:.3f} ($2, $10)[/]")

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