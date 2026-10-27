"""`ByteArray`, represented as a byte buffer with a reference count.

Each extern follows the ownership conventions of its C counterpart: an exclusive byte array is
updated in place, and a shared one is copied first.
"""

from __future__ import annotations

from .array import mk_array
from .core import dec, track
from .hash import hash_bytes


class ByteArray:
    """A Lean `ByteArray`: a `bytearray` holding its exact bytes, with a reference count."""

    def __init__(self, data: bytearray) -> None:
        self.rc = 1
        self.data = data
        track(self)

    def __len__(self) -> int:
        return len(self.data)

    def describe(self) -> str:
        return f"byte array of size {len(self.data)}"


def mk_byte_array(raw, size: int | None = None) -> ByteArray:
    """Returns a new byte array containing a copy of the first `size` bytes of `raw`."""
    contents = raw[:size] if size is not None else raw
    return ByteArray(bytearray(contents))


def _reserve(a: ByteArray) -> ByteArray:
    """Takes ownership of `a` and returns an exclusive byte array with its contents."""
    if a.rc == 1:
        return a
    r = ByteArray(bytearray(a.data))
    dec(a)
    return r


def _uset(a: ByteArray, i: int, v: int) -> ByteArray:
    r = _reserve(a)
    r.data[i] = v
    return r


def _bytes_eq(a: ByteArray, b: ByteArray) -> bool:
    return a.data == b.data


def _mk(data) -> ByteArray:
    r = ByteArray(bytearray(v & 0xFF for v in data))
    dec(data)
    return r


def _data(a: ByteArray):
    r = mk_array([b for b in a.data])
    dec(a)
    return r


def _get_byte(a: ByteArray, i: int) -> int:
    """Returns the byte at `i`, or 0 out of bounds."""
    return a.data[i] if 0 <= i < len(a.data) else 0


def _set_if_in_bounds(a: ByteArray, i: int, v: int) -> ByteArray:
    return _uset(a, i, v) if 0 <= i < len(a.data) else a


def _push(a: ByteArray, v: int) -> ByteArray:
    r = _reserve(a)
    r.data.append(v & 0xFF)
    return r


def _copy_slice(
    src: ByteArray, src_off: int, dest: ByteArray, dest_off: int, length: int, _exact
) -> ByteArray:
    """Copies `src[src_off, src_off + length)` over `dest` starting at `dest_off`.

    Offsets past the end are clamped, as in the reference implementation.
    """
    start = min(src_off, len(src.data))
    n = min(length, len(src.data) - start)
    at = min(dest_off, len(dest.data))
    suffix = min(dest_off + n, len(dest.data))
    data = dest.data[:at] + src.data[start : start + n] + dest.data[suffix:]
    dec(dest)
    return ByteArray(bytearray(data))


def _validate_utf8(a: ByteArray) -> int:
    try:
        bytes(a.data).decode("utf-8")
    except UnicodeDecodeError:
        return 0
    return 1


def _bool(b: bool) -> int:
    return int(b)


externs = {
    "ByteArray.mk": _mk,
    "ByteArray.data": _data,
    "ByteArray.emptyWithCapacity": lambda _capacity: ByteArray(bytearray()),
    "ByteArray.size": lambda a: len(a.data),
    "ByteArray.usize": lambda a: len(a.data),
    "ByteArray.get": lambda a, i, _h: _get_byte(a, i),
    # Like `lean_byte_array_get`, this returns 0 out of bounds without panicking.
    "ByteArray.get!": _get_byte,
    "ByteArray.uget": lambda a, i, _h: _get_byte(a, i),
    "ByteArray.set": lambda a, i, v, _h: _uset(a, i, v),
    "ByteArray.set!": _set_if_in_bounds,
    "ByteArray.uset": lambda a, i, v, _h: _uset(a, i, v),
    "ByteArray.push": _push,
    "ByteArray.copySlice": _copy_slice,
    "ByteArray.beq": lambda a, b: _bool(_bytes_eq(a, b)),
    "ByteArray.decEq": lambda a, b: _bool(_bytes_eq(a, b)),
    "ByteArray.hash": lambda a: hash_bytes(bytes(a.data), len(a.data), 11),
    # Byte arrays are never marked linear, so there is no mark to set or propagate.
    "ByteArray.markLinear": lambda a: a,
    "ByteArray.propagateMark": lambda _a, b: b,
    "ByteArray.validateUTF8": _validate_utf8,
}
