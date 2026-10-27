def main() -> None:
    s: str = "hello"
    c: str = ""
    n: i32 = 0
    for c in s:
        n += 1
    print(len(s))
    print(s[0])
    print(s.find("llo"))
    print(s.upper())
    print(s + "!")
    print(str(n))


main()
