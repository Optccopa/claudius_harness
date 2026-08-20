import argparse

from claudius.console import console
from claudius.main import chat


def main():
    parser = argparse.ArgumentParser(
        prog="claudius", description="Runs the claudius cli (claudecode like)"
    )
    parser.add_argument("user_input", nargs="?")
    args = parser.parse_args()

    console.clear()

    chat(args.user_input)


if __name__ == "__main__":
    main()
