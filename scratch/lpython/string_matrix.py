from lpython import i32
from string_lp import (
    string_get,
    string_length,
    string_next,
    string_prev,
    string_is_valid_pos,
    decode_char_at,
    string_extract,
    string_set,
    string_push,
    string_compare,
    string_dec_eq,
    string_dec_lt,
)

SAMPLES: list[str] = ["", "a", "héllo", "日本語", "🙂🙂", "aé日🙂z", "abcabc"]
CHARS: list[i32] = [65, 233, 26085, 128578]


def main():
    k: i32 = 0
    while k < len(SAMPLES):
        s: str = SAMPLES[k]
        print(len(s))
        print(string_length(s))
        i: i32 = 0
        while i < len(s) + 2:
            print(string_get(s, i))
            print(string_next(s, i))
            print(string_prev(s, i))
            print(string_is_valid_pos(s, i))
            print(decode_char_at(s, i))
            i += 1
        b: i32 = 0
        while b < len(s) + 2:
            e: i32 = 0
            while e < len(s) + 2:
                t: str = string_extract(s, b, e)
                print(len(t))
                print(string_length(t))
                e += 1
            b += 1
        i = 0
        while i < len(s) + 1:
            j: i32 = 0
            while j < len(CHARS):
                c: i32 = CHARS[j]
                u: str = string_set(s, i, c)
                print(len(u))
                print(string_length(u))
                print(string_compare(u, s))
                j += 1
            i += 1
        print(len(string_push(s, 26085)))
        k += 1
    a: i32 = 0
    while a < len(SAMPLES):
        b = 0
        while b < len(SAMPLES):
            print(string_compare(SAMPLES[a], SAMPLES[b]))
            print(string_dec_eq(SAMPLES[a], SAMPLES[b]))
            print(string_dec_lt(SAMPLES[a], SAMPLES[b]))
            b += 1
        a += 1


main()
