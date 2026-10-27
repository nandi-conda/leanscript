"""`Float` and `Float32`.

`Float` is a Python `float`, which is IEEE 754 binary64. `Float32` is also a Python `float`, kept
rounded to binary32 after every operation.
"""

import math
import struct

from .core import Ctor
from .string import mk_string

_F64 = struct.Struct("<d")
_U64 = struct.Struct("<Q")
_F32 = struct.Struct("<f")
_U32 = struct.Struct("<I")

_F64_MANTISSA = (1 << 52) - 1
_F32_MANTISSA = (1 << 23) - 1


def float_of_bits(b):
    """Returns the binary64 float with the bit pattern `b`."""
    return _F64.unpack(_U64.pack(b & ((1 << 64) - 1)))[0]


def float_to_bits(x):
    """Returns the bit pattern of the binary64 float `x`."""
    return _U64.unpack(_F64.pack(float(x)))[0]


def float32_of_bits(b):
    """Returns the binary32 float with the bit pattern `b`, as a binary64 value."""
    return _F32.unpack(_U32.pack(b & 0xFFFFFFFF))[0]


def float32_round(x):
    """Rounds `x` to binary32, like `Math.fround`."""
    try:
        return _F32.unpack(_F32.pack(x))[0]
    except OverflowError:
        # `struct` reports a value too large for binary32, where IEEE arithmetic rounds to
        # infinity.
        return math.inf if x > 0 else -math.inf


def float32_to_bits(x):
    """Returns the bit pattern of `x` rounded to binary32."""
    return _U32.unpack(_F32.pack(float32_round(x)))[0]


def _pow2(n):
    """Returns `2^n` as a binary64 float, for the exponents `scalbn` uses."""
    return 2.0**n


def _format_fixed6(x):
    """Formats a finite float with six digits after the decimal point, exactly like C's `%f`.

    Python's `format(x, ".6f")` rounds the exact binary value to nearest with ties to even, so it
    agrees with `%f` on the digits. It differs only for a value whose integer part is large enough
    that the conversion is not exact, so the digits are computed from the bits instead.
    """
    negative = x < 0 or (x == 0 and math.copysign(1.0, x) < 0)
    b = float_to_bits(abs(x))
    exponent = b >> 52
    mantissa = b & _F64_MANTISSA
    if exponent == 0:
        exponent = 1
    else:
        mantissa |= 1 << 52
    # |x| = mantissa * 2^(exponent - 1075), so |x| * 10^6 = num / den.
    num = mantissa * 10**6
    den = 1
    if exponent >= 1075:
        num <<= exponent - 1075
    else:
        den <<= 1075 - exponent
    q = num // den
    twice_rem = 2 * (num % den)
    if twice_rem > den or (twice_rem == den and (q & 1) == 1):
        q += 1
    digits = str(q).rjust(7, "0")
    return ("-" if negative else "") + digits[:-6] + "." + digits[-6:]


def float_to_string(x):
    """Formats `x` as `Float.toString` does: `NaN`, `inf`, `-inf`, or six decimal places."""
    if math.isnan(x):
        return "NaN"
    if x == math.inf:
        return "inf"
    if x == -math.inf:
        return "-inf"
    return _format_fixed6(x)


def _scalbn(x, n):
    """`x * 2^n` with a single rounding, like C's `scalbn` (this is musl's algorithm)."""
    if n > 1023:
        x *= _pow2(1023)
        n -= 1023
        if n > 1023:
            x *= _pow2(1023)
            n -= 1023
            n = min(n, 1023)
    elif n < -1022:
        # Scaling by 2^-1022 * 2^53 keeps intermediate results normal, so only the last step
        # rounds.
        x *= _pow2(-1022) * _pow2(53)
        n += 1022 - 53
        if n < -1022:
            x *= _pow2(-1022) * _pow2(53)
            n += 1022 - 53
            n = max(n, -1022)
    return x * _pow2(n)


def _clamp_exponent(n):
    """Converts the `Int` `n` to an exponent for `_scalbn`, saturating where the result is 0 or
    ±inf."""
    return max(-10000, min(10000, n))


def _frexp(x):
    """Splits `x` into a mantissa in `[0.5, 1)` and an exponent, like C's `frexp`."""
    if x == 0 or not math.isfinite(x):
        return (x, 0)
    e = 0
    if abs(x) < _pow2(-1022):
        x *= _pow2(54)
        e -= 54
    biased = (float_to_bits(x) >> 52) & 0x7FF
    e += biased - 1022
    return (x * _pow2(-(biased - 1022)), e)


def _decompose(x):
    """Returns `(m, e)` with `x = m * 2^e` exactly, for finite `x`."""
    b = float_to_bits(x)
    biased = (b >> 52) & 0x7FF
    m = b & _F64_MANTISSA
    if biased != 0:
        m |= 1 << 52
    return (-m if x < 0 else m, max(biased, 1) - 1075)


def _fma(a, b, c):
    """`a * b + c` with a single rounding, like C's `fma`."""
    if not math.isfinite(a) or not math.isfinite(b) or not math.isfinite(c) or a * b == 0:
        return a * b + c
    ma, ea = _decompose(a)
    mb, eb = _decompose(b)
    mc, ec = _decompose(c)
    e = min(ea + eb, ec)
    m = ((ma * mb) << (ea + eb - e)) + (mc << (ec - e))
    if m == 0:
        # An exact zero sum is +0 in round-to-nearest, unless both addends are -0.
        return a * b + c
    return _round_scaled(m, e)


def _round_scaled(m, e):
    """Rounds `m * 2^e` to the nearest double, with ties to even."""
    negative = m < 0
    mag = -m if negative else m
    # Keep 54 significant bits plus a sticky bit, so that `float` rounds exactly once, then scale.
    excess = mag.bit_length() - 55
    if excess > 0:
        sticky = 1 if (mag & ((1 << excess) - 1)) != 0 else 0
        mag = (mag >> excess) | sticky
        e += excess
    # `_scalbn` rounds again only if the result is subnormal, where precision is already reduced.
    r = _scalbn(float(mag), e)
    return -r if negative else r


def _round_half_away(x):
    """C's `round`: rounds to the nearest integer, with ties away from zero."""
    if not math.isfinite(x):
        return x
    t = math.trunc(x)
    if abs(x - t) >= 0.5:
        t += 1 if x > 0 else -1
    if t == 0:
        # Preserve the sign of zero, which `math.trunc` loses.
        return math.copysign(0.0, x)
    return float(t)


def _to_unsigned(max_value):
    """Converts to an unsigned integer type with maximum `max_value`, saturating and mapping NaN to
    0."""

    def convert(a):
        if math.isnan(a):
            return 0
        if a >= 0:
            if a < max_value + 1:
                return math.trunc(a)
            return max_value
        return 0

    return convert


def _to_signed(width):
    """Converts to a signed integer type of width `width`, saturating and mapping NaN to 0."""
    mask = (1 << width) - 1
    minimum = -(1 << (width - 1))
    limit = 1 << (width - 1)

    def convert(a):
        if math.isnan(a):
            r = 0
        elif minimum - 1 < a:
            r = math.trunc(a) if a < limit else -minimum - 1
        else:
            r = minimum
        return r & mask

    return convert


def _to_uint64(a):
    if math.isnan(a):
        return 0
    if a >= 0:
        if a < 1 << 64:
            return math.trunc(a)
        return (1 << 64) - 1
    return 0


def _to_int64(a):
    if math.isnan(a):
        r = 0
    elif -(1 << 63) <= a:
        r = math.trunc(a) if a < 1 << 63 else (1 << 63) - 1
    else:
        r = -(1 << 63)
    return r & ((1 << 64) - 1)


def _ceil(a):
    if not math.isfinite(a):
        return a
    r = math.ceil(a)
    return math.copysign(0.0, a) if r == 0 else float(r)


def _floor(a):
    if not math.isfinite(a):
        return a
    r = math.floor(a)
    return math.copysign(0.0, a) if r == 0 else float(r)


def _sin(a):
    try:
        return math.sin(a)
    except ValueError:
        return math.nan


def _cos(a):
    try:
        return math.cos(a)
    except ValueError:
        return math.nan


def _tan(a):
    try:
        return math.tan(a)
    except ValueError:
        return math.nan


def _asin(a):
    try:
        return math.asin(a)
    except ValueError:
        return math.nan


def _acos(a):
    try:
        return math.acos(a)
    except ValueError:
        return math.nan


def _sinh(a):
    try:
        return math.sinh(a)
    except OverflowError:
        return math.copysign(math.inf, a)


def _cosh(a):
    try:
        return math.cosh(a)
    except OverflowError:
        return math.inf


def _acosh(a):
    try:
        return math.acosh(a)
    except ValueError:
        return math.nan


def _atanh(a):
    if a > 1 or a < -1:
        return math.nan
    if a == 1:
        return math.inf
    if a == -1:
        return -math.inf
    return math.atanh(a)


def _exp(a):
    try:
        return math.exp(a)
    except OverflowError:
        return math.inf


def _log(a):
    if a == 0:
        return -math.inf
    if a < 0:
        return math.nan
    return math.log(a)


def _log2(a):
    if a == 0:
        return -math.inf
    if a < 0:
        return math.nan
    return math.log2(a)


def _log10(a):
    if a == 0:
        return -math.inf
    if a < 0:
        return math.nan
    return math.log10(a)


def _sqrt(a):
    if a < 0:
        return math.nan
    return math.sqrt(a)


def _div(a, b):
    """`a / b` with JavaScript's division by zero, which Python raises instead."""
    if b == 0:
        if math.isnan(a) or a == 0:
            return math.nan
        return math.copysign(math.inf, math.copysign(1.0, a) * math.copysign(1.0, b))
    return a / b


def _is_odd_integer(b):
    return math.isfinite(b) and b == math.floor(b) and math.fmod(b, 2.0) != 0


def _pow(a, b):
    """`a ** b` with the special cases of JavaScript's `Math.pow`, which the runtime uses."""
    if math.isnan(b):
        return math.nan
    if b == 0:
        return 1.0
    if math.isnan(a):
        return math.nan
    if math.isinf(b):
        magnitude = abs(a)
        if magnitude == 1.0:
            return math.nan
        return math.inf if (magnitude > 1) == (b > 0) else 0.0
    if a == 1.0:
        return 1.0
    try:
        return math.pow(a, b)
    except OverflowError:
        return -math.inf if (a < 0 and _is_odd_integer(b)) else math.inf
    except ValueError:
        if a == 0.0 and b < 0:
            negative_zero = math.copysign(1.0, a) < 0
            return -math.inf if (negative_zero and _is_odd_integer(b)) else math.inf
        return math.nan


def _exp2(a):
    return _pow(2.0, a)


def _bool(b):
    return 1 if b else 0


def _float_externs(name, round_, of_bits, to_bits):
    """Returns the externs of `Float` or `Float32`, where `round_` rounds a result to the type's
    precision."""

    def unary(f):
        def apply(a):
            return round_(f(a))

        return apply

    ext = {
        "ofBits": of_bits,
        # The bit-level model of an IEEE 754 float is its bit pattern.
        "ofModel": of_bits,
        "toBits": to_bits,
        "toModel": to_bits,
        "add": lambda a, b: round_(a + b),
        "sub": lambda a, b: round_(a - b),
        "mul": lambda a, b: round_(a * b),
        "div": lambda a, b: round_(_div(a, b)),
        "neg": lambda a: -a,
        "abs": abs,
        "decLt": lambda a, b: _bool(a < b),
        "decLe": lambda a, b: _bool(a <= b),
        "lt": lambda a, b: _bool(a < b),
        "le": lambda a, b: _bool(a <= b),
        "beq": lambda a, b: _bool(a == b),
        "isNaN": lambda a: _bool(math.isnan(a)),
        "isFinite": lambda a: _bool(math.isfinite(a)),
        "isInf": lambda a: _bool(math.isinf(a)),
        "toString": lambda x: mk_string(float_to_string(x)),
        "sin": unary(_sin),
        "cos": unary(_cos),
        "tan": unary(_tan),
        "asin": unary(_asin),
        "acos": unary(_acos),
        "atan": unary(math.atan),
        "atan2": lambda a, b: round_(math.atan2(a, b)),
        "sinh": unary(_sinh),
        "cosh": unary(_cosh),
        "tanh": unary(math.tanh),
        "asinh": unary(math.asinh),
        "acosh": unary(_acosh),
        "atanh": unary(_atanh),
        "exp": unary(_exp),
        "exp2": unary(_exp2),
        "log": unary(_log),
        "log2": unary(_log2),
        "log10": unary(_log10),
        "pow": lambda a, b: round_(_pow(a, b)),
        "sqrt": unary(_sqrt),
        "cbrt": unary(math.cbrt),
        "ceil": _ceil,
        "floor": _floor,
        "round": _round_half_away,
        "fma": lambda a, b, c: round_(_fma(a, b, c)),
        "scaleB": lambda a, n: round_(_scalbn(a, _clamp_exponent(n))),
        "frExp": lambda a: Ctor(0, list(_frexp(a)), None),
        "toUInt8": _to_unsigned(0xFF),
        "toUInt16": _to_unsigned(0xFFFF),
        "toUInt32": _to_unsigned(0xFFFFFFFF),
        "toUInt64": _to_uint64,
        "toUSize": _to_unsigned(0xFFFFFFFF),
        "toInt8": _to_signed(8),
        "toInt16": _to_signed(16),
        "toInt32": _to_signed(32),
        "toInt64": _to_int64,
        "toISize": _to_signed(32),
        "toFloat": lambda a: a,
        "toFloat32": float32_round,
    }
    return {name + "." + op: fn for op, fn in ext.items()}


externs = {}
externs.update(_float_externs("Float", lambda a: a, float_of_bits, float_to_bits))
externs.update(_float_externs("Float32", float32_round, float32_of_bits, float32_to_bits))
