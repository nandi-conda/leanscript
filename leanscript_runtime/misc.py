"""`Bool` conversions, `Thunk`, and debugging and unsafe primitives."""

import time

from .core import Thunk, apply, dec, inc, is_shared, write_stderr

# Stable, distinct numbers standing in for object addresses. Heap objects do not support weak
# references, so the table keeps the object itself, which also keeps its id from being reused for
# another object during the run.
_addresses = {}
_next_address = 1


def _address(x):
    global _next_address
    if not _is_object(x):
        return 0
    entry = _addresses.get(id(x))
    if entry is None or entry[0] is not x:
        entry = (x, _next_address)
        _next_address += 1
        _addresses[id(x)] = entry
    return entry[1]


def _is_object(x):
    """Returns whether `x` is a heap object, as `typeof x === "object"` does in JavaScript."""
    return not isinstance(x, (int, float))


def _bool(b):
    return 1 if b else 0


def _thunk_mk(_alpha, fn):
    return Thunk(fn)


def _thunk_pure(_alpha, a):
    return Thunk(None, a)


def _thunk_get(_alpha, t):
    if t.fn is not None:
        fn = t.fn
        t.fn = None
        t.value = apply(fn, [0])
    inc(t.value)
    return t.value


def _dbg_trace(_alpha, msg, fn):
    write_stderr(f"{msg}\n")
    dec(msg)
    return apply(fn, [0])


def _dbg_trace_if_shared(_alpha, msg, a):
    if _is_object(a) and is_shared(a):
        write_stderr(f"shared RC {msg}\n")
    return a


def _dbg_sleep(_alpha, ms, fn):
    time.sleep(ms / 1000.0)
    return apply(fn, [0])


def _timeit(_alpha, msg, fn, _w):
    start = time.perf_counter()
    r = apply(fn, [0])
    # JavaScript's `toPrecision(3)` and Python's `.3g` agree on the digits; not on the exponent
    # spelling, which does not matter here.
    write_stderr(f"{msg} {format((time.perf_counter() - start) / 1000.0, '.3g')}s\n")
    return r


def _is_exclusive_unsafe(_alpha, a):
    return _bool(_is_object(a) and is_shared(a) == 0)


def _is_scalar_obj(_alpha, a):
    r = 0 if _is_object(a) else 1
    dec(a)
    return r


def _sorry_ax(_alpha, _synthetic):
    raise RuntimeError("LeanScript: executed 'sorry'")


externs = {
    "Bool.toUInt8": lambda b: b,
    "Bool.toUInt16": lambda b: b,
    "Bool.toUInt32": lambda b: b,
    "Bool.toUInt64": lambda b: int(b),
    "Bool.toUSize": lambda b: b,
    "Bool.toInt8": lambda b: b,
    "Bool.toInt16": lambda b: b,
    "Bool.toInt32": lambda b: b,
    "Bool.toInt64": lambda b: int(b),
    "Bool.toISize": lambda b: b,
    # Evaluating both arguments is the point of these, which the caller has already done.
    "strictAnd": lambda a, b: a & b,
    "strictOr": lambda a, b: a | b,
    "Thunk.mk": _thunk_mk,
    "Thunk.pure": _thunk_pure,
    "Thunk.get": _thunk_get,
    "dbgTrace": _dbg_trace,
    "dbgTraceIfShared": _dbg_trace_if_shared,
    "dbgStackTrace": lambda _alpha, fn: apply(fn, [0]),
    "dbgSleep": _dbg_sleep,
    "timeit": _timeit,
    "allocprof": lambda _alpha, _msg, fn, _w: apply(fn, [0]),
    "isExclusiveUnsafe": _is_exclusive_unsafe,
    "isScalarObj": _is_scalar_obj,
    "ptrAddrUnsafe": lambda _alpha, a: _address(a),
    "sorryAx": _sorry_ax,
}
