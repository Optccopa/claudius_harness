import anthropic

from claudius.settings import settings

class Anthropic(anthropic.Anthropic):
    def __init__(self):
        if not settings.anthropic_api_key:
            raise ValueError("Failed loading Anthropic api key, set ANTHROPIC_API_KEY in .env")
        
        super().__init__(
            api_key=settings.anthropic_api_key
        )

class OpenRouter(anthropic.Anthropic):
    def __init__(self):
        if not settings.openrouter_api_key:
            raise ValueError("Failed loading OpenRouter api key, set OPENROUTER_API_KEY in .env")
        
        super().__init__(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            max_retries=0
        )

class Ollama(anthropic.Anthropic):
    def __init__(self):
        super().__init__(
            api_key="ollama", # local
            base_url=settings.ollama_base_url,
            max_retries=0
        )

class LazyClient:
    def __init__(self):
        self._anthropic = None
        self._openrouter = None
        self._ollama = None

    def client(self, source: str | None = None):
        if source == "ollama" or source is None and ":" in settings.model and "/" not in settings.model:
            if not self._ollama:
                self._ollama = Ollama()

            return self._ollama
        
        elif source == "openrouter" or source is None and "/" in settings.model:
            if not settings.openrouter_api_key:
                raise ValueError("Failed loading openrouter api key, set OPENROUTER_API_KEY in .env")

            if not self._openrouter:
                self._openrouter = OpenRouter()

            return self._openrouter

        elif source == "anthropic" or source is None and settings.model.startswith("claude"):
            if not settings.anthropic_api_key:
                raise ValueError("Failed loading anthropic api key, set ANTHROPIC_API_KEY in .env")

            if not self._anthropic:
                self._anthropic = Anthropic()

            return self._anthropic

        else:
            if source:
                raise ValueError(f"Invalid source: {source}, please use anthropic, ollama, openrouter, or None for auto")
            raise ValueError(f"Invalid model: {settings.model}, please enter a valid model by using /model or changing the .env file")

client = LazyClient()