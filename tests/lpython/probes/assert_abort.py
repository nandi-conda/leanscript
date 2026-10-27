def check(x: i32) -> i32:
    assert x > 0, "negative"
    return x


def main() -> None:
    print(check(-1))


main()
