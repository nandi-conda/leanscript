class Ctor:
    tag: i32


def get_tag(c: Ctor) -> i32:
    return c.tag


def main() -> None:
    c: Ctor = Ctor()
    c.tag = 3
    print(get_tag(c))


main()
