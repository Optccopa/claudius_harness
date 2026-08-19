import datetime
import json
import platform
from pathlib import Path

from claudius.settings import settings
from claudius.console import console

def _prompt_for_permission():
    if console.confirm(
        "Do you trust this project and want to adopt its CLAUDE.md file into your system prompt"
        ):
        settings.save_key(**{f"{settings.cwd.absolute()}:IsTrustedWorkspace": True})
        return True
    else:
        settings.save_key(**{f"{settings.cwd.absolute()}:IsTrustedWorkspace": False})
        return False

def _claude_md() -> str:
    if settings.claude_file.exists():
        with open(settings.claude_file) as f:
            claude_md = f.read()

        return f"## Project claude.md\n{claude_md}"
    else:
        console.error(f"Could not find CLAUDE.md at {settings.claude_file}")
        return ""

class Messages:
    def __init__(self):
        self.messages = []

    def sys_prompt(self) -> str:
        now = datetime.datetime.now()

        time = now.strftime("%Y-%m-%d %I:%M %p")

        with open(settings.system_file, encoding="utf-8") as f:
            system = f.read()

        system = system.replace("{{model}}", settings.model)
        system = system.replace("{{time}}", time)
        system = system.replace("{{dir}}", str(Path().resolve()))
        system = system.replace(
            "{{platform}}",
            platform.system() or "Undetermined"
        )
        trusted = settings.load().get(f"{settings.cwd.absolute()}:IsTrustedWorkspace")

        if trusted is None: # never prompted before

            if _prompt_for_permission(): # accepted
                system = system.replace("{{claude_md}}", _claude_md())

            else: # denied on first run
                system = system.replace("{{claude_md}}", "")

        elif trusted == True: # prompted and said yes
            system = system.replace("{{claude_md}}", _claude_md())

        else: # prompted and said no / other
            system = system.replace("{{claude_md}}", "")

        system = system.rstrip()

        settings.debug_system_file.write_text(system, encoding="utf-8")

        return system

    def save(self, path: Path) -> None:
        def to_dict(b):
            return b if isinstance(b, dict) else b.model_dump(mode="json", exclude_none=True)

        out = [
            {"role": m["role"],
            "content": m["content"] if isinstance(m["content"], str)
                        else [to_dict(b) for b in m["content"]]}
            for m in self.messages
        ]

        path = Path(path)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def save_exc(self, exc: str, snapshot: int):
        """Saves and deletes current context"""
        now = datetime.datetime.now()
        path = Path(f"{settings.chats_dir}/chat-{exc}-{now.strftime('%H-%M-%S')}.json")

        self.save(path)

        del self.messages[snapshot:]

        console.success(f"Saved messages as {path.resolve()}")

    def load(self, path: Path):
        self.messages = json.loads(Path(path).read_text(encoding="utf-8"))

messages = Messages()