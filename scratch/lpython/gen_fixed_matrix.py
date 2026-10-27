
"""Generate `fixed_matrix.py` and `fixed_cases.json` from the case tables.

`fixed_ref.mjs` reads the cases and prints the reference results with the JavaScript runtime:

    node scratch/lpython/fixed_ref.mjs > /tmp/fixed_ref.txt
    lpython -I scratch/lpython scratch/lpython/fixed_matrix.py -o /tmp/fixed_matrix
    /tmp/fixed_matrix > /tmp/fixed_lp.txt
    diff /tmp/fixed_ref.txt /tmp/fixed_lp.txt
"""

import json
import sys
from pathlib import Path

here = Path(__file__).resolve().parent

TYPES = [
    ("UInt8", 8, 0),
    ("UInt16", 16, 0),
    ("UInt32", 32, 0),
    ("UInt64", 64, 0),
    ("Int8", 8, 1),
    ("Int16", 16, 1),
    ("Int32", 32, 1),
    ("Int64", 64, 1),
]
OPS = [
    ("add", 0, 2),
    ("sub", 1, 2),
    ("mul", 2, 2),
    ("div", 3, 2),
    ("mod", 4, 2),
    ("land", 5, 2),
    ("lor", 6, 2),
    ("xor", 7, 2),
    ("shiftLeft", 8, 2),
    ("shiftRight", 9, 2),
    ("decLt", 10, 2),
    ("decLe", 11, 2),
]
UNARY = [
    ("complement", 12),
    ("neg", 13),
    ("abs", 14),
    ("log2", 15),
]
VALUES = {
    8: [0, 1, 127, 128, 255],
    16: [0, 1, 32767, 32768, 65535],
    32: [0, 1, 2147483647, 2147483648, 4294967295],
    64: [0, 1, (1 << 63) - 1, 1 << 63, (1 << 64) - 1],
}

def lit(v):
    """An `i64` expression for the bit pattern `v`.

    LPython 0.22 mis-parses decimal literals above 2^53, so the value is assembled from two 32-bit
    halves, which are exact.
    """
    if v < (1 << 32):
        return f"i64({v})"
    hi = v >> 32
    lo = v & 0xFFFFFFFF
    if lo == 0:
        return f"(i64({hi}) << i64(32))"
    return f"((i64({hi}) << i64(32)) + i64({lo}))"


cases = []
for name, width, signed in TYPES:
    vals = VALUES[width]
    for oname, oid, arity in OPS:
        for a in vals:
            for b in vals:
                cases.append({"type": name, "width": width, "signed": signed, "op": oname, "id": oid, "a": a, "b": b})
    for oname, oid in UNARY:
        # `abs` is only defined on the signed types and `log2` only on the unsigned ones.
        if oname == "abs" and signed == 0:
            continue
        if oname == "log2" and signed == 1:
            continue
        for a in vals:
            cases.append({"type": name, "width": width, "signed": signed, "op": oname, "id": oid, "a": a, "b": None})

# Conversions between widths, sign-extended from signed sources and zero-extended otherwise.
conversions = [
    ("UInt8", 8, 0, "UInt16", 16),
    ("UInt8", 8, 0, "UInt64", 64),
    ("Int8", 8, 1, "Int16", 16),
    ("Int8", 8, 1, "UInt8", 8),
    ("Int8", 8, 1, "Int64", 64),
    ("UInt32", 32, 0, "UInt8", 8),
    ("Int32", 32, 1, "UInt8", 8),
    ("UInt64", 64, 0, "UInt32", 32),
    ("Int64", 64, 1, "Int32", 32),
]
for src_name, src_w, src_signed, dst_name, dst_w in conversions:
    for a in VALUES[src_w]:
        cases.append({"type": src_name, "width": src_w, "signed": src_signed, "op": "to" + dst_name, "id": 100 + dst_w, "a": a, "b": None})

# 64-bit values exceed the precision of a JSON number, so the node reference reads them as strings.
json.dump(
    [
        {**c, "a": str(c["a"]), "b": None if c["b"] is None else str(c["b"])}
        for c in cases
    ],
    (here / "fixed_cases.json").open("w"),
)
print(len(cases))

# LPython driver.
lines = []
lines.append('"""Conformance run for `fixed_lp.py`; prints one signed result per line."""')
lines.append("")
lines.append("from lpython import i32, i64")
lines.append("from fixed_lp import (")
for fn in ["add", "sub", "mul", "div", "mod", "land", "lor", "xor", "shift_left", "shift_right",
           "dec_lt", "dec_le", "complement", "neg", "abs_", "log2", "to_signed", "to_width"]:
    lines.append(f"    {fn},")
lines.append(")")
lines.append("")
lines.append("")
lines.append("def apply_op(op: i32, a: i64, b: i64, width: i32, signed: i32) -> i64:")
for oname, oid, arity in OPS:
    fn = {"shiftLeft": "shift_left", "shiftRight": "shift_right", "decLt": "dec_lt", "decLe": "dec_le"}.get(oname, oname)
    if fn == "shift_right":
        lines.append(f"    if op == {oid}:")
        lines.append(f"        return shift_right(a, b, width, signed)")
    elif fn in ("dec_lt", "dec_le"):
        lines.append(f"    if op == {oid}:")
        lines.append(f"        return i64({fn}(a, b, width, signed))")
    elif fn in ("div", "mod"):
        lines.append(f"    if op == {oid}:")
        lines.append(f"        return {fn}(a, b, width, signed)")
    else:
        lines.append(f"    if op == {oid}:")
        lines.append(f"        return {fn}(a, b, width)")
for oname, oid in UNARY:
    fn = {"abs": "abs_", "log2": "log2"}.get(oname, oname)
    if oname == "log2":
        lines.append(f"    if op == {oid}:")
        lines.append(f"        return log2(a, width)")
    else:
        lines.append(f"    if op == {oid}:")
        lines.append(f"        return {fn}(a, width)")
lines.append("    return i64(0)")
lines.append("")
lines.append("")
lines.append("def main():")
for c in cases:
    if c["op"].startswith("to") and c["id"] >= 100:
        dst_w = c["id"] - 100
        lines.append(f"    print(to_signed(to_width({lit(c['a'])}, {c['width']}, {c['signed']}, {dst_w}), {dst_w}))")
    elif c["b"] is None:
        lines.append(f"    print(to_signed(apply_op({c['id']}, {lit(c['a'])}, i64(0), {c['width']}, {c['signed']}), {c['width']}))")
    else:
        lines.append(f"    print(to_signed(apply_op({c['id']}, {lit(c['a'])}, {lit(c['b'])}, {c['width']}, {c['signed']}), {c['width']}))")
lines.append("")
lines.append("")
lines.append("main()")
(here / "fixed_matrix.py").write_text("\n".join(lines) + "\n")
print(len(lines))
