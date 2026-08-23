"""
Main CLI assistant, run with `claudius "hello"`
"""

import inspect
import os
from pathlib import Path

import anthropic
from rich.markdown import Markdown
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from claudius import tools
from claudius.clients import client, models
from claudius.commands import handler as command_handler
from claudius.console import console
from claudius.errorhandler import handler
from claudius.messages import messages
from claudius.settings import settings

# If a tool is in this dict it doesnt print args to the tool
SILENT = [
    "ask_user_question",
    "create_file",
    "read_file",
    "edit_file",
    "git_diff",
    "tree",
]

MAX_RECENT_MODELS = 5

session_tokens: dict[str, int] = {"session_input_tokens": 0, "session_output_tokens": 0}

named_tool_functions = {
    name: fn
    for name, fn in inspect.getmembers(tools, inspect.isfunction)
    if fn.__module__ == tools.__name__ and not name.startswith("_")
}


def stream_response(stream, parts: list):
    buf = ""
    code_lines = None
    for text in stream.text_stream:
        parts.append(text)
        buf += text
        while "\n" in buf:
            line, _, buf = buf.partition("\n")
            fence = line.strip().startswith("```")
            if code_lines is None:
                if fence:
                    code_lines = [line]
                    console.raw_line(line)
                else:
                    console.line(line)
            else:
                code_lines.append(line)
                console.raw_line(line)
                if fence:
                    console.clear_lines(len(code_lines))
                    console.renderable(Markdown("\n".join(code_lines), style="body"))
                    code_lines = None

        console.partial(buf)

    if code_lines is not None:
        code_lines.append(buf)
        console.raw_line(buf)
        console.clear_lines(len(code_lines))
        console.renderable(Markdown("\n".join(code_lines), style="body"))
    elif buf:
        console.line(buf)
    else:
        print()

    return stream.get_final_message()


def chat(first: str | None = None):
    while True:
        try:
            try:
                user_input: str | None
                if first:
                    user_input, first = first, None
                else:
                    user_input = console.input()  # Default 'you:'

                if user_input is None:
                    break

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    try:
                        command_handler.parse(user_input)
                    except Exception as e:
                        handler.log(e)
                    continue
            except (EOFError, KeyboardInterrupt):
                break

            snapshot = len(messages.messages)

            messages.messages.append({"role": "user", "content": user_input})

            try:
                while True:
                    parts: list[str] = []
                    final = None
                    try:
                        with client.client().messages.stream(
                            model=settings.model,
                            max_tokens=32768,
                            system=messages.sys_prompt(),
                            tools=client.client().tools(),
                            messages=messages.messages,
                        ) as stream:
                            final = stream_response(stream, parts)
                    except KeyboardInterrupt:
                        pass

                    # add used model to recent models
                    recent: list = settings.load_key("recentModels") or []

                    if settings.model in recent:
                        recent.remove(settings.model)

                    recent.insert(0, settings.model)
                    settings.save_key(recentModels=recent[:MAX_RECENT_MODELS])

                    if final is None:
                        partial = "".join(parts).strip()
                        if partial:
                            messages.messages.append(
                                {
                                    "role": "assistant",
                                    "content": partial + "\n\n[interrupted]",
                                }
                            )
                        else:
                            del messages.messages[snapshot:]
                        console.dim(" interrupted")
                        break

                    if final.stop_reason == "max_tokens":
                        console.warn("    hit max_tokens, reply truncated")

                    messages.messages.append({"role": "assistant", "content": final.content})

                    for block in final.content:
                        t = block.type

                        if t == "server_tool_use":
                            if block.name == "web_search":
                                console.bullet(f"search  {block.input.get('query', '')}")
                            continue

                        if t == "web_search_tool_result":
                            n = len(block.content) if isinstance(block.content, list) else 0
                            console.bullet(f"{n} results", glyph="↳")
                            continue

                    if final.stop_reason != "tool_use":
                        break

                    results = []
                    aborted = False
                    for block in final.content:
                        t = block.type

                        if t == "thinking":
                            continue

                        if t != "tool_use":
                            continue

                        if aborted:
                            results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": "interrupted by user.",
                                    "is_error": True,
                                }
                            )
                            continue

                        path_arg = block.input.get("path")
                        if path_arg:
                            try:
                                s = Path(os.path.relpath(path_arg, settings.cwd)).as_posix()
                            except ValueError:
                                s = Path(path_arg).as_posix()
                            if s.startswith("../"):
                                s = Path(path_arg).as_posix().replace(Path.home().as_posix(), "~")
                            block.input["path"] = s if len(s) <= 60 else "…/" + s[-(60 - 2) :]

                        args = ", ".join([f"{k}={v!r}" for k, v in block.input.items()])
                        suffix = f"with {args}" if block.input else ""
                        console.bullet(f"{block.name} {suffix}")

                        try:
                            output = named_tool_functions[block.name](
                                **block.input, mode=settings.mode
                            )
                            is_error = False
                        except KeyboardInterrupt:
                            output, is_error, aborted = "Interrupted by user.", True, True
                        except TypeError as e:
                            output = (
                                f"{e}. Check the tool's input_schema for exact parameter names."
                            )
                            is_error = True
                        except Exception as e:
                            output, is_error = f"{type(e).__name__}: {e}", True

                        if (
                            block.name not in SILENT
                        ):  # Ignore large dumps from readfile / reprinting ask_user_question
                            console.tool_result(output, is_error)

                        results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": str(output),
                                "is_error": is_error,
                            }
                        )

                    messages.messages.append({"role": "user", "content": results})

                    if aborted:
                        break

                print()

            except anthropic.PermissionDeniedError as e:
                if e.status_code == 403:
                    console.error("You may have an invalid model")
                handler.log(e)
                messages.save_exc(type(e).__name__, snapshot)

            except anthropic.APIConnectionError as e:
                handler.log(e)
                messages.save_exc(type(e).__name__, snapshot)

            except anthropic.RateLimitError as e:
                handler.log(e)
                messages.save_exc(type(e).__name__, snapshot)

            except anthropic.APIStatusError as e:
                handler.log(e)
                messages.save_exc(type(e).__name__, snapshot)
                continue

            except ValueError as e:
                handler.log(e)
                messages.save_exc(type(e).__name__, snapshot)
                continue

            if final:
                u = final.usage

                session_tokens["session_input_tokens"] += u.input_tokens
                session_tokens["session_output_tokens"] += u.output_tokens

                info = models.model_info()

                cost = (
                    session_tokens["session_input_tokens"] * info["input_cost"]
                    + session_tokens["session_output_tokens"] * info["output_cost"]
                ) / 1_000_000

                tokens = 0
                tokens += u.input_tokens or 0
                tokens += u.output_tokens or 0

                total = info["context_length"]
                frac = tokens / total if total else 0.0
                style = "green" if frac < 0.60 else "yellow" if frac < 0.85 else "red"
                grid = Table.grid(padding=(0, 1))
                grid.add_column(width=28)
                grid.add_column(justify="right")
                grid.add_row(
                    ProgressBar(
                        total=total,
                        completed=tokens,
                        width=28,
                        complete_style=style,
                        finished_style=style,
                        style="grey23",
                    ),
                    Text.assemble((f"{tokens:,}/{total:,}", style)),
                )

                pricing = (
                    f"${cost:.2f} (${info['input_cost']:.2f}, ${info['output_cost']:.2f}"
                    if info["input_cost"] > 0 and info["output_cost"] > 0
                    else "free"
                )

                console.dim(f"{settings.model} · {settings.mode} · session: {pricing})")
                console.renderable(grid)
        except KeyboardInterrupt:
            continue
