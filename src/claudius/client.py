import anthropic

from claudius.settings import settings
from claudius.console import console

class Client:
    def __init__(self):
        self._anthropic = None
        self._openrouter = None
        self._ollama = None

    def client(self, source: str | None = None):

        if source == "ollama" or (
            source is None and ":" in settings.model and "/" not in settings.model
        ):
            if not self._ollama:
                self._ollama = anthropic.Anthropic(
                    api_key="ollama",
                    base_url=settings.ollama_base_url,
                    max_retries=0
                )

                console.dim(f"Loaded {settings.model}")

            return self._ollama

        elif source == "anthropic" or "/" not in settings.model:
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
                    base_url=settings.openrouter_base_url,
                    max_retries=0
                )

                console.dim(f"Loaded {settings.model}")

            return self._openrouter

        else:
            raise ValueError(f"Invalid model: {settings.model}, please enter a valid model by using /model or changing the .env file")

client = Client()