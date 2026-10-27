"""Fixed-width integer primitives for LPython 0.22.

A fixed-width integer is stored as its unsigned bit pattern in an `i64`, exactly as the C and
JavaScript runtime store it. LPython `i64` arithmetic wraps, so masking with the width's bit mask
reproduces the reference semantics; the sign is only applied when a value is observed.

`width` is 8, 16, 32, or 64, and `signed` is 1 for the signed types and 0 for the unsigned ones.
`USize` and `ISize` are 32 bits wide, as the reference targets a 32-bit platform.
"""

from lpython import i32, i64


def mask(width: i32) -> i64:
    if width >= 64:
        return i64(-1)
    return (i64(1) << i64(width)) - i64(1)


def wrap(x: i64, width: i32) -> i64:
    """Wraps `x` to the unsigned bit pattern of `width` bits."""
    return x & mask(width)


def to_signed(x: i64, width: i32) -> i64:
    """Reads the bit pattern `x` as a signed value of `width` bits."""
    if width >= 64:
        return x
    half: i64 = i64(1) << i64(width - 1)
    if x >= half:
        return x - (i64(1) << i64(width))
    return x


def to_integer(x: i64, width: i32, signed: i32) -> i64:
    """Reads the bit pattern `x` as the `Nat` or `Int` it represents."""
    if signed == 1:
        return to_signed(x, width)
    return x


def of_integer(n: i64, width: i32) -> i64:
    """Wraps the `Nat` or `Int` `n` to the bit pattern of `width` bits."""
    return wrap(n, width)


def add(a: i64, b: i64, width: i32) -> i64:
    return wrap(a + b, width)


def sub(a: i64, b: i64, width: i32) -> i64:
    return wrap(a - b, width)


def mul(a: i64, b: i64, width: i32) -> i64:
    return wrap(a * b, width)


def tdiv(a: i64, b: i64) -> i64:
    """Division rounding toward zero."""
    q: i64 = a // b
    if a % b != i64(0):
        if (a < i64(0)) != (b < i64(0)):
            q += i64(1)
    return q


def trem(a: i64, b: i64) -> i64:
    """The remainder of `tdiv`, which has the sign of `a`."""
    return a - tdiv(a, b) * b



def u_lt(a: i64, b: i64) -> i32:
    """Compares two unsigned 64-bit patterns, which may read as negative `i64`s."""
    flip: i64 = i64(1) << i64(63)
    if (a ^ flip) < (b ^ flip):
        return 1
    return 0


def udiv64(a: i64, b: i64) -> i64:
    """Unsigned 64-bit division on bit patterns, which LPython's `u64` does not compute correctly."""
    if b == i64(0):
        return i64(0)
    top: i64 = i64(1) << i64(63)
    if not u_lt(b, top):
        if u_lt(a, b):
            return i64(0)
        return i64(1)
    q: i64 = i64(0)
    r: i64 = i64(0)
    i: i32 = 63
    while i >= 0:
        r = (r << i64(1)) | ((a >> i64(i)) & i64(1))
        if not u_lt(r, b):
            r = r - b
            q = q | (i64(1) << i64(i))
        i -= 1
    return q


def umod64(a: i64, b: i64) -> i64:
    if b == i64(0):
        return a
    return a - udiv64(a, b) * b


def div(a: i64, b: i64, width: i32, signed: i32) -> i64:
    """Division by zero is zero."""
    if b == i64(0):
        return i64(0)
    if signed == 0 and width >= 64:
        return udiv64(a, b)
    return wrap(tdiv(to_integer(a, width, signed), to_integer(b, width, signed)), width)


def mod(a: i64, b: i64, width: i32, signed: i32) -> i64:
    """The remainder of division by zero is the dividend."""
    if b == i64(0):
        return a
    if signed == 0 and width >= 64:
        return umod64(a, b)
    return wrap(trem(to_integer(a, width, signed), to_integer(b, width, signed)), width)


def land(a: i64, b: i64, width: i32) -> i64:
    return wrap(a & b, width)


def lor(a: i64, b: i64, width: i32) -> i64:
    return wrap(a | b, width)


def xor(a: i64, b: i64, width: i32) -> i64:
    return wrap(a ^ b, width)


def complement(a: i64, width: i32) -> i64:
    return wrap(~a, width)


def neg(a: i64, width: i32) -> i64:
    return wrap(-a, width)


def shift_left(a: i64, b: i64, width: i32) -> i64:
    return wrap(a << (b & i64(width - 1)), width)


def shift_right(a: i64, b: i64, width: i32, signed: i32) -> i64:
    s: i64 = b & i64(width - 1)
    if signed == 1:
        return wrap(to_signed(a, width) >> s, width)
    if width >= 64:
        if s == i64(0):
            return a
        # `a` may have the sign bit set, so shift logically.
        return (a >> s) & ((i64(1) << (i64(64) - s)) - i64(1))
    return a >> s


def abs_(a: i64, width: i32) -> i64:
    v: i64 = to_signed(a, width)
    if v < i64(0):
        return wrap(-v, width)
    return a


def log2(a: i64, width: i32) -> i64:
    if a == i64(0):
        return i64(0)
    n: i64 = i64(0)
    x: i64 = a
    while x != i64(0):
        x = shift_right(x, i64(1), width, 0)
        n += i64(1)
    return n - i64(1)


def dec_lt(a: i64, b: i64, width: i32, signed: i32) -> i32:
    if signed == 0 and width >= 64:
        return u_lt(a, b)
    if to_integer(a, width, signed) < to_integer(b, width, signed):
        return 1
    return 0


def dec_le(a: i64, b: i64, width: i32, signed: i32) -> i32:
    if signed == 0 and width >= 64:
        return 1 - u_lt(b, a)
    if to_integer(a, width, signed) <= to_integer(b, width, signed):
        return 1
    return 0


def to_width(a: i64, from_width: i32, signed: i32, to_width_: i32) -> i64:
    """Conversion between widths, sign-extending from a signed source and zero-extending otherwise."""
    return wrap(to_integer(a, from_width, signed), to_width_)
