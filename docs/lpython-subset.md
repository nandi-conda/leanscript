# LPython 0.22.0 subset notes

This document records what the LPython compiler accepts, so the emitter and runtime plan can be
evaluated against the stated target. It is a probe report, not a complete language specification.

## Version and provenance

- Compiler: LPython 0.22.0.
- Source: conda-forge, `linux-64`.
- Release date: 2024-07-08. This is the newest release on conda-forge and GitHub; there is no newer
  release to pin.
- Compilation model: `lpython` compiles ahead of time to a native executable; `-o` names the
  executable.

## Target status

LPython 0.22.0 is the target. The current `leanscript_runtime` contract and the current IR lowering
cannot compile under it. The runtime and emitter must be redesigned as described below. CPython 3
source is an explicitly flagged fallback that requires user approval; it is not a silent
substitute.

## Summary

LPython 0.22.0 compiles a small, statically typed subset of Python. It rejects the current runtime
contract:

- Classes with non-default constructors, inheritance, `__slots__`, or methods are rejected.
- `bytearray` and `bytes` are unavailable, as are `str.encode` and `bytes.decode`.
- `try`/`except` and f-strings are compiler crashes, not clean diagnostics.
- `lambda` and `@property` are rejected.
- Bare `int` is unsupported; every binding needs an explicit annotation.
- `sys.stderr.write` is rejected.
- `sys.exit(n)` writes `STOP n` to stderr and exits with `n`; earlier stdout is preserved.

The main blocker is the type model, not syntax. Lean IR values are dynamically typed: a
constructor's fields can mix strings, integers, floats, closures, and other constructors. LPython
has no `Any`, union, or object type, and no method dispatch on a tag. A faithful port of the
JavaScript runtime is impossible.

## Probe results

### Rejected or constrained

| Feature | Result |
| --- | --- |
| `class` with `__init__(self, tag, f, s)` | Semantic error: "Only default constructors implemented". |
| Class inheritance | Semantic error: "Inheritance in classes isn't supported yet". |
| `__slots__` in a class | Semantic error: "AnnAssign expected inside struct". |
| Method `def get(self) -> i32` | Semantic error: "Argument does not have a type". |
| Method `def get(self: Ctor) -> i32` inside the class body | Semantic error: "The type 'Ctor' is undeclared"; there is no forward reference. |
| Method annotation `self: "Ctor"` | Semantic error: "Only Name, Subscript, and Call supported… in annotation". Class methods are unusable. |
| `bytearray` | Semantic error: "The type 'bytearray' is undeclared". |
| `bytes` and `b"..."` literals | Semantic error: undeclared. `str.encode` and `bytes.decode` are unavailable. |
| `try`/`except` | **Internal compiler error**: "Unhandled exception… visit_Try() not implemented". Not a clean diagnostic. |
| F-strings | **Internal compiler error** with a raw traceback. |
| `lambda` | Semantic error: rejected. |
| `@property` | Semantic error: rejected. |
| `sys.stderr.write` | Semantic error: "Only Name type and constant integers supported in Call". |
| Bare `int` | Semantic error: "int type is not supported yet". |
| Unannotated binding, `x = 1` | Semantic error: "Variable 'x' not declared". Every binding needs an explicit type. |
| `xs: list[i32] = [1, "a"]` | Semantic error: "All List elements must be of the same type for now". |
| `x: i32 \| str = 1` | Semantic error: "Only Name, Subscript, and Call supported for now in annotation of annotated assignment". |
| `from typing import Any` | Semantic error: "Could not find the module 'typing'". |
| `for c in s` over a `str` with undeclared `c` | Semantic error: "Variable 'c' not declared". This is the unannotated-binding rule, not a string-iteration limit. |
| Attribute access on a call result, `make(4).tag` | Semantic error: "Only Name, Attribute is supported for now in Attribute". |

### Working

| Feature | Result |
| --- | --- |
| Annotated functions and recursion | Work. |
| `while`, `print` | Work. |
| `list[T]` with an explicit element type | Works. |
| `dict[str, T]` with explicit key and value types | Works. |
| Annotated-field classes with a default constructor and post-construction assignment, `c: Ctor = Ctor(); c.tag = 2` | Works, including `list[i32]` fields. |
| `for c in s` over a `str` with `c: str = ""` declared first | Works. |
| `str` operations: `len`, indexing, `+`, `==`, `find`, `startswith`, `upper` | Work. |
| `assert cond, msg` | Prints `AssertionError: msg` to stderr and exits 1. Usable abort path. |
| `sys.argv` | Works. |
| Imports via `-I` | Work. |
| `sys.exit(n)` | Prints `STOP n` to stderr, preserves earlier stdout, and exits with status `n`. Exit codes are usable; the `STOP n` line is the only noise. |

## Type-model evidence

These probes are the strongest evidence for the blocker:

- `xs: list[i32] = [1, "a"]` is rejected: "All List elements must be of the same type for now".
  There are no heterogeneous containers.
- `x: i32 | str = 1` is rejected: "Only Name, Subscript, and Call supported for now in annotation
  of annotated assignment". There are no union types.
- `from typing import Any` fails: "Could not find the module 'typing'". There is no `Any`.
- There is no `bytearray` type: "The type 'bytearray' is undeclared".
- Classes have no methods and no forward reference to their own type.

Together these mean there is no common object type and no runtime tag dispatch. A faithful port of
`src/runtime/*.js` cannot be compiled by LPython.

## Required IR and runtime shape changes

Every row is a place where the current IR/lowering or runtime shape must change to fit LPython
0.22.

| Area | Current shape | LPython 0.22 constraint | Required change |
| --- | --- | --- | --- |
| Value representation | `Ctor(tag, fields, scalars)` class with methods | Classes allow annotated fields and a default constructor only; no methods | Encode a value as a tagged cell with typed payload fields; use free functions and `if` chains for tag dispatch |
| Heterogeneous fields | `Ctor.f` mixes strings, ints, floats, closures, and other Ctors | `list[T]` is homogeneous; no `Any`, union, or object type | Split payloads by type or use a tagged union with typed slots; the emitter must emit a layout per constructor shape |
| Scalar fields | `Ctor.s` dict mixes integer and float fields | `dict[str, T]` has one value type | Use typed scalar slots, separate int and float dictionaries, or per-shape records |
| Strings | `LeanString(rc, data: str, _encoded: bytes)` | No `bytes`, `bytearray`, `str.encode`, or `bytes.decode` | Use a typed UTF-8 buffer such as `list[i32]` with manual encode and decode helpers |
| Byte arrays | `ByteArray` over `bytearray` | `bytearray` and `bytes` are undeclared | Use a typed integer buffer with manual byte operations |
| Closures | `Closure(fn, arity, args)`, `pap`, `apply`, lambdas | No `lambda`; classes have no methods; no common callable type | Encode closures as tagged records with a function id and captured arguments; dispatch `apply` with `if` chains or monomorphize |
| Higher-order calls | `fap`, `pap`, `ap` over dynamic function values | No `Any` or common function type | Give the emitter a typed closure representation and a finite dispatch; some call shapes may need specialization |
| Exceptions | `try`/`except` in the runtime and error paths | `try`/`except` is an internal compiler error | Use `assert`-based aborts or explicit return codes; redesign `unreachable`, absent externs, and panic paths |
| Join points | `jmp` and labeled blocks | No labeled `break`; exceptions are unavailable | Lower join points with flags, state machines, or typed loop variables |
| `case` | `case` over a tag | No `match`; use `if`/`elif` on an integer tag | Emit `if`/`elif` chains |
| Self tail calls | `while True` loop with parameter reassignment | `while` works, but every variable needs a type | Declare typed parameters and loop variables before the loop |
| Reference counting | `rc` attribute, `inc`/`dec`/`del`/`reset`/`isShared`/`reuse`, `_children()` | No methods; memory model is LPython's; no `sys.getrefcount` | Make `inc`/`dec`/`del` no-ops, make `isShared` conservatively true, and let `reuse` allocate; remove `_children` and finalizers |
| Runtime objects | `Ctor`, `Closure`, `Ref`, `Thunk`, `Handle`, `LeanArray`, `LeanString` classes with methods | Only annotated fields, a default constructor, and post-construction assignment | Use annotated-field structs plus free functions; assign fields after construction; avoid inheritance, `__slots__`, and methods |
| IO | `sys.stderr.write`, writable `os` and file APIs | `sys.stderr.write` is rejected; writable `os`/file APIs are unavailable in the probe | Redesign IO around LPython-supported calls, or add a host layer; flag CLI, file system, and process fixtures as blocked until this is solved |
| Exit codes | `sys.exit(n)` | Writes `STOP n` to stderr before exiting `n`; earlier stdout is preserved | Keep exit codes; the harness must tolerate the `STOP n` stderr line |
| Diagnostics | `error:`/`warning:` and runtime messages | `assert cond, msg` prints `AssertionError: msg` to stderr and exits 1 | Map errors to `assert` or return codes; accept that messages and exit codes may differ from the JavaScript runtime |
| Integers | Python arbitrary-precision `int` | `i8`, `i16`, `i32`, `i64`, `u64`, `f64`; bare `int` is unsupported | Map IR types to LPython types; define a representation for large `Nat` and `Int`; mask fixed-width operations |
| Annotations | Inferred Python bindings | Every binding needs an explicit annotation | Annotate functions, parameters, returns, and locals from the IR types |
| Heterogeneous lists | Lists of mixed values | `list[T]` requires one element type | Split by type or use tagged cells; the emitter must choose a typed layout |
| `typing` | `from typing import Any` | The `typing` module is missing | Avoid `Any`, unions, and `typing` imports |
| String formatting | f-strings | F-strings are an internal compiler error | Use concatenation and `str()` |
| Properties | `@property` | Rejected | Use free functions |
| Attribute access | `make(4).tag` | Attribute access on a call result is rejected | Assign to a typed variable first |
| Loop variables | `for c in s` | The loop variable must be declared with a type first | Declare loop variables before the loop |
| Imports | `PYTHONPATH` | Imports use the `-I` module path | Pass the runtime package root with `-I` |
| Compilation | Run `.py` with the interpreter | `lpython` compiles ahead of time to a native executable | The test harness must compile and run the executable, not run `python file.py` |
| Extern table | `externs: dict[str, callable]` with heterogeneous signatures | No `Any`, no common callable type, homogeneous `dict[str, T]` | Resolve externs at emission time and emit direct calls or a finite `if` chain; do not rely on a runtime dict of callables |
| Runtime entry | `run_main(inits, main, arity, error_to_string)` with callables | No common callable type | Emit a typed dispatch or direct calls for `main` and the init functions |
| Test harness | Runs generated `.py` under an interpreter | AOT compilation; `STOP n` on stderr for `sys.exit` | Compile with `lpython`, run the executable, capture stdout/stderr/exit, and tolerate `STOP n` |

## How probed

```sh
# Compiler version and provenance
curl -s 'https://api.github.com/repos/lcompilers/lpython/releases?per_page=1'
#   -> v0.22.0, published 2024-07-08 (newest release)
mkdir /tmp/lpenv && cd /tmp/lpenv
printf '[workspace]\nname = "lpenv"\nchannels = ["conda-forge"]\nplatforms = ["linux-64"]\n' > pixi.toml
pixi add lpython
pixi run lpython --version
#   -> LPython version: 0.22.0 / Platform: Linux / Default target: x86_64-unknown-linux-gnu

# Each probe is a standalone file whose last statement calls main().
lpython probe.py -o probe.out && ./probe.out; echo "exit $?"
```

Diagnostic behavior:

- A rejected program prints `semantic error:` plus a source span on stderr and exits 2.
- A compiler crash prints a traceback on stderr and exits 2.
- A runtime `assert` failure prints to stderr and exits 1.
- `sys.exit(n)` prints `STOP n` to stderr and exits `n`.

Probes covered `__init__`, inheritance, `__slots__`, methods, `bytearray`, `bytes`,
`str.encode`/`bytes.decode`, `try`/`except`, lambdas, `@property`, f-strings, `for` over `str`,
`sys.stderr.write`, bare `int`, annotations (`i8`, `i16`, `i32`, `i64`, `u64`, `f64`, `str`,
`list[T]`, `dict[K, V]`, `set`), classes as fields and arguments, `dict` of strings, nested lists,
module imports with `-I`, `assert`, `sys.argv`, `sys.exit`, and the type-model probes above.

## CPython fallback

CPython 3 source is viable today: the three CPython runtime modules already match the JavaScript
reference on the sampled string and container operations, and generated `.py` can run directly
under CPython. It is a fallback only. Switching to it requires explicit user approval and a docs
change; it is not a silent substitution.

## Open questions

- Is there a quieter exit path than `sys.exit`, or should the harness ignore the `STOP n` stderr
  line?
- Does LPython's `dict[K, V]` cover the runtime's dictionary use, or are there key-type limits?
- Can the runtime be split into LPython-compilable typed modules plus a CPython-only host layer, or
  does that violate the single-target requirement?
- Does LPython support the class-field and post-construction assignment pattern needed for `Ctor`,
  or must every value become a tagged list?
- Are writable `os` and file APIs completely unavailable, or is there an LPython-supported path for
  the CLI, file system, and process fixtures?
