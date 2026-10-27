# LPython 0.22.0 subset notes

This document records what the LPython compiler accepts, so the emitter and runtime plan can be
evaluated against the real target. It is a probe report, not a complete language specification.

## Version

- Compiler: LPython 0.22.0.
- Source: conda-forge, `linux-64`.
- Release date: 2024-07-08. This is the newest release on conda-forge and GitHub; there is no newer
  release to pin.

## Summary

LPython 0.22.0 compiles a small, statically typed subset of Python. It cannot compile the current
`leanscript_runtime` contract:

- Classes with non-default constructors, inheritance, `__slots__`, or methods are rejected.
- `bytearray`, `bytes`, and their codecs are unavailable.
- `try`/`except`, `lambda`, `@property`, and f-strings are rejected.
- Bare `int` is unsupported; every binding needs an explicit numeric or container annotation.
- `sys.stderr.write` is rejected, and `sys.exit` prints `STOP <n>` on stdout before exiting.

The main blocker is the type model, not syntax. Lean IR values are dynamically typed: a
constructor's fields can mix strings, integers, floats, closures, and other constructors. LPython
has no `Any`, union, or object type, and no method dispatch on a tag. A faithful port of the
JavaScript runtime is therefore impossible.

## Probe results

| Feature | Result |
| --- | --- |
| `class` with `__init__(self, tag, f, s)` | Semantic error: "Only default constructors implemented". |
| Class inheritance | "Inheritance in classes isn't supported yet". |
| `__slots__` in a class | "AnnAssign expected inside struct". |
| Methods, with `self` or `self: Ctor` | Rejected. |
| `bytearray` | "The type 'bytearray' is undeclared". |
| `bytes` and `b"..."` literals | Undeclared. |
| `str.encode` and `bytes.decode` | Unavailable. |
| `try`/`except` | Internal compiler error: "visit_Try() not implemented". |
| `lambda` | Rejected. |
| `@property` | Rejected. |
| F-strings | Internal compiler error. |
| `for c in s` over a `str` | Rejected. |
| `sys.stderr.write` | "Only Name type and constant integers supported in Call". |
| Bare `int` | "int type is not supported yet". |
| Implicit binding, `x = 1` | "Variable 'x' not declared"; annotate `i32`, `i64`, `f64`, `str`, `list[T]`, or `dict[K,V]`. |
| `sys.exit(2)` | Prints `STOP 2` on stdout before exiting with status 2. |
| Annotated functions, recursion, `while`, `print` | Work. |
| `list[T]` | Works with an explicit element type. |
| `dict[str, T]` | Works with explicit key and value types. |
| Classes with annotated fields and a default constructor | Work, but no methods. |
| `str` operations: `len`, indexing, `+`, `==`, `find`, `startswith`, `upper` | Work. |
| `assert cond, msg` | Prints `msg` and exits with status 1. |
| `sys.argv` | Works. |
| Imports via `-I` | Work. |

## Consequences for the plan

A faithful port of the JavaScript runtime cannot run on LPython 0.22.0. If LPython is a hard
requirement, the runtime and emitter need a redesign:

- **Value encoding.** Represent a constructor as a tagged list or record with an integer tag, and
  dispatch with `if` chains. There is no `Any`, union, or object type.
- **Strings.** Represent strings as a typed UTF-8 buffer, such as `list[i32]`, with manual encode
  and decode helpers. `bytes`, `bytearray`, and the usual codecs are unavailable.
- **Types.** Annotate every function, parameter, return, and local. The emitter must derive the
  annotations from the IR types.
- **Control flow.** Do not use `try`/`except`, `match`, `lambda`, f-strings, or properties. Lower
  join points with flags or loops.
- **Errors.** Use `assert` or an explicit return-code path. Do not use `sys.exit` for normal
  program exits, because it writes `STOP <n>` to stdout and breaks output comparison.
- **IO.** Writable `os` and file APIs and `sys.stderr.write` are unavailable. The runtime needs a
  different IO and error-reporting design.
- **Imports.** Use LPython's `-I` module path, not CPython's `PYTHONPATH`.
- **Reference counting.** LPython's memory model does not expose the JavaScript runtime's
  reference-count protocol. `isShared` and `reuse` need a conservative or redesigned lowering.

If LPython is not a hard requirement, CPython 3 source is viable today: the runtime modules
already match the JavaScript reference on the sampled string and container operations, and the
test harness can run generated `.py` directly under CPython.

## Open questions

- Is there a stdout-safe way to exit with a status under LPython?
- Does LPython's `dict[K, V]` cover the runtime's dictionary use, or are there key-type limits?
- Can the runtime be split into LPython-compilable typed modules plus a CPython-only host layer, or
  does that violate the single-target requirement?
- Does LPython support the class-field and constructor pattern needed by `Ctor`, or must every
  value become a tagged list?
