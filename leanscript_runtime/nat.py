"""`Nat` and `Int`.

Python integers are arbitrary precision, so every value is a Python `int`. The JavaScript runtime
distinguishes safe integers from `BigInt`s to stay exact; that distinction has no counterpart here.
"""


def normalize(n):
    """Returns `n` as a normalized `Nat` or `Int`, which is already the case in Python."""
    return n


def nat_add(a, b):
    return a + b


def nat_sub(a, b):
    """Subtraction that saturates at zero."""
    return 0 if a < b else a - b


def nat_mul(a, b):
    return a * b


def nat_div(a, b):
    if b == 0:
        return 0
    return a // b


def nat_mod(a, b):
    if b == 0:
        return a
    return a % b


def nat_pow(a, b):
    return a**b


def nat_log2(a):
    if a == 0:
        return 0
    # The high bit of `a`, which is what `31 - Math.clz32(a)` computes for the values the JS
    # runtime keeps as numbers, and what the binary length computes for its `BigInt`s.
    return a.bit_length() - 1


def nat_shift_left(a, b):
    return a << b


def nat_shift_right(a, b):
    return a >> b


def nat_lor(a, b):
    return a | b


def nat_land(a, b):
    return a & b


def nat_xor(a, b):
    return a ^ b


def _trunc_div(a, b):
    """Division rounding toward zero, which Python's `//` does not do for negative operands."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _trunc_mod(a, b):
    """The remainder of `_trunc_div`, which has the sign of `a` as in JavaScript's `%`."""
    return a - _trunc_div(a, b) * b


def int_neg(a):
    return -a if a != 0 else 0


def int_add(a, b):
    return a + b


def int_sub(a, b):
    return a - b


def int_mul(a, b):
    return a * b


def int_tdiv(a, b):
    """Division rounding toward zero, where division by zero is zero."""
    if b == 0:
        return 0
    return _trunc_div(a, b)


def int_tmod(a, b):
    """The remainder of `int_tdiv`, which has the sign of `a`. The remainder of division by zero is
    `a`."""
    if b == 0:
        return a
    return _trunc_mod(a, b)


def int_emod(a, b):
    """The remainder of `int_ediv`, which is never negative. The remainder of division by zero is
    `a`."""
    r = int_tmod(a, b)
    if r < 0:
        return int_add(r, int_neg(b) if b < 0 else b)
    return r


def int_ediv(a, b):
    """Euclidean division, where division by zero is zero."""
    if b == 0:
        return 0
    q = int_tdiv(a, b)
    if int_tmod(a, b) >= 0:
        return q
    return int_sub(q, 1) if b > 0 else int_add(q, 1)


def nat_gcd(a, b):
    while b != 0:
        a, b = b, a % b
    return a


def nat_pow_mod(a, b, m):
    if m == 0:
        return nat_pow(a, b)
    base = a % m
    exp = b
    r = 1 % m
    while exp > 0:
        if exp & 1:
            r = (r * base) % m
        base = (base * base) % m
        exp >>= 1
    return r


def _bool(b):
    return 1 if b else 0


externs = {
    "Nat.add": nat_add,
    "Nat.sub": nat_sub,
    "Nat.mul": nat_mul,
    "Nat.div": nat_div,
    "Nat.mod": nat_mod,
    "Nat.pow": nat_pow,
    "Nat.log2": nat_log2,
    "Nat.shiftLeft": nat_shift_left,
    "Nat.shiftRight": nat_shift_right,
    "Nat.lor": nat_lor,
    "Nat.land": nat_land,
    "Nat.xor": nat_xor,
    "Nat.decEq": lambda a, b: _bool(a == b),
    "Nat.decLt": lambda a, b: _bool(a < b),
    "Nat.decLe": lambda a, b: _bool(a <= b),
    "Nat.beq": lambda a, b: _bool(a == b),
    "Nat.blt": lambda a, b: _bool(a < b),
    "Nat.ble": lambda a, b: _bool(a <= b),
    "Nat.pred": lambda a: nat_sub(a, 1),
    "Nat.divExact": lambda a, b, _h: nat_div(a, b),
    "Nat.gcd": nat_gcd,
    "Nat.powMod": nat_pow_mod,
    "Int.ofNat": lambda n: n,
    "Int.negSucc": lambda n: int_neg(nat_add(n, 1)),
    "Int.neg": int_neg,
    "Int.add": int_add,
    "Int.sub": int_sub,
    "Int.mul": int_mul,
    "Int.tdiv": int_tdiv,
    "Int.tmod": int_tmod,
    "Int.ediv": int_ediv,
    "Int.emod": int_emod,
    "Int.divExact": lambda a, b, _h: int_tdiv(a, b),
    "Int.decNonneg": lambda a: _bool(a >= 0),
    "Int.natAbs": lambda a: int_neg(a) if a < 0 else a,
    "Int.decEq": lambda a, b: _bool(a == b),
    "Int.decLt": lambda a, b: _bool(a < b),
    "Int.decLe": lambda a, b: _bool(a <= b),
}
