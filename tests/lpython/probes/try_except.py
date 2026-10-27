def check(x: i32) -> i32:
    try:
        if x < 0:
            raise ValueError("negative")
        return x
    except ValueError:
        return 0


def main() -> None:
    print(check(-1))


main()
