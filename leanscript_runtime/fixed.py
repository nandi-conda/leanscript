"""Fixed-width integers: `UInt8`, `UInt16`, `UInt32`, `UInt64`, `USize`, and their signed
counterparts `Int8`, `Int16`, `Int32`, `Int64`, and `ISize`.

As in the C runtime, a signed integer is stored as the unsigned integer with the same bits, so both
share a representation: a Python `int` in `[0, 2^w)`. We target a 32-bit platform, so `USize` and
`ISize` are 32 bits wide.
"""

from .float import float32_round
from .string import mk_string


def _trunc_div(x, y):
    """Division rounding toward zero."""
    q = abs(x) // abs(y)
    return -q if (x < 0) != (y < 0) else q


def _trunc_rem(x, y):
    """The remainder of `_trunc_div`, which has the sign of `x`."""
    return x - _trunc_div(x, y) * y


def _bool(b):
    return 1 if b else 0


class _FixedType:
    """A fixed-width integer type, described by the primitives that its externs derive from."""

    def __init__(self, name, width, signed):
        self.name = name
        self.width = width
        self.signed = signed
        self.mask = (1 << width) - 1
        self.half = 1 << (width - 1)
        self.zero = 0

    def of_integer(self, n):
        """Wraps the `Nat` or `Int` `n` to this width."""
        return n & self.mask

    def to_signed(self, a):
        """Returns the value of `a` as a signed Python `int`."""
        a &= self.mask
        return a - (1 << self.width) if a >= self.half else a

    def value(self, a):
        """Returns the value of `a`, signed if the type is."""
        return self.to_signed(a) if self.signed else a

    def to_integer(self, a):
        """Returns the value of `a` as a normalized `Nat` or `Int`."""
        return self.value(a)

    def add(self, a, b):
        return (a + b) & self.mask

    def sub(self, a, b):
        return (a - b) & self.mask

    def mul(self, a, b):
        # The low bits of the product are the same whether it is computed in 32 bits or more.
        return (a * b) & self.mask

    def div(self, x, y):
        return _trunc_div(x, y) & self.mask

    def rem(self, x, y):
        return _trunc_rem(x, y) & self.mask

    def land(self, a, b):
        return (a & b) & self.mask

    def lor(self, a, b):
        return (a | b) & self.mask

    def xor(self, a, b):
        return (a ^ b) & self.mask

    def complement(self, a):
        return (~a) & self.mask

    def shift_left(self, a, s):
        return (a << s) & self.mask

    def shift_right(self, a, s):
        if self.signed:
            return (self.to_signed(a) >> s) & self.mask
        return a >> s

    def log2(self, a):
        return 0 if a == 0 else a.bit_length() - 1

    def abs(self, a):
        return abs(self.to_signed(a)) & self.mask

    def shift_amount(self, b):
        # The width is a power of two, so the low bits of `b` are its remainder modulo the width
        # whether `b` is read as unsigned or as signed (as `BitVec.smod` does for signed types).
        return b & (self.width - 1)


_TYPES = (
    _FixedType("UInt8", 8, False),
    _FixedType("UInt16", 16, False),
    _FixedType("UInt32", 32, False),
    _FixedType("UInt64", 64, False),
    _FixedType("USize", 32, False),
    _FixedType("Int8", 8, True),
    _FixedType("Int16", 16, True),
    _FixedType("Int32", 32, True),
    _FixedType("Int64", 64, True),
    _FixedType("ISize", 32, True),
)


def _fixed_width_externs(t):
    """Returns the externs of the type `t`, with the semantics of the corresponding `BitVec` ops."""
    ext = {
        "add": t.add,
        "sub": t.sub,
        "mul": t.mul,
        # Division by zero is zero, and the remainder of division by zero is the dividend.
        "div": lambda a, b: t.zero if b == t.zero else t.div(t.value(a), t.value(b)),
        "mod": lambda a, b: a if b == t.zero else t.rem(t.value(a), t.value(b)),
        "land": t.land,
        "lor": t.lor,
        "xor": t.xor,
        "complement": t.complement,
        "neg": lambda a: t.sub(t.zero, a),
        "shiftLeft": lambda a, b: t.shift_left(a, t.shift_amount(b)),
        "shiftRight": lambda a, b: t.shift_right(a, t.shift_amount(b)),
        "decEq": lambda a, b: _bool(a == b),
        "decLt": lambda a, b: _bool(t.value(a) < t.value(b)),
        "decLe": lambda a, b: _bool(t.value(a) <= t.value(b)),
        "ofNat": t.of_integer,
        "ofNatLT": lambda n, _h: t.of_integer(n),
        "ofBitVec": t.of_integer,
        "toBitVec": lambda a: a,
        "toFloat": lambda a: float(t.value(a)),
        "toFloat32": lambda a: float32_round(float(t.value(a))),
    }
    if t.signed:
        ext["ofInt"] = t.of_integer
        ext["toInt"] = t.to_integer
        ext["abs"] = t.abs
    else:
        ext["toNat"] = t.to_integer
        ext["log2"] = t.log2
    # Conversions between widths sign-extend from a signed type and zero-extend from an unsigned
    # one.
    for target in _TYPES:
        if target is not t:
            ext["to" + target.name] = (
                lambda a, source=t, dest=target: dest.of_integer(source.to_integer(a))
            )
    return {t.name + "." + op: fn for op, fn in ext.items()}


externs = {}
for _t in _TYPES:
    externs.update(_fixed_width_externs(_t))
externs.update(
    {
        "USize.ofNat32": lambda n, _h: n,
        "USize.repr": lambda n: mk_string(str(n)),
        "System.Platform.getNumBits": lambda _unit: 32,
    }
)
del _t
