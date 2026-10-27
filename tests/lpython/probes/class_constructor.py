class Ctor:
    tag: i32
    value: i32


def main() -> None:
    c: Ctor = Ctor(1, 2)
    print(c.tag)


main()
