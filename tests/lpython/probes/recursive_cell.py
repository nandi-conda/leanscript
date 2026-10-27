class Cell:
    tag: i32
    kids: list[Cell]


def main() -> None:
    c: Cell = Cell()
    c.tag = 1
    c.kids = []
    print(c.tag)


main()
