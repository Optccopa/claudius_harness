from pathlib import Path

import questionary as qt

from neptune.clients import models
from neptune.console import console
from neptune.messages import messages
from neptune.settings import settings


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

        choices: list = []

        anthropic_models = models.list_anthropic()

        openrouter_models = models.list_openrouter()

        ollama_models = models.list_ollama()

        recent_models = models.list_recents()

        if anthropic_models:
            choices.extend(
                [
                    qt.Separator("---Anthropic---"),
                    *[qt.Choice(title=m, value=m) for m in anthropic_models[:5]],
                ]
            )

        if openrouter_models[0]:  # paid
            choices.extend(
                [
                    qt.Separator("---Paid---"),
                    *[qt.Choice(title=m, value=m) for m in openrouter_models[0][:5]],
                ]
            )

        if openrouter_models[1]:  # free
            choices.extend(
                [
                    qt.Separator("---Free---"),
                    *[qt.Choice(title=m, value=m) for m in openrouter_models[1][:5]],
                ]
            )

        if ollama_models:
            choices.extend(
                [
                    qt.Separator("---Ollama---"),
                    *[qt.Choice(title=m, value=m) for m in ollama_models[:5]],
                ]
            )

        if recent_models:
            choices.extend(
                [
                    qt.Separator("---Recents---"),
                    *[qt.Choice(title=m, value=m) for m in models.list_recents()[:5]],
                ]
            )

        if not choices:
            console.error("Could not load any model choices.")
            return

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

    def _dir(self):
        console.info(f"neptune directory: {settings.neptune_dir.resolve()}")

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

        elif cmd == "dir":
            self._dir()

        else:
            console.error(f"Command not found: {cmd}")


handler = CommandHandler()
