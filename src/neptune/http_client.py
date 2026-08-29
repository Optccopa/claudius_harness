import atexit

import httpx2

_client: httpx2.Client | None = None


def http_client() -> httpx2.Client:
    global _client
    if _client is None:
        _client = httpx2.Client(http2=True)
        atexit.register(_client.close)
    return _client
