def make_adder(n: i32) -> i32:
    def add(x: i32) -> i32:
        return x + n
    return add


def main() -> None:
    f: i32 = make_adder(3)
    print(f(4))


main()
