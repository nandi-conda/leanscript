class Cell:
    tag: i32
    ints: list[i32]
    strs: list[str]


def main() -> None:
    c: Cell = Cell()
    c.tag = 1
    c.ints = [7, 8]
    c.strs = ["a"]
    print(c.tag)
    print(len(c.ints))
    print(len(c.strs))


main()
