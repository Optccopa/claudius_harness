from pathlib import Path

import questionary as qt

from claudius.clients import models
from claudius.console import console
from claudius.messages import messages
from claudius.settings import settings


class CommandHandler:
    def _model(self, args: str):
        console.dim(f"Current model: {settings.model}")

        if args:
            args = args.strip()
            settings.model = args
            console.success(f"Changed model to {args}")

            try:
                settings.save_key(model=args)
            except Exception as e:
                console.error(f"Had an issue while trying to save the model to settings: {e}")

            return

        choices = [
            qt.Separator("---Anthropic---"),
            *[qt.Choice(title=m, value=m) for m in models.list_anthropic()][:5],
            qt.Separator("---Paid---"),
            *[qt.Choice(title=m, value=m) for m in models.list_openrouter()[0][:5]],
            qt.Separator("---Free---"),
            *[qt.Choice(title=m, value=m) for m in models.list_openrouter()[1][:5]],
            qt.Separator("---Ollama---"),
            *[qt.Choice(title=m, value=m) for m in models.list_ollama()[:5]],
            qt.Separator("---Recents---"),
            *[qt.Choice(title=m, value=m) for m in models.list_recents()[:5]],
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

    def _save(self, args: str | None):
        messages.save(Path(f"{settings.chats_dir}/chat-{args}.json"))
        console.success("Saved messages")

    def _load(self, args: str | None):
        path = Path(f"{settings.chats_dir}/chat-{args}.json")
        if not path.exists():
            console.error(f"No such chat: {path.resolve()}")
            return

        messages.load(path)
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
