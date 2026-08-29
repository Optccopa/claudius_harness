import argparse

from neptune.console import console
from neptune.errorhandler import handler
from neptune.main import chat


def main():
    parser = argparse.ArgumentParser(
        prog="neptune", description="Runs the neptune cli (claudecode like)"
    )
    parser.add_argument("user_input", nargs="?")
    args = parser.parse_args()

    console.clear()
    try:
        chat(args.user_input)
    except Exception as e:
        handler.exit(e)


if __name__ == "__main__":
    main()
