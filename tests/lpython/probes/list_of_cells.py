class Cell:
    tag: i32
    value: i32


def main() -> None:
    a: Cell = Cell()
    a.tag = 1
    a.value = 7
    cs: list[Cell] = [a]
    print(len(cs))


main()
