import difflib
import os
import re
import subprocess
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import questionary as qt
from rich.markup import escape

from neptune.console import PROMPT_STYLE, console
from neptune.settings import settings

LS_IGNORE = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    ".mypy_cache",
    ".ruff_cache",
}

# Directories that dont get walked, speeds up grep / glob
# uses everything also listed in LS_IGNORE
WALK_IGNORE = LS_IGNORE | {
    "venv",
    "dist",
    "build",
    "bin",
    "obj",
    "packages",
    "target",
    "vendor",
    ".next",
    ".tox",
    ".pytest_cache",
    ".gradle",
    ".idea",
}

# Files above this are assumed to be data, not source code
MAX_GREP_BYTES = 2_000_000

tools: list[dict[str, Any]] = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 5},
    {
        "name": "ask_user_question",
        "description": "Ask a question in a structured format, reach for this when you need clarification",
        "input_schema": {
            "type": "object",
            "required": ["question", "choices"],
            "properties": {
                "question": {"type": "string", "description": "The question to ask the user"},
                "choices": {
                    "type": "array",
                    "description": "Short answer options. An extra field is appended for the user to provide extras",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "max_answers": {
                    "type": "integer",
                    "description": "Max allowed choices the user can provide, default: 1",
                },
            },
        },
        "input_examples": [
            {
                "question": "What httplib should i use?",
                "choices": ["aiohttp (async)", "requests (blocking)", "stdlib (blocking)"],
            },
            {
                "question": "What should i fix right now?",
                "choices": ["Offset fov", "Bullet clipping", "StackOverflow in main"],
                "max_answers": 1,
            },
        ],
    },
    {
        "name": "read_file",
        "description": (
            "Read file lines using a global directory and line numbers\n"
            "Returns lines with line numbers"
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
                    "minimum": 0,
                },
                "end_line": {
                    "type": "integer",
                    "description": "End of lines to read",
                    "minimum": 1,
                },
            },
        },
    },
    {
        "name": "ls",
        "description": (
            "- List directory contents as flat relative paths, one entry per line\n"
            "- This tool has no permission requirements\n"
            "- Directories get a trailing slash; set recurse=true to expand them\n"
            "- Ignores .git, node_modules, __pycache__, .venv and similar cache dirs\n"
            "- Capped at max_entries lines so huge directories stay cheap to read"
        ),
        "input_schema": {
            "type": "object",
            "required": [],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory to list. If not specified, the current working directory will be used",
                },
                "recurse": {
                    "type": "boolean",
                    "description": "Expand subdirectories. Default false.",
                },
                "max_entries": {
                    "type": "integer",
                    "description": "Max number of lines returned before truncating. Default 200.",
                },
            },
        },
    },
    {
        "name": "glob",
        "description": (
            "- Fast file pattern matching tool that works with any codebase size\n"
            "- This command has no permission requirements, PREFER THIS OVER OTHER TOOLS\n"
            "- Reach for powershell if nothing else without permission requirements fits\n"
            '- Supports glob patterns like "**/*.py" or "src/**/*.ts"\n'
            "- Returns matching file paths sorted by modification time, newest first\n"
            "- Use this tool when you need to find files by name patterns\n"
            "- Use tree instead when you want to see the shape of a directory\n"
            "- You can call multiple tools in a single response. It is always better "
            "to speculatively perform multiple searches in parallel if they are "
            "potentially useful."
        ),
        "input_schema": {
            "type": "object",
            "required": ["pattern"],
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The glob pattern to match files against",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "The directory to search in. If not specified, the current working "
                        "directory will be used. IMPORTANT: Omit this field to use the default "
                        'directory. DO NOT enter "undefined" or "null" - simply omit it for '
                        "the default behavior."
                    ),
                },
            },
        },
    },
    {
        "name": "grep",
        "description": (
            "- Fast content search tool that works with any codebase size\n"
            "- Searches file contents using regular expressions\n"
            "- This command has no permission requirements, PREFER THIS OVER OTHER TOOLS\n"
            "- Reach for powershell if nothing else without permission requirements fits\n"
            '- Supports full regex syntax (e.g. "log.*Error", "def\\\\s+\\\\w+")\n'
            '- Filter which files are searched with glob_filter (e.g. "**/*.py")\n'
            "- Returns matching lines with line numbers\n"
            "- Use this instead of Select-String\n"
            "- Set files_only=true when you only need to know which files match — "
            "it is much cheaper than returning every line\n"
            "- When doing an open ended search that may require multiple rounds, "
            "call this several times in parallel with different patterns"
        ),
        "input_schema": {
            "type": "object",
            "required": ["pattern"],
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The regular expression pattern to search for in file contents",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "The directory to search in, or a single file to search. IMPORTANT: "
                        "Omit this field to use the default directory. DO NOT enter "
                        '"undefined" or "null" - omit it for the default behavior.'
                    ),
                },
                "glob_filter": {
                    "type": "string",
                    "description": (
                        'Glob pattern limiting which files are searched, e.g. "**/*.py". '
                        'Must start with "**/" to search subdirectories - a bare "*.py" '
                        "only matches files sitting directly in path. Defaults to every file. "
                        "Ignored when path is a single file."
                    ),
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Case insensitive search. Default false.",
                },
                "files_only": {
                    "type": "boolean",
                    "description": (
                        "Return only the paths of files that match, not the matching lines. "
                        "Default false."
                    ),
                },
                "context": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "description": (
                        "Lines of context to show before and after each match. Default 0. "
                        "Ignored when files_only is true."
                    ),
                },
            },
        },
    },
    {
        "name": "git_status",
        "description": (
            "Show working tree status via `git status --porcelain`.\n"
            "This command has no permission requirements, PREFER THIS OVER OTHER TOOLS\n"
            "Reach for powershell if nothing else without permission requirements fits"
        ),
        "input_schema": {"type": "object", "required": [], "properties": {}},
    },
    {
        "name": "git_diff",
        "description": (
            "Show unstaged changes for a single file via `git diff <file_name>`.\n"
            "Only shows changed since last commit\n"
            "This command has no permission requirements, PREFER THIS OVER OTHER TOOLS\n"
            "Reach for powershell if nothing else without permission requirements fits"
        ),
        "input_schema": {
            "type": "object",
            "required": ["file_name"],
            "properties": {
                "file_name": {
                    "type": "string",
                    "description": "Path to the file to diff, relative to the repo root",
                }
            },
        },
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
                    "description": "Seconds before the command is killed. default: 60.",
                    "minimum": 1,
                    "maximum": 600,
                },
            },
        },
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
                    "description": "The file to edit, provide a global directory",
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact text to replace, without line numbers",
                },
                "new_string": {"type": "string", "description": "Text to replace it with"},
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace every occurrence instead of requiring uniqueness. default: false",
                },
            },
        },
    },
    {
        "name": "create_file",
        "description": (
            "Create a new empty file at the given path.\n"
            "Fails if the file already exists — use edit_file to modify it instead.\n"
            "Parent directories are created automatically if missing.\n"
            "The user is shown a permission prompt and asked to approve. If denied, "
            "do not retry, ask the user what they'd prefer instead."
        ),
        "input_schema": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file to create, provide a global directory",
                },
                "content": {
                    "type": "string",
                    "description": "The content that is written to the file on creation",
                },
            },
        },
    },
]


class RejectedToolUse(Exception):
    """Your tool use was manually rejected by the user"""


def _raise_for_permission(label: str, mode: str):
    if mode == "auto":
        print(f"{settings.model} ran `{label}` (auto)")
        return

    else:
        ok = console.confirm(
            f"{settings.model} wants to run `{label}`",
            default=True,
        )
        if not ok:
            raise RejectedToolUse(f"Your tool use was rejected, {label}")


def _show_diff(old: str, new: str, max_lines: int = 40) -> None:
    old_lines = old.splitlines()
    new_lines = new.splitlines()

    shown = 0
    for group in difflib.SequenceMatcher(None, old_lines, new_lines).get_grouped_opcodes(3):
        for tag, i1, i2, j1, j2 in group:
            if shown >= max_lines:
                console.dim("  …")
                return
            if tag in ("replace", "delete"):
                for n, line in enumerate(old_lines[i1:i2], i1 + 1):
                    console.dim(f"  {n:>4} [err]- {escape(line)}", markup=True)
                    shown += 1
            if tag in ("replace", "insert"):
                for n, line in enumerate(new_lines[j1:j2], j1 + 1):
                    console.dim(f"  {n:>4} [ok]+ {escape(line)}", markup=True)
                    shown += 1
            if tag == "equal":
                for n, line in enumerate(new_lines[j1:j2], j1 + 1):
                    console.dim(f"  {n:>4}   {line}")
                    shown += 1
    console._print("")


def ask_user_question(question: str, choices: list, max_answers: int = 1, **kwargs):
    choices = list(choices) + ["Other"]
    response = qt.checkbox(
        question,
        choices,
        validate=lambda sel: True if len(sel) <= max_answers else f"Pick at most {max_answers}",
        style=PROMPT_STYLE,
    ).ask()

    if not response:
        return "User provided an empty answer."

    if response[0] == "Other":
        return console.input("What else?")
    else:
        return response


def powershell(command: str, timeout: int = 60, **kwargs) -> str:
    _raise_for_permission(command, str(kwargs.get("mode")))
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            errors="replace",
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


def read_file(path: str, start_line: int = 0, end_line: int | None = None, **kwargs):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    if end_line is None or end_line > len(lines):
        end_line = len(lines)

    if start_line > end_line:
        raise ValueError("Start line cannot be after end line")
    read = []
    for i, line in enumerate(lines, 1):
        if i < start_line:
            continue
        if i > end_line:
            continue
        read.append(f"{i} {line}")

    return "".join(read)


def edit_file(
    path: str, old_string: str = "", new_string: str = "", replace_all: bool = False, **kwargs
) -> str:
    if old_string == "":
        old_string = kwargs.get("old_str", "")
    if new_string == "":
        new_string = kwargs.get("new_str", "")
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
    _raise_for_permission(f"edit {p.name}", str(kwargs.get("mode")))

    p.write_text(updated, encoding="utf-8")
    return f"Edited {path} ({count} replacement{'s' if count != 1 else ''})"


def create_file(path: str | Path, content: str | None = None, **kwargs):
    path = Path(path)
    if path.exists():
        return f"{path.resolve()} already exists. Use edit_file to modify it."

    _raise_for_permission(f"create_file {path}", str(kwargs.get("mode")))

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    except OSError as e:
        return f"Could not create {path}: {e}"

    with open(path, "w", encoding="utf-8") as f:
        f.write(content or "")

    return f"Created file at {path.resolve()}"


def ls(path: str | Path = Path(), recurse: bool = False, max_entries: int = 200, **kwargs) -> str:
    root = Path(path)
    if not root.is_dir():
        return f"{root} is not a directory."

    lines: list[str] = []

    def walk(d: Path) -> None:
        try:
            entries = sorted(d.iterdir(), key=lambda p: (p.is_dir(), p.name.lower()))
        except PermissionError:
            lines.append(f"{d.relative_to(root).as_posix()}/  [permission denied]")
            return

        for e in entries:
            if len(lines) >= max_entries:
                return
            rel = e.relative_to(root).as_posix()
            if not e.is_dir():
                lines.append(rel)
            elif e.name in LS_IGNORE or e.is_symlink() or not recurse:
                lines.append(f"{rel}/  [not expanded]")
            else:
                lines.append(f"{rel}/")
                walk(e)

    walk(root)
    truncated = "\n[truncated]" if len(lines) >= max_entries else ""
    return f"{root.resolve()}\n" + "\n".join(lines) + truncated


def _iter_files(root: Path, pattern: str):
    if pattern.startswith("**/") and "/" not in pattern[3:]:
        name = pattern[3:]
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in WALK_IGNORE]
            for fn in filenames:
                if fnmatch(fn, name):
                    yield Path(dirpath) / fn
    else:
        for p in root.glob(pattern):
            if p.is_file():
                yield p


def glob(pattern: str, path: str = str(Path().resolve()), **kwargs) -> str:
    root = Path(path)
    if not root.is_dir():
        return f"Not a directory: {path}"

    hits = list(_iter_files(root, pattern))
    hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    if not hits:
        return f"No files match {pattern}"

    out = [str(p) for p in hits[:200]]
    if len(hits) > 200:
        out.append(f"[{len(hits)} total, showing 200]")
    return "\n".join(out)


def grep(
    pattern: str,
    path: str = ".",
    glob_filter: str = "**/*",
    case_insensitive: bool = False,
    files_only: bool = False,
    context: int = 0,
    **kwargs,
) -> str:
    try:
        rx = re.compile(pattern, re.IGNORECASE if case_insensitive else 0)
    except re.error as e:
        return f"Bad regex: {e}"

    root = Path(path)
    if not root.exists():
        return f"No such path: {path}"

    single = root.is_file()
    candidates = [root] if single else _iter_files(root, glob_filter)

    hits, count, scanned = [], 0, 0
    for f in candidates:
        if not single and any(p.startswith(".") for p in f.parts):
            continue
        scanned += 1
        try:
            if f.stat().st_size > MAX_GREP_BYTES:
                continue
            raw = f.read_bytes()
        except OSError:
            continue

        if b"\0" in raw[:8192]:  # binary, skip before taking time to decode
            continue

        try:
            lines = raw.decode("utf-8").splitlines()
        except UnicodeDecodeError:
            continue

        matched = [i for i, line in enumerate(lines) if rx.search(line)]
        if not matched:
            continue
        count += len(matched)

        if files_only:
            hits.append(str(f))
            continue

        hits.append(f"\n{f}")
        for i in matched:
            lo, hi = max(0, i - context), min(len(lines), i + context + 1)
            for n in range(lo, hi):
                mark = ":" if n == i else "-"
                hits.append(f"{n + 1}{mark} {lines[n][:300]}")

        if len(hits) > 400:
            hits.append(f"\n[truncated, {count}+ matches]")
            break

    if not hits:
        if not scanned:
            # Distinguish "searched nothing" from "searched and found nothing"
            hint = f" Did you mean '**/{glob_filter}'?" if "/" not in glob_filter else ""
            return f"glob_filter {glob_filter!r} matched no files under {path}.{hint}"
        return f"No matches for {pattern}"
    return "\n".join(hits)


def _git_run(command: list[str], timeout: int = 60, **kwargs) -> str:
    try:
        r = subprocess.run(
            command,
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            errors="replace",
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


def git_status(**kwargs) -> str:
    out = _git_run(["git", "status", "--porcelain"])
    return out or "(no output)"


def git_diff(file_name: str, **kwargs) -> str:
    out = _git_run(["git", "diff", file_name])
    return out or "(no output)"
