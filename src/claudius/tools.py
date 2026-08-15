import difflib
import questionary as qt
import subprocess
import os
from pathlib import Path
from rich.console import Console
from rich.theme import Theme
from rich.tree import Tree
from rich import print

theme = Theme({
    "body":   "#e8e3d8",
    "accent": "#D97757",
    "dim":    "#8a8175",
    "user":   "#b9f2ff",
    "ok":     "#7fb069",
    "warn":   "#d9a75f",
    "err":    "#d9605a",
})

console = Console(theme=theme, highlight=False)

tools = [
    {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": 5
    },
    {
        "name": "ask_user_question",
        "description": "Ask a question to the user to clarify ambigous prompts, Use this almost every prompt",
        "input_schema": {
            "type": "object",
            "required": ["question", "choices"],
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user"
                },
                "choices": {
                    "type": "array",
                    "description": "Short answer options. An 'other' field is always shown as well.",
                    "items": {"type": "string"},
                    "minItems": 1
                },
                "max_answers": {
                    "type": "integer",
                    "description": "Max allowed choices the user can provide, default: 1"
                }
            }
        } 
    },
    {
        "name": "powershell",
        "description": (
            "Run a powershell command and return its combined stdout and stderr.\n\n"
            "Each call runs in a fresh shell rooted at the workspace directory. "
            "`cd` does NOT persist between calls, so chain with && or use absolute "
            "paths when a command depends on a directory change.\n"
            "Never use this to read files unless you cannot use read_file\n"
            "Never use this to edit files unless you cannot use edit_file\n"
            "commands will prompt the user for approval. If a command is denied, do not retry it — ask "
            "the user what they'd prefer instead."
        ),
        "input_schema": {
            "type": "object",
            "required": ["command"],
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run. Quote paths containing spaces.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Seconds before the command is killed. default: 120.",
                    "minimum": 1,
                    "maximum": 600,
                },
            },
        },
    },
    {
        "name": "read_file", 
        "description": (
            "Read file lines using a global directory and line numbers\nReturns lines with line numbers"
        ),
        "input_schema": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file to read, provide a global directory",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start of lines to read",
                    "minimum": 0
                },
                "end_line": {
                    "type": "integer",
                    "description": "End of lines to read",
                    "minimum": 1
                }
            }
        }
    },
    {
        "name": "edit_file",
        "description": (
            "Replace an exact string in a file.\n"
            "old_string must match the file byte-for-byte including whitespace and "
            "indentation, and must appear exactly once — include surrounding lines "
            "for context if needed.\n"
            "Do NOT include the line numbers that read_file prefixes to its output.\n"
            "Fails without modifying anything if the match is missing or ambiguous.\n"
            "Always read_file first so you are matching against actual content.\n"
            "The user is shown a diff and asked to approve. If denied, do not retry — "
            "ask the user what they'd prefer instead."
        ),
        "input_schema": {
            "type": "object",
            "required": ["path", "old_string", "new_string"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file to edit, provide a global directory"
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact text to replace, without line numbers"
                },
                "new_string": {
                    "type": "string",
                    "description": "Text to replace it with"
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace every occurrence instead of requiring uniqueness. default: false"
                }
            }
        }
    },
    {
        "name": "tree",
        "description": (
            "Recursively list contents of a directory as a tree\n"
            "Use as an alternative to ls and any time you need to list files"
        ),
        "input_schema": {
            "type": "object",
            "required": [],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to list, default: project dir"
                }
            }
        }
    }
]

class RejectedToolUse(Exception):
    """Your tool use was manually rejected by the user"""

def _raise_for_permission(label: str):
    ok = qt.confirm(
        f"Claude wants to run {label}",
        default=True,
    ).ask()
    if not ok:
        raise RejectedToolUse(f"Your tool use was rejected, {label}")

def _show_diff(old: str, new: str, max_lines: int = 40) -> None:
    old_lines = old.splitlines()
    new_lines = new.splitlines()

    shown = 0
    for group in difflib.SequenceMatcher(None, old_lines, new_lines).get_grouped_opcodes(3):
        for tag, i1, i2, j1, j2 in group:
            if shown >= max_lines:
                console.print("  [dim]…[/]")
                return
            if tag in ("replace", "delete"):
                for n, line in enumerate(old_lines[i1:i2], i1 + 1):
                    console.print(f"  [dim]{n:>4}[/] [err]- {line}[/]")
                    shown += 1
            if tag in ("replace", "insert"):
                for n, line in enumerate(new_lines[j1:j2], j1 + 1):
                    console.print(f"  [dim]{n:>4}[/] [ok]+ {line}[/]")
                    shown += 1
            if tag == "equal":
                for n, line in enumerate(old_lines[i1:i2], i1 + 1):
                    console.print(f"  [dim]{n:>4}   {line}[/]")
                    shown += 1
    console.print()

def ask_user_question(question: str, choices: list, max_answers: int = 1):
    choices = list(choices) + ["Other"]
    response = qt.checkbox(
        question,
        set(choices),
        validate=lambda sel: True if len(sel) <= max_answers else f"Pick at most {max_answers}"
    ).ask()

    if response[0] == "Other":
        return qt.text("What else?").ask()
    else:
        return response

def powershell(command: str, timeout: int = 60) -> str:
    _raise_for_permission(command)
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=os.getcwd(), capture_output=True, text=True, errors="replace",
            timeout=min(timeout, 600),
        )
    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s. Use a longer timeout for long tasks."

    out = (r.stdout + r.stderr).strip()
    if len(out) > 30_000:
        out = out[:15_000] + f"\n\n[... {len(out) - 30_000} chars elided ...]\n\n" + out[-15_000:]

    if r.returncode != 0:
        return f"exit {r.returncode}\n{out}"
    return out or "(no output)"

def read_file(path: str, start_line: int = 0, end_line: int | None = None):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    if not end_line or end_line > len(lines):
        end_line = len(lines)

    if start_line > end_line:
        raise ValueError("Start line cannot be before end line")
    read = []
    for i, l in enumerate(lines, 1):
        if i < start_line:
            continue
        if i > end_line:
            continue
        read.append(f"{i} {l}")

    return "".join(read)

def edit_file(path: str, old_string: str = "", new_string: str = "",
              replace_all: bool = False, **kwargs) -> str:
    old_string = old_string or kwargs.get("old_str", "")
    new_string = new_string or kwargs.get("new_str", "")
    p = Path(path)

    if not p.exists():
        return f"File not found: {path}"
    if p.is_dir():
        return f"{path} is a directory."
    if old_string == new_string:
        return "old_string and new_string are identical, nothing to do."

    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"{path} is not a UTF-8 text file."

    count = text.count(old_string)

    if count == 0:
        return (
            "old_string not found. It must match the file exactly, including "
            "whitespace and indentation. Do NOT include the line-number prefix "
            "from read_file output. Call read_file and copy the text verbatim."
        )

    if count > 1 and not replace_all:
        return (
            f"old_string appears {count} times. Include surrounding lines to make "
            f"it unique, or set replace_all=true to change every occurrence."
        )

    updated = text.replace(old_string, new_string)

    _show_diff(text, updated)
    _raise_for_permission(f"edit {p.name}")

    p.write_text(updated, encoding="utf-8")
    return f"Edited {path} ({count} replacement{'s' if count != 1 else ''})"

def tree(path: str = ".", prefix: str = "") -> str:
    entries = sorted(Path(path).iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    entries = [e for e in entries if not e.name.startswith(".")]
    out = []
    for i, e in enumerate(entries):
        last = i == len(entries) - 1
        out.append(f"{prefix}{'\\ ' if last else '|- '}{e.name}")
        if e.is_dir():
            out.append(tree(e, prefix + ("    " if last else "|   ")))
    return "\n".join(filter(None, out))