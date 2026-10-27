def inc(x: i32) -> i32:
    return x + 1


def apply_it(f: i32, x: i32) -> i32:
    return f(x)


def main() -> None:
    print(apply_it(inc, 1))


main()
