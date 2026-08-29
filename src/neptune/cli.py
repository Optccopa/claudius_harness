import argparse

from neptune.console import console
from neptune.main import chat


def main():
    parser = argparse.ArgumentParser(
        prog="neptune", description="Runs the neptune cli (claudecode like)"
    )
    parser.add_argument("user_input", nargs="?")
    args = parser.parse_args()

    console.clear()

    chat(args.user_input)


if __name__ == "__main__":
    main()
