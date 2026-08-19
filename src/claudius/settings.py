import os
from pathlib import Path

from dotenv import load_dotenv
from platformdirs import user_data_dir

class Settings:
    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent.parent.parent

        self.claudius_dir = Path(user_data_dir(".claudius", appauthor=False))

        self.claudius_dir.mkdir(exist_ok=True, parents=True)

        self.env_file = self.claudius_dir / ".env"

        self._raise_for_env_file()

        load_dotenv(self.env_file)

        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

        self.model = os.getenv("MODEL") or "claude-sonnet-5"

        self.mode = "manual"

        self.system_file = self.base_dir / "SYSTEM.md"

        self.chats_dir = self.claudius_dir / "chats"

        self.chats_dir.mkdir(exist_ok=True, parents=True)

        self.ollama_base_url = "http://localhost:11434"
        self.openrouter_base_url = "https://openrouter.ai/api"

    def _raise_for_env_file(self):
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

settings = Settings()