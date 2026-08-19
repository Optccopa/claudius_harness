from pathlib import Path

import httpx
import questionary as qt

from claudius.tools import tools

from claudius.settings import settings
from claudius.console import console
from claudius.clients import client
from claudius.messages import messages

class CommandHandler:
    def _model(self, args: str):
        console.dim(f"Current model: {settings.model}")

        if args:
            settings.model = args.strip()
            console.success(f"Changed model to {args.strip()}")

        try:
            r = httpx.get(
                f"{settings.openrouter_base_url}/v1/models",
                params={
                    "sort": "intelligence-high-to-low",
                    "min_tool_success_rate": "0.01",
                    "supported_parameters": "tools"
                }
            )

            paid: list[str] | None = None
            free: list[str] | None = None

            if r.status_code == 200:
                free, paid = [], []
                for m in r.json()["data"]:
                    if m["id"].endswith(":batch"):
                        continue

                    p = m.get("pricing", {})
                    is_free = not any(float(p.get(k) or 0) for k in ("prompt", "completion", "request"))
                    if "claude" in m["id"]:
                        continue # Claude models already listed on anthropic endpoint

                    (free if is_free else paid).append(m["id"])
        except httpx.HTTPError as e:
            console.error(f"Failed fetching OpenRouter models {e}")

        try:
            r = httpx.get(
                f"{settings.ollama_base_url}/api/tags"
            )
            if r.status_code == 200:
                ollama = [
                    m["name"] for m in r.json()["models"]
                    if "tools" in m["capabilities"]
                ]
        except httpx.HTTPError as e:
            console.error(f"Failed fetching Ollama models {e}")

        choices = [
            qt.Separator("---Anthropic---"),
            *[qt.Choice(title=m.display_name, value=m.id) for m in client.client("anthropic").models.list()][:5],
            qt.Separator("---Paid---"),
            *[qt.Choice(title=m, value=m) for m in paid[:5]],
            qt.Separator("---Free---"),
            *[qt.Choice(title=m, value=m) for m in free[:5]],
            qt.Separator("---Ollama---"),
            *[qt.Choice(title=m, value=m) for m in ollama[:5]],
        ]

        model = console.select("Select a model", choices=choices)

        if model:
            settings.model = model
            console.success(f"Changed model to {model}")

            try:
                settings.save_key(model=model)
            except Exception as e:
                console.error(f"Had an issue while trying to save the model to settings: {e}")

    def _mode(self, args: str | None):
        if args:
            settings.mode = args or "manual"
            console.success(f"Changed mode to {settings.mode}")
        else:
            console.info(f"Current mode: {settings.mode} (available: 'manual', 'auto')")

    def _tools(self):
        if not tools:
            console.dim("No tools registered")
            return

        width = max(len(t["name"]) for t in tools)
        for t in tools:
            desc = t.get("description") or "Description not found"
            console.info(f"  {t['name']:<{width}}  [dim]{desc}")

    def _save(self, args: str | None):
        messages.save(Path(f"{settings.chats_dir}/chat-{args}.json"))
        console.success("Saved messages")

    def _load(self, args: str | None):
        messages.load(Path(f"{settings.chats_dir}/chat-{args}.json"))
        console.success("Loaded messages")

    def _env(self):
        console.info(f".env file: {settings.env_file.resolve()}")

    def _settings(self):
        console.info(f"settings.json file: {settings.settings_file.resolve()}")

    def parse(self, user_input: str = "/") -> None:
        cmd, _, args = user_input.removeprefix("/").partition(" ")
        cmd = cmd.lower()
        args = args.strip()

        if cmd == "model":
            return self._model(args=args)

        elif cmd == "tools":
            self._tools()

        elif cmd == "save":
            self._save(args=args)

        elif cmd == "load":
            self._load(args=args)

        elif cmd == "mode":
            self._mode(args=args)

        elif cmd == "env":
            self._env()

        elif cmd == "settings":
            self._settings()

        else:
            console.error(f"Command not found: {cmd}")

handler = CommandHandler()