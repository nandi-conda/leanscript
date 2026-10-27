"""UTF-8 string primitives for LPython 0.22.

LPython `str` is a UTF-8 byte string: `len` counts bytes, `s[i]` is the one-byte `str` at byte `i`,
`ord` returns that byte, and `chr` of a byte value produces that one byte. That matches Lean's
`String.Pos` model, so positions are byte offsets and no codec is needed: only scalar counting and
scalar encoding, which this module implements.

Strings are immutable in LPython, so a string has no reference count and every operation returns a
new string. Slicing a `str` parameter is unreliable in LPython 0.22 (see the probe notes), so
substrings are built by copying bytes.
"""

from lpython import i32

DEFAULT_CHAR: i32 = 65


def byte_at(s: str, i: i32) -> i32:
    if i < 0 or i >= len(s):
        return 0
    # `ord` of a one-byte string is the signed value of the byte, so mask it back to 0-255.
    return ord(s[i]) & 255


def is_char_boundary(s: str, i: i32) -> bool:
    if i < 0 or i >= len(s):
        return False
    return (byte_at(s, i) & 192) != 128


def sequence_size(b: i32) -> i32:
    if b < 128:
        return 1
    if (b & 224) == 192:
        return 2
    if (b & 240) == 224:
        return 3
    return 4


def decode_char_at(s: str, i: i32) -> i32:
    c: i32 = byte_at(s, i)
    if c < 128:
        return c
    if (c & 224) == 192:
        return ((c & 31) << 6) | (byte_at(s, i + 1) & 63)
    if (c & 240) == 224:
        return ((c & 15) << 12) | ((byte_at(s, i + 1) & 63) << 6) | (byte_at(s, i + 2) & 63)
    return ((c & 7) << 18) | ((byte_at(s, i + 1) & 63) << 12) | ((byte_at(s, i + 2) & 63) << 6) | (byte_at(s, i + 3) & 63)


def encode_char(c: i32) -> str:
    if c < 128:
        return chr(c)
    if c < 2048:
        return chr(192 | (c >> 6)) + chr(128 | (c & 63))
    if c < 65536:
        return chr(224 | (c >> 12)) + chr(128 | ((c >> 6) & 63)) + chr(128 | (c & 63))
    return chr(240 | (c >> 18)) + chr(128 | ((c >> 12) & 63)) + chr(128 | ((c >> 6) & 63)) + chr(128 | (c & 63))


def copy_bytes(s: str, b: i32, e: i32) -> str:
    r: str = ""
    k: i32 = b
    while k < e:
        r += s[k]
        k += 1
    return r


def string_length(s: str) -> i32:
    n: i32 = 0
    i: i32 = 0
    while i < len(s):
        i += sequence_size(byte_at(s, i))
        n += 1
    return n


def string_get(s: str, i: i32) -> i32:
    if is_char_boundary(s, i):
        return decode_char_at(s, i)
    return DEFAULT_CHAR


def string_next(s: str, i: i32) -> i32:
    if is_char_boundary(s, i):
        return i + sequence_size(byte_at(s, i))
    return i + 1


def string_prev(s: str, i: i32) -> i32:
    if i == 0:
        return 0
    if i > len(s):
        return i - 1
    j: i32 = i - 1
    while j > 0 and (byte_at(s, j) & 192) == 128:
        j -= 1
    return j


def string_is_valid_pos(s: str, i: i32) -> i32:
    if i < len(s):
        if is_char_boundary(s, i):
            return 1
        return 0
    if i == len(s):
        return 1
    return 0


def string_extract(s: str, b: i32, e: i32) -> str:
    if b >= e or b >= len(s) or not is_char_boundary(s, b):
        return ""
    end: i32 = e
    if e > len(s) or (e < len(s) and not is_char_boundary(s, e)):
        end = len(s)
    return copy_bytes(s, b, end)


def string_append(s: str, t: str) -> str:
    if len(t) == 0:
        return s
    return s + t


def string_push(s: str, c: i32) -> str:
    return s + encode_char(c)


def string_set(s: str, i: i32, c: i32) -> str:
    if not is_char_boundary(s, i):
        return s
    old: i32 = sequence_size(byte_at(s, i))
    new: str = encode_char(c)
    if old == len(new):
        return copy_bytes(s, 0, i) + new + copy_bytes(s, i + old, len(s))
    return copy_bytes(s, 0, i) + new + copy_bytes(s, i + old, len(s))


def string_compare(s: str, t: str) -> i32:
    n: i32 = len(s)
    if len(t) < n:
        n = len(t)
    i: i32 = 0
    while i < n:
        a: i32 = byte_at(s, i)
        b: i32 = byte_at(t, i)
        if a != b:
            if a < b:
                return 0
            return 2
        i += 1
    if len(s) == len(t):
        return 1
    if len(s) < len(t):
        return 0
    return 2


def string_dec_eq(s: str, t: str) -> i32:
    if string_compare(s, t) == 1:
        return 1
    return 0


def string_dec_lt(s: str, t: str) -> i32:
    if string_compare(s, t) == 0:
        return 1
    return 0
