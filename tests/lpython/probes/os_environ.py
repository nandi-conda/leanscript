import os


def main() -> None:
    print(len(os.getenv("HOME")))


main()
