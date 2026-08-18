import argparse

from claudius.main import chat

def main():
    parser = argparse.ArgumentParser(
        prog="claudius",
        description="Runs the claudius cli (claudecode like)"
    )
    parser.add_argument("user_input", nargs="?")
    args = parser.parse_args()
    chat(args.user_input)

if __name__ == "__main__":
    main()