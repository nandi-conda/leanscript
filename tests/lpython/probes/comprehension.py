def main() -> None:
    xs: list[i32] = [1, 2, 3]
    ys: list[i32] = [x * 2 for x in xs]
    print(len(ys))


main()
