class Ctor:
    tag: i32

    def get(self) -> i32:
        return self.tag


def main() -> None:
    c: Ctor = Ctor()
    c.tag = 7
    print(c.get())


main()
