import json
import os
from pathlib import Path

from dotenv import load_dotenv
from platformdirs import user_data_dir


class Settings:
    def __init__(self):
        self.neptune_dir = Path(user_data_dir(".neptune", appauthor=False))

        self.cwd = Path().resolve()

        self.neptune_dir.mkdir(exist_ok=True, parents=True)

        self.settings_file = self.neptune_dir / "settings.json"
        self._print_for_settings_file()

        self.env_file = self.neptune_dir / ".env"
        self._exit_for_env_file()

        load_dotenv(self.env_file)

        self.claude_file = self.cwd / "CLAUDE.md"

        # most recently sent filled sys prompt
        self.debug_dir = self.neptune_dir / "debug"
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        self.debug_system_file = self.debug_dir / "sysprompt.md"

        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

        self.model: str = self.load()["model"]
        self.mode = "manual"

        self.system_file = Path(__file__).resolve().parent / "SYSTEM.md"

        self.chats_dir = self.neptune_dir / "chats"
        self.chats_dir.mkdir(exist_ok=True, parents=True)

        self.ollama_base_url = "http://localhost:11434"
        self.openrouter_base_url = "https://openrouter.ai/api"

    def _exit_for_env_file(self):
        if not self.env_file.exists():
            self.env_file.write_text(
                "ANTHROPIC_API_KEY=\nOPENROUTER_API_KEY=\n",
                encoding="utf-8",
            )
            # escape codes make the text red
            # console isnt usable because this is initialized first
            print(
                f"\033[31m{self.env_file.resolve()} must have either OPENROUTER_API_KEY or ANTHROPIC_API_KEY defined\033[0m"
            )
            raise SystemExit()

    def _print_for_settings_file(self):
        if not self.settings_file.exists():
            self.settings_file.write_text(
                json.dumps({"model": "claude-sonnet-5"}, indent=4), encoding="utf-8"
            )

            print(f"{self.settings_file.resolve()} Created with default model claude-sonnet-5")

    def save(self):
        before = self.load()
        with open(self.settings_file, "w") as f:
            f.write(
                json.dumps(
                    before
                    | {
                        "model": self.model,
                    },
                    indent=4,
                )
            )

    def save_key(self, **kwargs):
        """Takes key=value strings"""
        before = self.load()
        with open(self.settings_file, "w") as f:
            f.write(json.dumps(before | kwargs, indent=4))

    def load_key(self, key: str):
        """Returns value or None"""
        with open(self.settings_file) as f:
            return json.loads(f.read()).get(key)

    def load(self) -> dict:
        with open(self.settings_file) as f:
            return json.loads(f.read())


settings = Settings()
