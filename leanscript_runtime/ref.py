"""`ST.Ref`, a mutable reference cell (see `Ref` in `core.py`).

Each extern follows the ownership conventions of its C counterpart: the ref itself is borrowed,
and a value stored in it is owned by the ref.
"""

from .core import Ref, dec, inc


def _mk_ref(_sigma, _alpha, a, _w):
    return Ref(a)


def _ref_get(_sigma, _alpha, r, _w):
    inc(r.value)
    return r.value


def _ref_put(_sigma, _alpha, r, a, _w):
    old = r.value
    r.value = a
    dec(old)
    return 0


def _ref_take(_sigma, _alpha, r, _w):
    # Leaves `()` behind, so that the value taken out may be exclusive.
    v = r.value
    r.value = 0
    return v


def _ref_set(_sigma, _alpha, r, a, _w):
    # `set` discards the old value, where `put` returns it.
    old = r.value
    r.value = a
    dec(old)
    return 0


def _ref_swap(_sigma, _alpha, r, a, _w):
    old = r.value
    r.value = a
    return old


def _ref_ptr_eq(_sigma, _alpha, r1, r2, _w):
    return 1 if r1 is r2 else 0


def _void_mk(_sigma, a):
    dec(a)
    return 0


externs = {
    "ST.Prim.mkRef": _mk_ref,
    "ST.Prim.Ref.get": _ref_get,
    "ST.Prim.Ref.put": _ref_put,
    "ST.Prim.Ref.take": _ref_take,
    "ST.Prim.Ref.set": _ref_set,
    "ST.Prim.Ref.swap": _ref_swap,
    "ST.Prim.Ref.ptrEq": _ref_ptr_eq,
    "Void.mk": _void_mk,
}
