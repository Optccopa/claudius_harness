import traceback
from pathlib import Path

from neptune.console import console
from neptune.settings import settings


class ErrorHandler:
    def _location(self, exc: Exception) -> str:
        summary = traceback.extract_tb(exc.__traceback__)

        if not summary:
            return "unknown location"

        frame = summary[-1]
        line_number = frame.lineno or 0
        filename = frame.filename or "<unknown>"

        if filename.startswith("<"):
            return f"{filename}:{line_number}"

        try:
            path = Path(filename).resolve()
        except OSError:
            path = Path(filename)

        try:
            return f"{path.relative_to(settings.cwd)}:{line_number}"
        except ValueError:
            return f"{path}:{line_number}"

    def describe(self, exc: Exception) -> str:
        if hasattr(exc, "body"):
            if exc.body.get("metadata"):
                if exc.body["metadata"].get("raw"):
                    return exc.body["metadata"]["raw"]

            elif exc.body.get("error"):
                if exc.body["error"].get("message"):
                    return exc.body["error"]["message"]

        return f"{type(exc).__name__} @ {self._location(exc)}\n"

    def exit(self, exc: Exception):
        console.error(f"Neptune has crashed :(\n{self.describe(exc)}")
        raise SystemExit()

    def log(self, exc: Exception):
        console.error(f"Neptune had an error :(\n{self.describe(exc)}")


handler = ErrorHandler()
