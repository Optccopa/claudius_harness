import traceback
from pathlib import Path

from claudius.console import console
from claudius.settings import settings


class ErrorHandler:
    def describe(self, exc: Exception) -> str:
        tb = exc.__traceback__
        summary = traceback.extract_tb(tb)

        if summary:
            last_frame = summary[-1]
            line_number = last_frame.lineno
            path = Path(last_frame.filename)
        else:
            line_number = 0
            path = Path()

        try:
            relative = path.relative_to(settings.cwd)
        except ValueError:
            relative = settings.cwd / "CLAUDE.md"

        return f"{type(exc).__name__} @ {relative}:{line_number}\n"

    def exit(self, exc: Exception):
        console.error(f"Claudius has crashed :(\n{self.describe(exc)}")
        raise SystemExit()

    def log(self, exc: Exception):
        console.error(f"Claudius had an error :(\n{self.describe(exc)}")


handler = ErrorHandler()
