import questionary as qt
import subprocess
import os
from pathlib import Path
from rich.tree import Tree
from rich import print

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
    
def ask_user_question(question: str, choices: list, max_answers: int = 1):
    choices.append("Other")
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

def tree(path: str = ".") -> str:
    entries = sorted(Path(path).iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    out = []
    for i, e in enumerate(entries):
        if e.name.startswith("."):
            continue
        last = i == len(entries) - 1
        out.append(f"{'\\ ' if last else '|- '}{e.name}")
        if e.is_dir():
            out.append(tree(e, ("    " if last else "|   ")))
    return "\n".join(filter(None, out))