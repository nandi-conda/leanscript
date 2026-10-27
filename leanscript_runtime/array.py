"""`Array`, represented as a Python list subclass with a reference count.

Each extern follows the ownership conventions of its C counterpart: an exclusive array is updated
in place, and a shared one is copied first.
"""

from __future__ import annotations

from .core import array_to_list, dec, inc, inc_n, list_to_array, panic, track

OUT_OF_BOUNDS = "Error: index out of bounds"


class LeanArray(list):
    """A Lean `Array`: a list of owned references with a reference count."""

    __slots__ = ("rc", "_refs")

    def __init__(self, items=()) -> None:
        super().__init__(items)
        self.rc = 1
        # Whether any element is reference counted. Copying an array of scalars needs no per-element
        # work, which matters because a shared array is copied on every update.
        self._refs = any(type(x) is not int for x in self)
        track(self)

    def _children(self):
        """Returns the elements, which the array owns."""
        return self

    def describe(self) -> str:
        return f"array of size {len(self)}"


def mk_array(items) -> LeanArray:
    """Makes a Lean `Array` owning the elements of `items`."""
    return LeanArray(items)


def _copy(a: LeanArray) -> LeanArray:
    """Returns an exclusive copy of `a`, sharing its elements."""
    r = LeanArray.__new__(LeanArray)
    list.__init__(r, a)
    r.rc = 1
    r._refs = a._refs
    track(r)
    if r._refs:
        for x in r:
            inc(x)
    return r


def _ensure_exclusive(a: LeanArray) -> LeanArray:
    """Takes ownership of `a` and returns an exclusive array with the same elements."""
    if a.rc == 1:
        return a
    r = _copy(a)
    dec(a)
    return r


def _get_owned(a: LeanArray, i: int):
    """Returns the element at `i` as an owned reference."""
    x = a[i]
    inc(x)
    return x


def _set(a: LeanArray, i: int, v) -> LeanArray:
    r = _ensure_exclusive(a)
    dec(r[i])
    r[i] = v
    if type(v) is not int:
        r._refs = True
    return r


def _get_or_panic(d, a: LeanArray, i: int):
    return a[i] if 0 <= i < len(a) else panic(d, OUT_OF_BOUNDS)


def _get_owned_or_panic(_α, d, a: LeanArray, i: int):
    x = _get_or_panic(d, a, i)
    inc(x)
    return x


def _mk(_α, lst):
    xs = list_to_array(lst)
    for x in xs:
        inc(x)
    dec(lst)
    return mk_array(xs)


def _mk_empty(_α, _capacity) -> LeanArray:
    return mk_array([])


def _to_list(_α, a: LeanArray):
    for x in a:
        inc(x)
    lst = array_to_list(list(a))
    dec(a)
    return lst


def _replicate(_α, n: int, v) -> LeanArray:
    if n > 0xFFFFFFFF:
        raise MemoryError("LeanScript: out of memory")
    if n == 0:
        dec(v)
    else:
        inc_n(v, n - 1)
    return mk_array([v] * n)


def _swap_if_in_bounds(_α, a: LeanArray, i: int, j: int) -> LeanArray:
    if not (0 <= i < len(a) and 0 <= j < len(a)):
        return a
    r = _ensure_exclusive(a)
    r[i], r[j] = r[j], r[i]
    return r


def _push(_α, a: LeanArray, v) -> LeanArray:
    r = _ensure_exclusive(a)
    r.append(v)
    if type(v) is not int:
        r._refs = True
    return r


def _pop(_α, a: LeanArray) -> LeanArray:
    if not a:
        return a
    r = _ensure_exclusive(a)
    dec(r.pop())
    return r


def _set_or_panic(_α, a: LeanArray, i: int, v) -> LeanArray:
    if 0 <= i < len(a):
        return _set(a, i, v)
    dec(v)
    return panic(a, OUT_OF_BOUNDS)


def _swap(_α, a: LeanArray, i: int, j: int, _hi: int, _hj: int) -> LeanArray:
    r = _ensure_exclusive(a)
    r[i], r[j] = r[j], r[i]
    return r


externs = {
    "Array.mk": _mk,
    "Array.mkEmpty": _mk_empty,
    "Array.emptyWithCapacity": _mk_empty,
    "Array.toList": _to_list,
    "Array.replicate": _replicate,
    # Arrays are never marked linear, so there is no mark to set or propagate.
    "Array.markLinear": lambda _α, a: a,
    "Array.propagateMark": lambda _α, _β, _xs, ys: ys,
    "Array.swapIfInBounds": _swap_if_in_bounds,
    "Array.size": lambda _α, a: len(a),
    "Array.usize": lambda _α, a: len(a),
    "Array.getInternal": lambda _α, a, i, _h: _get_owned(a, i),
    "Array.getInternalBorrowed": lambda _α, a, i, _h: a[i],
    "Array.get!Internal": _get_owned_or_panic,
    "Array.get!InternalBorrowed": lambda _α, d, a, i: _get_or_panic(d, a, i),
    "Array.uget": lambda _α, a, i, _h: _get_owned(a, i),
    "Array.ugetBorrowed": lambda _α, a, i, _h: a[i],
    "Array.push": _push,
    "Array.pop": _pop,
    "Array.set": lambda _α, a, i, v, _h: _set(a, i, v),
    "Array.uset": lambda _α, a, i, v, _h: _set(a, i, v),
    "Array.set!": _set_or_panic,
    "Array.swap": _swap,
}
