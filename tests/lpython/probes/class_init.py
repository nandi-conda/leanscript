class Ctor:
    tag: i32
    value: i32

    def __init__(self, tag: i32, value: i32) -> None:
        self.tag = tag
        self.value = value


def main() -> None:
    c: Ctor = Ctor(1, 2)
    print(c.tag)


main()
