def count(n: i32) -> i32:
    if n <= 0:
        return 0
    return 1 + count(n - 1)


def main() -> None:
    print(count(1000))


main()
