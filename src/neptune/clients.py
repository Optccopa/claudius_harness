from typing import Any

import anthropic
from httpx2 import ConnectError

from neptune.console import console
from neptune.errorhandler import handler
from neptune.http_client import http_client
from neptune.settings import settings
from neptune.tools import tools

DEFAULT_INFO: dict[str, Any] = {"context_length": 256000, "input_cost": 0.0, "output_cost": 0.0}


class Models:
    def __init__(self):
        self._ollama_models: list | None = None
        self._openrouter_models: tuple[list, list] | None = None
        self._anthropic_models: list | None = None
        self._info: dict[str, dict[str, Any]] = {}

    def _list_openrouter(self) -> tuple[list, list]:
        """returns: paid, free"""
        paid: list[str] = []
        free: list[str] = []
        r = http_client().get(
            f"{settings.openrouter_base_url}/v1/models",
            params={
                "sort": "intelligence-high-to-low",
                "min_tool_success_rate": "0.01",
                "supported_parameters": "tools",
            },
        )

        r.raise_for_status()

        if r.status_code == 200:
            for m in r.json()["data"]:
                p = m.get("pricing", {})
                self._info[m["id"]] = {
                    "context_length": m.get("context_length"),
                    "input_cost": float(p["prompt"]) * 1_000_000 if p.get("prompt") else None,
                    "output_cost": float(p["completion"]) * 1_000_000
                    if p.get("completion")
                    else None,
                }

                if m["id"].endswith(":batch"):
                    continue

                is_free = not any(float(p.get(k) or 0) for k in ("prompt", "completion", "request"))
                if "claude" in m["id"]:
                    continue  # Claude models already listed on anthropic endpoint

                (free if is_free else paid).append(m["id"])

        return paid, free

    def _list_ollama(self) -> list:
        r = http_client().get(f"{settings.ollama_base_url}/api/tags")
        if r.status_code == 200:
            return [m["name"] for m in r.json()["models"] if "tools" in m["capabilities"]]
        return []

    def _list_anthropic(self) -> list:
        return [m.id for m in client.client("anthropic").models.list()]

    def list_openrouter(self) -> tuple[list, list]:
        """Cached helper for _list_openrouter"""
        try:
            if self._openrouter_models is None:
                self._openrouter_models = self._list_openrouter()
                return self._openrouter_models

            else:
                return self._openrouter_models
        except ConnectError as e:
            handler.log(e)
            console.error("Failed loading openrouter models due to openrouter not responding")
            return ([], [])

    def list_ollama(self) -> list:
        """Cached helper for _list_ollama"""
        try:
            if self._ollama_models is None:
                self._ollama_models = self._list_ollama()
                return self._ollama_models

            else:
                return self._ollama_models

        except ConnectError:
            console.error("Failed loading ollama models due to ollama server not running")
            return []

    def list_anthropic(self) -> list:
        """Cached helper for _list_anthropic"""
        try:
            if self._anthropic_models is None:
                self._anthropic_models = self._list_anthropic()
                return self._anthropic_models

            else:
                return self._anthropic_models
        except ValueError:
            console.error("Failed loading anthropic models due to missing api key")
            return []

        except anthropic.APIError:
            console.error("Failed loading anthropic models due to invalid api key")
            return []

    def list_recents(self) -> list:
        return settings.load_key("recentModels") or []

    def _info_anthropic(self) -> dict:
        m = client.client("anthropic").models.retrieve(settings.model)
        return {"context_length": m.max_input_tokens, "input_cost": None, "output_cost": None}

    def _info_openrouter(self) -> dict:
        self.list_openrouter()
        return self._info.get(settings.model) or {}

    def _info_ollama(self) -> dict:
        r = http_client().post(
            f"{settings.ollama_base_url}/api/show", json={"model": settings.model}
        )
        if r.status_code != 200:
            return {}

        info = r.json().get("model_info", {})
        n = next((v for k, v in info.items() if k.endswith(".context_length")), None)
        return {"context_length": n, "input_cost": 0.0, "output_cost": 0.0}  # runs locally

    def model_info(self) -> dict[str, Any]:
        """Cached info for the active model: context_length, input_cost, output_cost"""
        try:
            if settings.model not in self._info:
                src = client.client()

                if isinstance(src, Ollama):
                    info = self._info_ollama()
                elif isinstance(src, OpenRouter):
                    info = self._info_openrouter()
                else:
                    info = self._info_anthropic()

                if info:
                    self._info[settings.model] = info
        except (ConnectError, anthropic.APIError, ValueError):
            console.error("Failed fetching model info, look above, using defaults")
            return DEFAULT_INFO

        return self._info.get(settings.model) or DEFAULT_INFO


class Anthropic(anthropic.Anthropic):
    def __init__(self):
        if not settings.anthropic_api_key:
            raise ValueError("Failed loading Anthropic api key, set ANTHROPIC_API_KEY in .env")

        super().__init__(api_key=settings.anthropic_api_key, http_client=http_client())

    def tools(self) -> list:
        """Defines the tools used when calling models on the client"""
        return tools


class OpenRouter(anthropic.Anthropic):
    def __init__(self):
        if not settings.openrouter_api_key:
            raise ValueError("Failed loading OpenRouter api key, set OPENROUTER_API_KEY in .env")

        super().__init__(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            max_retries=0,
            http_client=http_client(),
            default_headers={
                "HTTP-Referer": "https://github.com/Optccopa/neptune",
                "X-OpenRouter-Title": "Neptune",
                "X-OpenRouter-Categories": "coding-agent,productivity",
            },
        )

    def tools(self) -> list:
        """Defines the tools used when calling models on the client"""
        return [
            t
            for t in tools
            if t.get("type") is None  # skip anthropic server side tools
        ]


class Ollama(anthropic.Anthropic):
    def __init__(self):
        super().__init__(
            api_key="ollama",  # local
            base_url=settings.ollama_base_url,
            max_retries=0,
            http_client=http_client(),
        )

    def tools(self) -> list:
        """Defines the tools used when calling models on the client"""
        return [
            t
            for t in tools
            if t.get("type") is None  # skip anthropic server side tools
        ]


class LazyClient:
    def __init__(self):
        self._anthropic: Anthropic | None = None
        self._openrouter: OpenRouter | None = None
        self._ollama: Ollama | None = None

    def client(self, source: str | None = None) -> Anthropic | OpenRouter | Ollama:
        if (
            source == "ollama"
            or source is None
            and ":" in settings.model
            and "/" not in settings.model
        ):
            if not self._ollama:
                self._ollama = Ollama()

            return self._ollama

        elif source == "openrouter" or source is None and "/" in settings.model:
            if not settings.openrouter_api_key:
                raise ValueError(
                    "Failed loading openrouter api key, set OPENROUTER_API_KEY in .env"
                )

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
                raise ValueError(
                    f"Invalid source: {source}, please use anthropic, ollama, openrouter, or None for auto"
                )
            raise ValueError(
                f"Invalid model: {settings.model}, please enter a valid model by using /model or changing the .env file"
            )


client = LazyClient()
models = Models()
