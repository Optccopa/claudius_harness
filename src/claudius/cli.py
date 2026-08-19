import argparse
import subprocess
import os

from claudius.main import chat

def main():
    parser = argparse.ArgumentParser(
        prog="claudius",
        description="Runs the claudius cli (claudecode like)"
    )
    parser.add_argument("user_input", nargs="?")
    args = parser.parse_args()

    subprocess.run('cls' if os.name == 'nt' else 'clear', shell=True)

    chat(args.user_input)

if __name__ == "__main__":
    main()