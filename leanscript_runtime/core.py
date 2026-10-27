"""Objects, closures, and other core runtime support for generated programs.

Heap objects carry a reference count in their `rc` field, with the same meaning as `m_rc` in the
Lean C runtime:

- `rc > 0`: the number of references. An object with `rc == 1` is exclusive and may be updated in
  place.
- `rc == 0`: persistent. Never freed and never exclusive.
- `rc == FREED`: freed. Touching it again is a reference counting bug, so we raise.

Objects without an `rc` field, such as scalars and foreign values, are treated as persistent.
Python's garbage collector reclaims the memory itself; the counts exist so that generated code knows
when an object is exclusive.
"""

from __future__ import annotations

import os
import sys

FREED = -1


def _children(x: object) -> object:
    """The reference counted children of `x`, or `None` if it has none."""
    children = getattr(x, "_children", None)
    return children() if children is not None else None


def _describe(x: object) -> str:
    describe = getattr(x, "_describe", None)
    if describe is not None:
        return describe()
    return type(x).__name__


def _use_after_free(op: str, x: object) -> Exception:
    return RuntimeError(f"LeanScript: {op} of freed object {_describe(x)}")


def _check_counted(x: object) -> None:
    if getattr(x, "rc", None) is None:
        raise RuntimeError(f"LeanScript: object without a reference count: {_describe(x)}")


def inc(x: object) -> None:
    rc = getattr(x, "rc", None)
    if rc is None:
        return
    if rc > 0:
        x.rc = rc + 1
    elif rc == FREED:
        raise _use_after_free("inc", x)


def inc_n(x: object, n: int) -> None:
    rc = getattr(x, "rc", None)
    if rc is None:
        return
    if rc > 0:
        x.rc = rc + n
    elif rc == FREED:
        raise _use_after_free("inc", x)


def dec(x: object) -> None:
    rc = getattr(x, "rc", None)
    if rc is None:
        return
    if rc > 1:
        x.rc = rc - 1
    elif rc == 1:
        # The children's counts are left alone: over-counting only makes generated code copy where
        # Lean would reuse, which is always safe.
        x.rc = FREED
    elif rc == FREED:
        raise _use_after_free("dec", x)


def del_(x: object) -> None:
    """Frees `x` without decrementing its children, whose references have moved elsewhere."""
    if getattr(x, "rc", None) is not None:
        x.rc = FREED


def reset(x: object, n: int) -> object:
    """If `x` is exclusive, releases its first `n` fields and returns it for reuse; otherwise gives
    up our reference to `x` and returns `0`."""
    if x.rc == 1:
        for i in range(n):
            dec(x.f[i])
        return x
    dec(x)
    return 0


def is_shared(x: object) -> int:
    return 0 if getattr(x, "rc", None) == 1 else 1


def tag(x: object) -> int:
    return x if isinstance(x, int) else x.tag


def unreachable() -> None:
    raise RuntimeError("LeanScript: unreachable code reached")


def panic(default_value: object, msg: object) -> object:
    """Reports the panic message `msg` and returns `default_value`, as `lean_panic_fn` does."""
    write_stderr(f"{msg}\n")
    return default_value


def mark_persistent(x: object) -> object:
    todo = [x]
    while todo:
        o = todo.pop()
        rc = getattr(o, "rc", None)
        if rc is None or not rc > 0:
            continue
        o.rc = 0
        children = _children(o)
        if children is not None:
            todo.extend(children)
    return x


def lazy(init) -> object:
    """Returns a function that computes `init()` on first call and caches the persistent value."""
    state = 0
    value = None

    def get():
        nonlocal state, value
        if state == 2:
            return value
        if state == 1:
            raise RuntimeError("LeanScript: cyclic constant initialization")
        state = 1
        value = mark_persistent(init())
        state = 2
        return value

    return get


def init_cell() -> object:
    """Returns a function that reads an `[init]` declaration, which must first be set with `set`."""
    initialized = False
    value = None

    def get():
        if not initialized:
            raise RuntimeError("LeanScript: `[init]` declaration read before initialization")
        return value

    def set_(v):
        nonlocal initialized, value
        value = mark_persistent(v)
        initialized = True

    get.set = set_
    return get


class Ctor:
    """A Lean constructor object, or a scalar boxed as one."""

    __slots__ = ("rc", "tag", "f", "s")

    def __init__(self, tag: int, f: list, s: dict | None):
        self.rc = 1
        self.tag = tag
        self.f = f
        self.s = s

    def _children(self):
        return self.f

    def _describe(self):
        return f"constructor {self.tag} with {len(self.f)} fields"


class Closure:
    """A partially applied function."""

    __slots__ = ("rc", "fn", "arity", "args")

    def __init__(self, fn, arity: int, args: list):
        self.rc = 1
        self.fn = fn
        self.arity = arity
        self.args = args

    def _children(self):
        return self.args

    def _describe(self):
        name = getattr(self.fn, "__name__", "closure")
        return f"closure of {name} with {len(self.args)}/{self.arity} arguments"


class Ref:
    """A mutable reference cell, `ST.Ref`, which owns its value."""

    __slots__ = ("rc", "value")

    def __init__(self, value):
        self.rc = 1
        self.value = value

    def _children(self):
        return (self.value,)

    def _describe(self):
        return "ref"


class Thunk:
    """A lazily computed value, `Thunk`."""

    __slots__ = ("rc", "fn", "value")

    def __init__(self, fn, value=None):
        self.rc = 1
        self.fn = fn
        self.value = value

    def _children(self):
        return (self.fn if self.fn is not None else self.value,)

    def _describe(self):
        return "evaluated thunk" if self.fn is None else "unevaluated thunk"


def pap(fn, arity: int, args: list) -> Closure:
    """Partially applies `fn`, which takes `arity` owned arguments, to the owned arguments `args`."""
    return Closure(fn, arity, args)


def _take_args(f: Closure) -> list:
    """Takes ownership of `f` and returns its fixed arguments, each of which the caller then owns."""
    args = f.args
    if f.rc == 1:
        del_(f)
        return args
    for arg in args:
        inc(arg)
    dec(f)
    return args


def apply(f: Closure, args: list) -> object:
    """Applies the closure `f` to `args`, which may be fewer or more than it still expects.

    Like `lean_apply_n`, this consumes `f` and every argument.
    """
    remaining = f.arity - len(f.args)
    if len(args) < remaining:
        return Closure(f.fn, f.arity, _take_args(f) + list(args))
    if len(args) == remaining:
        return f.fn(*_take_args(f), *args)
    result = f.fn(*_take_args(f), *args[:remaining])
    return apply(result, args[remaining:])


def array_to_list(xs) -> object:
    """Converts a Python iterable to a Lean `List`, moving the elements into it."""
    result = 0
    for x in reversed(list(xs)):
        result = Ctor(1, [x, result], None)
    return result


def list_to_array(list_: object) -> list:
    """Returns the elements of the Lean `List` as a list, without affecting any reference counts."""
    xs = []
    while list_ != 0:
        xs.append(list_.f[0])
        list_ = list_.f[1]
    return xs


def write_stdout(text: str) -> None:
    os.write(1, text.encode("utf-8"))


def write_stderr(text: str) -> None:
    os.write(2, text.encode("utf-8"))


def flush_output() -> None:
    """Writes are unbuffered, so there is nothing to flush."""


def run_main(inits: list, main, arity: int, error_to_string) -> None:
    """Runs the initializers, then `main`, and exits with the resulting status."""
    status = 0
    try:
        if _run_inits(inits, error_to_string):
            if arity == 2:
                r = main(array_to_list([mk_string(a) for a in sys.argv[1:]]), 0)
            else:
                r = main(0)
            if r.tag == 0:
                value = r.f[0]
                status = value if isinstance(value, int) else 0
            else:
                status = _report_error(r, error_to_string)
    finally:
        flush_output()
    raise SystemExit(status)


def _run_inits(inits: list, error_to_string) -> bool:
    for init, cell in inits:
        r = init(0)
        if r.tag != 0:
            _report_error(r, error_to_string)
            return False
        if cell is not None:
            cell.set(r.f[0])
        else:
            dec(r)
    return True


def _report_error(r: object, error_to_string) -> int:
    error = r.f[0]
    del_(r)
    msg = error_to_string(error)
    write_stderr(f"uncaught exception: {msg}\n")
    dec(msg)
    return 1


def track(x: object) -> object:
    """Registers a newly allocated object for leak checking, and returns it."""
    return x


def init_scalars(x: object) -> None:
    """Gives `x` an empty scalar field table if it does not have one yet."""
    if x.s is None:
        x.s = {}


class Jmp(Exception):
    """A jump to a join point whose labeled block is not the innermost loop."""

    __slots__ = ("j",)

    def __init__(self, j: int):
        self.j = j


class Tail(Exception):
    """A self tail call, which restarts the emitting function."""


def mk_string(s: str):
    """Constructs a Lean string from a Python string."""
    from .string import mk_string as make

    return make(s)


def resolve_externs(names: list, unavailable: list = ()) -> dict:
    """Returns the implementations of the externs named `names`.

    An extern in `unavailable` that the runtime does not implement is replaced by a function that
    raises when called. Any other missing extern is an error, so that a program fails when it loads
    instead of partway through running.
    """
    from . import externs as implementations

    unavailable = set(unavailable)
    missing = [
        name for name in names if name not in implementations and name not in unavailable
    ]
    if missing:
        raise RuntimeError(
            "LeanScript: missing implementations for externs:\n  " + "\n  ".join(missing)
        )
    resolved = dict(implementations)
    for name in unavailable:
        if name not in implementations:
            resolved[name] = _unavailable_extern(name)
    return resolved


def _unavailable_extern(name: str):
    def stub(*_args):
        raise RuntimeError(f"LeanScript: {name} is not available on this platform")

    return stub
