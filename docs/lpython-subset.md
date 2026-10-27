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

LPython 0.22.0 compiles a small, statically typed subset of Python. The current runtime contract is
blocked by several independent constraints:

- **No object model.** Classes are not usable as heap objects. Returning an instance, `list[P]`,
  class-typed fields, and mutation through a parameter are rejected or crash the compiler.
- **No dynamic value type.** Lean IR values mix strings, integers, floats, closures, and other
  constructors. LPython has no `Any`, union, or common object type, and no heterogeneous lists.
- **No arbitrary-precision integers.** LPython has `i8` through `i64`; Lean `Nat` is unbounded.
  Fixtures print `30!`, `2^100`, `10^20`, and `fib(200)`, so a bignum layer is required.
- **No writable IO or stdin.** LPython's `os` module is read-only and it has no stdin. The `Cli`
  fixture needs stdin, file write and append, and directory operations.
- **No usable exceptions.** `try`/`except` is an internal compiler error. Uncaught `raise` prints
  `ERROR STOP` with no message. `assert cond, msg` keeps the message and exits 1.
- **Byte strings, not text.** LPython `str` is a UTF-8 byte string. This is useful for Lean, but
  item assignment is unavailable and string slicing inside functions is unreliable.
- **Syntax gaps.** No f-strings, list comprehensions, generator expressions, `lambda`,
  `@property`, or `from __future__ import annotations`.
- **No bare `int`.** Every binding needs an explicit annotation, and every loop variable must be
  declared before the loop.

Together these mean no fixture subset that uses IO, `Nat`, or strings can pass unchanged. The type
model, object model, bignum gap, and IO gap are independent blockers.

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
| Return a class instance from a function | **Compiler segfault**. Classes are not heap objects. |
| `list[P]` where `P` is a class | **Compiler segfault**. |
| Class-typed field in another class | "'node' must be initialized with an instance of struct Node". |
| Mutate a field through a function parameter | "Assignment to an input function parameter 'p' is not allowed". |
| `bytearray` | Semantic error: "The type 'bytearray' is undeclared". |
| `bytes` and `b"..."` literals | Semantic error: undeclared. `str.encode` and `bytes.decode` are unavailable. |
| `s[0] = "z"` | Runtime error: `'str' object does not support item assignment`. |
| `try`/`except` | **Internal compiler error**: "Unhandled exception… visit_Try() not implemented". |
| F-strings | **Internal compiler error** with a raw traceback. |
| List comprehensions, `[x * 2 for x in xs]` | **Internal compiler error**. |
| Generator expressions | **Internal compiler error**. |
| `lambda` | Semantic error: rejected. |
| `@property` | Semantic error: rejected. |
| `from __future__ import annotations` | Semantic error: "Could not find the module '__future__'". |
| `sys.stderr.write` | Semantic error: "Only Name type and constant integers supported in Call". |
| Bare `int` | Semantic error: "int type is not supported yet". |
| Unannotated binding, `x = 1` | Semantic error: "Variable 'x' not declared". Every binding needs an explicit type. |
| `xs: list[i32] = [1, "a"]` | Semantic error: "All List elements must be of the same type for now". |
| `x: i32 \| str = 1` | Semantic error: "Only Name, Subscript, and Call supported for now in annotation of annotated assignment". |
| `from typing import Any` | Semantic error: "Could not find the module 'typing'". |
| `for c in s` over a `str` with undeclared `c` | Semantic error: "Variable 'c' not declared". The loop variable must be declared and typed first. |
| `for i in range(4)` or `for k in d` with undeclared variable | Semantic error: the loop variable must be declared and typed first. |
| Attribute access on a call result, `make(4).tag` | Semantic error: "Only Name, Attribute is supported for now in Attribute". |
| `def f(s: str, b: i32, e: i32) -> i32: return len(s[b:e])` | Compiles and runs but prints nothing. |
| `s[0:i]` printed from a function | Prints nothing. |
| `s[0:i] + "X" + s[i:]` or `s[i:]` inside a function | **Compiler segfault**. |
| `raise ValueError("boom")` uncaught | Prints `ERROR STOP` with no message and exits 1. Not a usable diagnostic path. |
| `u64` decimal literal above `i64` maximum | "Cannot cast negative value to unsigned integer". |
| `u64(9223372036854775807)` | Printed `4611709631586744390`; decimal construction is unreliable. |
| `/` on integers | Returns `f64`; use `//` for integer division. |

### Working

| Feature | Result |
| --- | --- |
| Annotated functions and recursion | Work. |
| `while`, `print` | Work. |
| `list[T]` with an explicit element type | Works. |
| `dict[str, T]` with explicit key and value types | Works. |
| Default arguments | Work. |
| Module-level `dict[str, str]` and `dict[str, int]` | Work; plain data can be module-level. |
| Annotated-field classes with a default constructor and local post-construction assignment, `c: Ctor = Ctor(); c.tag = 2` | Work locally, including `list[i32]` fields. Instances can be passed to a function for reading, but cannot be returned, stored in a list, or used as a field. Not a heap-object replacement for `Ctor`. |
| `for c in s` over a `str` with `c: str = ""` declared first | Works; iteration is byte by byte, not scalar by scalar. |
| `for i in range(n)` with `i: i32 = 0` declared first | Works. |
| `str` operations: `len`, indexing, `+`, `==`, `find`, `startswith`, `upper` | Work with UTF-8 byte semantics. |
| `len("é") == 2`, `len("日") == 3` | Confirmed; `str` is a UTF-8 byte string. |
| `s[i]` | Returns a one-byte `str`; `"é"[0] + "é"[1] == "é"`. |
| `print("é")` | Writes the bytes `c3 a9` unchanged. |
| `ord(s[i])` | Returns the signed byte value; `ord("é"[0]) == -61`, so use `ord(...) & 255`. |
| Byte-loop substring copy: `r: str = ""; while k < e: r += s[k]; k += 1` | Works and returns the right bytes. |
| `assert cond, msg` | Prints `AssertionError: msg` to stderr and exits 1. Usable abort path. |
| `sys.argv` | Works. |
| Imports via `-I` | Work. |
| `sys.exit(n)` | Prints `STOP n` to stderr, preserves earlier stdout, and exits with status `n`. |
| `(u64(1) << u64(63)) - u64(1)` | Exact; build 64-bit constants from shifts. |
| `big + big` | Wraps modulo `2^64`; `3 * (2^63 - 1)` is correct modulo `2^64`. |

## Diagnostic kinds

- Semantic error: prints `semantic error:` and a source span on stderr, exits 2.
- Internal compiler error: prints a traceback on stderr, exits 2.
- Compiler segfault: exits 139.
- Runtime `assert` failure: prints to stderr, exits 1.
- Uncaught `raise`: prints `ERROR STOP` with no message, exits 1.
- `sys.exit(n)`: prints `STOP n` to stderr, exits `n`.

## Type-model evidence

These probes are the strongest evidence for the type blocker:

- `xs: list[i32] = [1, "a"]` is rejected: "All List elements must be of the same type for now".
- `x: i32 | str = 1` is rejected: no union types.
- `from typing import Any` fails: no `Any`.
- There is no `bytearray` type.
- Classes cannot be returned, stored in lists, or used as fields, so there is no object type.
- Lean IR values mix strings, ints, floats, closures, and Ctors; LPython has no common type for
  them and no heterogeneous containers.

## Object-model evidence

The class probes are stronger than "no `__init__`":

- Returning a class instance from a function segfaults the compiler.
- `list[P]` of class instances segfaults.
- A class-typed field in another class is rejected.
- Mutating a field through a function parameter is not allowed.
- Local field assignment after construction works, and an instance can be passed to a function for
  reading.

There is no object model. The runtime cannot represent constructors, closures, refs, or thunks as
objects. It needs tagged lists or records with typed payloads, and free functions for operations.

## String semantics

LPython `str` is a UTF-8 byte string, not text:

- `len` is the byte length; `len("é") == 2` and `len("日") == 3`.
- Indexing returns a one-byte `str`; concatenation and equality use byte semantics.
- `print` writes the bytes unchanged.
- `ord` returns the signed byte value; mask with `& 255`.
- There is no item assignment.
- Slicing inside functions is unreliable or crashes the compiler; build substrings with byte loops.

This is good news for Lean: `String.Pos` is already a byte offset. The runtime can keep strings as
`str`, needs no codec, and `utf8ByteSize` is `len`.

## Numeric limits

LPython has `i8`, `i16`, `i32`, `i64`, `u64`, and `f64`; it has no arbitrary-precision integers.
Lean `Nat` is unbounded. Fixtures print `30!`, `2^100`, `10^20`, and `fib(200)`, so the runtime
needs a bignum layer, for example a `list[i64]` limb representation with its own arithmetic.
`Loops`, `NumberCrunching`, `Caching`, `Builtins`, and `ExprParser` cannot pass until it exists.

`u64` has extra traps:

- Decimal literals above `i64` maximum are rejected.
- `u64(9223372036854775807)` printed an incorrect value.
- Constants built from shifts are exact.
- Addition wraps modulo `2^64`.
- `/` returns `f64`; use `//` for integer division.

## IO and stdin

LPython's `os` module is read-only and it has no stdin. The `Cli` fixture needs stdin, file write
and append, directory operations, current-directory changes, environment access, and sleep. None of
that is available as tested. `sys.stderr.write` is also rejected. `Cli` is unimplementable on
LPython 0.22 without a host layer; it is not merely unsupported so far. Other IO, file system, and
process fixtures are blocked for the same reason.

## Required IR and runtime shape changes

Every row is a place where the current IR/lowering or runtime shape must change to fit LPython
0.22.

| Area | Current shape | LPython 0.22 constraint | Required change |
| --- | --- | --- | --- |
| Value representation | `Ctor(tag, fields, scalars)` class with methods | No object model; classes are not heap objects | Encode a value as a tagged list or record with typed payload fields; use free functions and `if` chains |
| Heterogeneous fields | `Ctor.f` mixes objects and scalars | `list[T]` is homogeneous; no `Any`, union, or object type | Split payloads by type or use a tagged union with typed slots |
| Scalar fields | `Ctor.s` dict mixes integer and float fields | `dict[str, T]` has one value type | Use typed scalar slots, separate int and float dictionaries, or per-shape records |
| Strings | `LeanString(rc, data: str, _encoded: bytes)` | `str` is a UTF-8 byte string; no `bytes`, `bytearray`, encode, or decode; no item assignment; slicing is unreliable | Keep strings as `str`; use byte length and indexing, `ord(...) & 255`, and loop-built substrings; no codec |
| Byte arrays | `ByteArray` over `bytearray` | `bytearray` and `bytes` are undeclared | Use a typed integer buffer with manual byte operations |
| Closures | `Closure(fn, arity, args)`, `pap`, `apply`, lambdas | No object model, no `lambda`, no common callable type | Encode closures as tagged lists or records with a function id and captured arguments; dispatch `apply` with `if` chains or specialize |
| Higher-order calls | `fap`, `pap`, `ap` over dynamic function values | No `Any` or common function type | Give the emitter a typed closure representation and finite dispatch |
| Exceptions | `try`/`except` and `raise` | `try`/`except` is an ICE; uncaught `raise` loses the message | Use `assert`-based aborts or explicit return codes; redesign `unreachable`, absent externs, and panic paths |
| Join points | `jmp` and labeled blocks | No labeled `break`; no exceptions | Lower join points with flags, state machines, or typed loop variables |
| `case` | `case` over a tag | No `match`; use `if`/`elif` on an integer tag | Emit `if`/`elif` chains |
| Self tail calls | `while True` loop with parameter reassignment | `while` works, but every variable needs a type | Declare typed parameters and loop variables before the loop |
| Reference counting | `rc`, `inc`/`dec`/`del`/`reset`/`isShared`/`reuse`, `_children()` | No object model, no methods, no `sys.getrefcount` | Make `inc`/`dec`/`del` no-ops, make `isShared` conservatively true, and let `reuse` allocate; remove `_children` and finalizers |
| Runtime objects | `Ctor`, `Closure`, `Ref`, `Thunk`, `Handle`, `LeanArray`, `LeanString` classes with methods | Classes are not heap objects and have no methods | Use tagged lists or records plus free functions; no instances returned, stored in lists, or used as fields |
| IO and stdin | `sys.stderr.write`, writable `os`, stdin | `os` is read-only; no stdin; `sys.stderr.write` rejected | Redesign IO or add a host layer; CLI, file system, and process fixtures are blocked |
| Bignums | Lean `Nat`/`Int` unbounded | Only `i8` through `i64`; no arbitrary precision | Add a bignum layer, such as `list[i64]` limbs, for `30!`, `2^100`, `10^20`, and `fib(200)` |
| `u64` | Decimal and division operations | Large decimal literals rejected; `u64(...)` unreliable; `/` returns `f64` | Build constants from shifts; use `//`; preserve modulo-`2^64` wraparound |
| Exit codes | `sys.exit(n)` | Writes `STOP n` to stderr before exiting `n` | Keep exit codes; the harness must tolerate the `STOP n` stderr line |
| Diagnostics | `error:`/`warning:` and runtime messages | `assert cond, msg` prints `AssertionError: msg` to stderr and exits 1; `raise` loses the message | Map errors to `assert` or return codes; accept that messages and exit codes may differ |
| Integers | Python arbitrary-precision `int` | `i8`, `i16`, `i32`, `i64`, `u64`, `f64`; bare `int` unsupported | Map IR types to LPython types; use the bignum layer for unbounded values; mask fixed-width operations |
| Annotations | Inferred Python bindings | Every binding and loop variable needs an explicit annotation; no `from __future__ import annotations` | Annotate functions, parameters, returns, locals, and loop variables from the IR types; avoid `__future__` |
| Heterogeneous lists | Lists of mixed values | `list[T]` requires one element type | Split by type or use tagged cells |
| `typing` | `from typing import Any` | The `typing` module is missing | Avoid `Any`, unions, and `typing` imports |
| Syntax | f-strings, comprehensions, generators, properties, lambdas | F-strings, comprehensions, and generators are ICEs; properties and lambdas are rejected | Use concatenation and `str()`, explicit loops, and free functions |
| Attribute access | `make(4).tag` | Attribute access on a call result is rejected | Assign to a typed variable first |
| Imports | `PYTHONPATH` | Imports use the `-I` module path | Pass the runtime package root with `-I` |
| Compilation | Run `.py` with the interpreter | `lpython` compiles ahead of time to a native executable | The harness compiles and runs the executable |
| Extern table | `externs: dict[str, callable]` with heterogeneous signatures | No `Any`; no common callable type; `dict[str, T]` is homogeneous | Resolve externs at emission time and emit direct calls or a finite `if` chain; plain module-level data dicts work |
| Runtime entry | `run_main(inits, main, arity, error_to_string)` with callables | No common callable type | Emit direct calls or a finite dispatch for `main` and init functions |
| Test harness | Runs generated `.py` under an interpreter | AOT compilation; `STOP n` on stderr for `sys.exit` | Compile with `lpython`, run the executable, capture stdout/stderr/exit, and tolerate `STOP n` |

## Portability evidence

- `scratch/lpython/gap.md` is a per-file audit of the three runtime modules, with each rejected
  construct and its replacement.
- `scratch/lpython/string_lp.py` is a working LPython 0.22 string module. Its output matches the
  CPython implementation on a 2081-value matrix (`scratch/lpython/string_matrix.expected`). It uses
  byte loops, `str` bytes, and no classes.
- This shows the string half of the runtime is portable. Arrays and byte arrays remain blocked on
  the value model.

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

Diagnostic behavior is summarized under "Diagnostic kinds". Probes covered `__init__`,
inheritance, `__slots__`, methods, returning class instances, `list[P]`, class fields, parameter
mutation, `bytearray`, `bytes`, `str.encode`/`bytes.decode`, `try`/`except`, lambdas, `@property`,
f-strings, comprehensions, generators, `from __future__ import annotations`, `for` over `str`,
`for i in range`, `for k in d`, `sys.stderr.write`, bare `int`, annotations (`i8`, `i16`, `i32`,
`i64`, `u64`, `f64`, `str`, `list[T]`, `dict[K, V]`, `set`), classes as fields and arguments, `dict`
of strings, nested lists, module imports with `-I`, `assert`, `raise`, `sys.argv`, `sys.exit`, UTF-8
length and indexing, `ord` byte values, slicing, `u64` literals and shifts, and the type-model
probes above.

## CPython fallback

CPython 3 source is viable today: the three CPython runtime modules already match the JavaScript
reference on the sampled string and container operations, and generated `.py` can run directly
under CPython. It is a fallback only. Switching to it requires explicit user approval and a docs
change; it is not a silent substitution.

## Open questions

- What bignum representation should the runtime use for unbounded `Nat`/`Int` under LPython, and
  how does it interact with `list[i64]` and fixed-width operations?
- Is there any writable IO or stdin path in LPython 0.22, or is the `Cli` fixture impossible
  without a host layer?
- Are the class-instance segfaults permanent subset limits or compiler bugs that might be fixed?
  If permanent, tagged lists or records are the only value model.
- Is there a fixed LPython release or workaround for the string-slicing bug beyond loop-built
  substrings?
- Is `assert` the only usable error path? Uncaught `raise` loses the message.
- Can `leanscript_runtime.externs` stay plain module-level data, or does the runtime need a
  heterogeneous mapping that LPython cannot express?
- Does LPython expose enough of its memory model to implement `isShared`, or should the emitter
  treat objects as always shared?
