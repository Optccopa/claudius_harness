import os
import json
from pathlib import Path

from dotenv import load_dotenv
from platformdirs import user_data_dir

class Settings:
    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent.parent.parent

        self.claudius_dir = Path(user_data_dir(".claudius", appauthor=False))

        self.claudius_dir.mkdir(exist_ok=True, parents=True)

        self.settings_file = self.claudius_dir / "settings.json"
        self._print_for_settings_file()
        
        self.env_file = self.claudius_dir / ".env"
        self._print_for_env_file()

        load_dotenv(self.env_file)

        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

        self.model = self.load()["model"]
        self.mode = "manual"

        self.system_file = self.base_dir / "SYSTEM.md"

        self.chats_dir = self.claudius_dir / "chats"
        self.chats_dir.mkdir(exist_ok=True, parents=True)

        self.ollama_base_url = "http://localhost:11434"
        self.openrouter_base_url = "https://openrouter.ai/api"

    def _print_for_env_file(self):
        if not self.env_file.exists():
            example = self.base_dir / "example.env"
            self.env_file.write_text(
                example.read_text(encoding="utf-8") if example.exists()
                else "ANTHROPIC_API_KEY=\nOPENROUTER_API_KEY=\n",
                encoding="utf-8",
            )
            print(
                f"{self.env_file.resolve()} must have either OPENROUTER_API_KEY or ANTHROPIC_API_KEY defined"
            )

    def _print_for_settings_file(self):
        if not self.settings_file.exists():
            self.settings_file.write_text(
                json.dumps({"model": "claude-sonnet-5"}, indent=4),
                encoding="utf-8"
            )

            print(
                f"{self.settings_file.resolve()} Created with default model claude-sonnet-5"
            )

    def save(self):
        before = self.load()
        with open(self.settings_file, "w") as f:
            f.write(json.dumps(before | {
                "model": self.model,
            }, indent=4))

    def save_key(self, **kwargs):
        """Takes key=value strings"""
        before = self.load()
        with open(self.settings_file, "w") as f:
            f.write(json.dumps(before | kwargs, indent=4))

    def load(self) -> dict:
        with open(self.settings_file) as f:
            return json.loads(f.read())


settings = Settings()