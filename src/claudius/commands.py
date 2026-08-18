import httpx
import questionary as qt

from claudius.tools import tools

from claudius.settings import settings
from claudius.console import console
from claudius.client import client
from claudius.messages import messages

class CommandHandler:
    def _model(self):
        console.dim(f"Current model: {settings.model}")
        try:
            r = httpx.get(
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

handler = CommandHandler()