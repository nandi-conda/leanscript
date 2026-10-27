# LPython 0.22.0 probe report

> **Verdict: LPython 0.22.0 is rejected as the transpile target.** 21 of 32 probes fail, including
> every probe for dynamic values, exceptions, closures, byte arrays, and file or standard IO. The
> target is CPython 3. The decision and the component scope are in
> [`docs/refactor-plan.md`](refactor-plan.md). This document is the evidence; it is not a target
> specification.

## Version and provenance

- Compiler: LPython 0.22.0.
- Source: conda-forge, `linux-64`, pinned in `pixi.toml` as `lpython = "==0.22.0"`.
- Release date: 2024-07-08. This is the newest release on conda-forge and GitHub.
- Compilation model: `lpython <probe>.py -o <executable>` compiles ahead of time to a native
  executable. The probe matrix compiles and runs the executable.

The compiler is kept as a pinned probe dependency only. It is not a build or test dependency of
leanscript.

## Reproducing the matrix

```sh
pixi run python tests/lpython/run_probes.py
```

The probes are in `tests/lpython/probes/`. Each probe is a small, independent program with a
`main()` call, and no probe imports `leanscript_runtime`: the matrix measures the compiler, not the
runtime. The runner compiles a probe and, if compilation succeeds, runs the executable. The
`assert` and `sys.exit` probes expect a nonzero exit, because that is the behavior under test.

## Probe matrix

| Probe | Construct | Result | Output or compiler diagnostic |
| --- | --- | --- | --- |
| `class_constructor.py` | classes: annotated fields, default constructor | pass | `1` |
| `class_init.py` | classes: explicit `__init__` | fail | `semantic error: Only default constructors implemented` |
| `class_method.py` | classes: methods | fail | `semantic error: Argument does not have a type` |
| `class_param.py` | classes: struct as function parameter | pass | `3` |
| `try_except.py` | exceptions: `try`/`except` | fail | `Internal Compiler Error: Unhandled exception (LCompilersException: visit_Try() not implemented)` |
| `assert_abort.py` | exceptions: `assert` abort | pass | `exit 1: AssertionError: negative` |
| `exit_code.py` | exceptions: `sys.exit` | pass | `exit 3: 1 / STOP 3` |
| `closure.py` | closures: nested function | fail | `semantic error: Internal FunctionDef: Not implemented` |
| `lambda.py` | closures: `lambda` | fail | `Internal Compiler Error: Unhandled exception (LCompilersException: visit_Lambda() not implemented)` |
| `first_class_function.py` | closures: function passed as a value | fail | `semantic error: Unsupported call type for f` |
| `comprehension.py` | comprehensions: list comprehension | fail | `Internal Compiler Error: Unhandled exception (LCompilersException: visit_ListComp() not implemented)` |
| `bytearray_bytes.py` | bytes: `bytearray` | fail | `semantic error: The type 'bytearray' is undeclared.` |
| `bytes_literal.py` | bytes: `bytes` literal | fail | `semantic error: The type 'bytes' is undeclared.` |
| `file_write.py` | io: writable file | fail | `semantic error: Function 'open' is not declared and not intrinsic` |
| `os_api.py` | io: `os.makedirs` | fail | `semantic error: The symbol 'makedirs' not found in the module 'os'` |
| `os_environ.py` | io: environment read | fail | `semantic error: The symbol 'getenv' not found in the module 'os'` |
| `os_cwd.py` | io: current directory | fail | `semantic error: The symbol 'getcwd' not found in the module 'os'` |
| `stdin_read.py` | io: standard input | fail | `semantic error: Only Name type and constant integers supported in Call` |
| `stderr_write.py` | io: standard error | fail | `semantic error: Only Name type and constant integers supported in Call` |
| `argv.py` | io: `sys.argv` | pass | `1` |
| `bare_int.py` | numbers: bare `int` | fail | `semantic error: int type is not supported yet.` |
| `dynamic_values.py` | dynamic values: union annotation | fail | `semantic error: Only Name, Subscript, and Call supported for now in annotation of annotated assignment.` |
| `typing_any.py` | dynamic values: `typing.Any` | fail | `semantic error: Could not find the module 'typing'. If an import path is available, please use the `-I` option to specify it` |
| `heterogeneous_list.py` | dynamic values: heterogeneous list | fail | `semantic error: All List elements must be of the same type for now` |
| `dict_typed.py` | dynamic values: homogeneous typed dict | pass | `1` |
| `tagged_cell.py` | dynamic values: one tagged cell with typed slots | pass | `1 / 2 / 1` |
| `list_of_cells.py` | dynamic values: list of structs | fail | `compiler crashed with signal 11, no diagnostic` |
| `recursive_cell.py` | dynamic values: recursive struct | fail | `semantic error: The type 'Cell' is undeclared.` |
| `recursion.py` | recursion: 1000-deep non-tail | pass | `1000` |
| `string_ascii.py` | strings: ASCII operations | pass | `5 / h / 2 / HELLO / hello! / 5` |
| `string_utf8.py` | strings: UTF-8 bytes | pass | `2 / -61 / é` |
| `string_escapes.py` | strings: escape decoding | pass | `3 / 6` |

## What the compiler accepts

LPython 0.22.0 accepts a statically typed leaf-program subset:

- Annotated functions and 1,000-deep non-tail recursion (`recursion`).
- `i32`, `i64`, and `f64`; `list[T]` and `dict[K, V]` with one element type (`dict_typed`).
- Classes with annotated fields, the generated default constructor, post-construction field
  assignment, and free functions that take or return the struct (`class_constructor`, `class_param`).
- A single tagged cell with typed slots (`tagged_cell`).
- ASCII `str` operations: `len`, indexing, `find`, `startswith`, `upper`, `+`, `==`, and `str(i32)`
  (`string_ascii`).
- `print`, `sys.argv`, `sys.exit`, and `assert` (`argv`, `exit_code`, `assert_abort`).
- Imports with `-I`.

This subset is real, but it cannot host `leanscript_runtime`. Every capability the runtime's value
model needs is missing.

## Where the runtime cannot follow

### Dynamic values

A Lean IR value is a constructor with a tag and a vector of fields. The fields mix constructors,
closures, strings, arrays, and scalars. LPython needs one static type per slot.

- There is no `Any`: `from typing import Any` fails because the `typing` module is missing
  (`typing_any`).
- There are no union types: `x: i32 | str` is rejected (`dynamic_values`).
- Containers are homogeneous: `list[i32] = [1, "a"]` is rejected (`heterogeneous_list`).
- A single tagged cell with typed slots compiles (`tagged_cell`), so a value can be encoded once.
  Values cannot form a heap: `list[Cell]` crashes the compiler with `SIGSEGV` and no diagnostic
  (`list_of_cells`), and a recursive `Cell` field is rejected because the class type is not visible
  in its own body (`recursive_cell`).
- A homogeneous typed `dict[str, i32]` works (`dict_typed`), but it cannot hold mixed values.

A parallel-array encoding, where every value is an integer index into typed arrays, is conceivable.
That is a new runtime design, not a port, and it still cannot express methods, closures,
exceptions, bytes, or IO. The project does not attempt it.

### Classes and methods

- Annotated fields with the generated default constructor work, including field assignment after
  construction (`class_constructor`).
- A struct passed to and returned from a free function works (`class_param`).
- An explicit `__init__` is rejected: "Only default constructors implemented" (`class_init`).
- A method is rejected: "Argument does not have a type" because `self` has no type (`class_method`).
- There are no methods, so `Ctor`, `Closure`, `Ref`, `Thunk`, `Handle`, `LeanArray`, and
  `LeanString` cannot keep their behavior on the object.

### Exceptions

- `try`/`except` is an internal compiler error: `visit_Try() not implemented` (`try_except`).
- The only abort paths are `assert cond, msg`, which prints `AssertionError: msg` and exits 1
  (`assert_abort`), and `sys.exit(n)`, which prints `STOP n` to stderr and exits `n` (`exit_code`).
- `ExitCode`, `UncaughtError`, `InitializeError`, `Jmp`, and `Tail` all depend on exceptions.

### Closures and first-class functions

- A nested function is rejected: "Internal FunctionDef: Not implemented" (`closure`).
- `lambda` is an internal compiler error: `visit_Lambda() not implemented` (`lambda`).
- A function value cannot be called: `f: i32` with `f(x)` gives "Unsupported call type for f"
  (`first_class_function`).
- There is no function type, so `Closure`, `pap`, `apply`, thunks, and the extern table of
  callables cannot be represented.

### Comprehensions

- A list comprehension is an internal compiler error: `visit_ListComp() not implemented`
  (`comprehension`). This alone is a workaround, but it adds no capability.

### Bytes and byte arrays

- `bytearray` is undeclared (`bytearray_bytes`).
- `bytes` and `b"..."` literals are undeclared (`bytes_literal`).
- `str.encode` and `bytes.decode` do not exist, so the runtime cannot move between text and bytes.
- `LeanString` and `ByteArray` depend on both.

### Numbers

- Bare `int` is unsupported: "int type is not supported yet" (`bare_int`). Every binding needs a
  fixed-width type such as `i32` or `i64`.
- Lean `Nat` and `Int` are arbitrary precision. LPython's integers are fixed width, so large values
  need a representation that this matrix does not provide.

### Strings

- ASCII operations work (`string_ascii`).
- A `str` is UTF-8 bytes. `len("é")` is 2, `s[0]` is the signed byte `-61`, and `upper()` leaves
  non-ASCII bytes unchanged (`string_utf8`).
- `\n` in a literal is decoded (length 3 for `"a\nb"`), but `\u00e9` is not (length 6)
  (`string_escapes`). Unicode escapes in source keep their six characters.
- There is no encode or decode. Byte offsets and hashes, which `LeanString` needs, cannot be
  implemented on LPython's `str`.

### File and standard IO

- `open` is not declared and not intrinsic (`file_write`).
- `os.makedirs`, `os.getenv`, and `os.getcwd` are missing from the `os` module (`os_api`,
  `os_environ`, `os_cwd`).
- `sys.stdin.readline` is rejected: "Only Name type and constant integers supported in Call"
  (`stdin_read`).
- `sys.stderr.write` is rejected for the same reason (`stderr_write`).
- `print` and `sys.argv` work (`argv`). There is no other output path, no input path, and no file
  system access.
- The `Cli` fixture, `WordFrequency`, and every fixture that writes files or reads stdin are
  blocked by this, not by emitter work.

### Recursion

- A 1,000-deep non-tail recursion compiles and runs (`recursion`). `ExprParser` needs that depth,
  so recursion alone is not a blocker. It is the only runtime-shaped capability that survives.

## Additional evidence from the wider probe set

The 32-probe matrix is the minimal reproduction. The earlier, wider probe set recorded the
following findings. They agree with the matrix and close questions the matrix does not ask. They
are additional evidence, not part of the counts above.

### Object model

Classes are not heap objects:

- Returning a class instance from a function crashes the compiler.
- `list[P]` where `P` is a class crashes the compiler.
- A class-typed field in another class is rejected: `'node' must be initialized with an instance of
  struct Node`.
- Mutating a field through a function parameter is rejected: `Assignment to an input function
  parameter 'p' is not allowed`.
- Local field assignment after construction works, and an instance can be passed to a function for
  reading.

The local-only pattern is not a replacement for `Ctor`: a constructor value must be returned,
stored in arrays, and referenced from other values.

### Bignums and `u64`

- LPython has `i8` through `i64`, `u64`, and `f64`; it has no arbitrary-precision integer.
- Lean `Nat` and `Int` are unbounded. Fixtures print `30!`, `2^100`, `10^20`, and `fib(200)`, so
  the runtime needs a bignum layer. `Loops`, `NumberCrunching`, `Caching`, `Builtins`, and
  `ExprParser` cannot pass until it exists.
- A `u64` decimal literal above the `i64` maximum is rejected: `Cannot cast negative value to
  unsigned integer`.
- `u64(9223372036854775807)` printed `4611709631586744390`; decimal construction is unreliable.
- Build large constants from shifts: `(u64(1) << u64(63)) - u64(1)` is exact.
- Addition wraps modulo `2^64`.
- `/` on integers returns `f64`; use `//` for integer division.

### String byte semantics

- `len("é") == 2` and `len("日") == 3`; `str` is a UTF-8 byte string.
- `s[i]` returns a one-byte `str`; `"é"[0] + "é"[1] == "é"`.
- `print("é")` writes the bytes `c3 a9` unchanged.
- `ord(s[i])` returns the signed byte; `ord("é"[0]) == -61`, so mask with `& 255`.
- `s[0] = "z"` fails at runtime: `'str' object does not support item assignment`.
- A byte-loop substring copy works. Slicing inside a function is unreliable: some slices print
  nothing, and `s[i:]` or `s[0:i] + "X" + s[i:]` can crash the compiler.

The byte semantics fit Lean's `String.Pos`, but the missing item assignment and unreliable slicing
mean a `LeanString` API cannot be built from `str` operations alone.

### Uncaught raises

- An uncaught `raise ValueError("boom")` prints `ERROR STOP` with no message and exits 1. It is not
  a usable diagnostic path; only `assert cond, msg` keeps the message.

## Diagnostic behavior


| Outcome | Exit code | Output |
| --- | --- | --- |
| Semantic error | 2 | `semantic error: <message>` and a source span on stderr. |
| Internal compiler error | 1 | `Internal Compiler Error: Unhandled exception` and a traceback with `LCompilersException`. |
| Compiler crash | signal 11 (shell status 139) | `list[Cell]` crashed with no diagnostic. |
| `assert` failure | 1 | `AssertionError: <msg>` on stderr. |
| Uncaught `raise` | 1 | `ERROR STOP` with no message. |
| `sys.exit(n)` | `n` | `STOP n` on stderr; earlier stdout is preserved. |

An internal compiler error exits 1, not 2. Earlier notes that claimed 2 for that case were wrong.

## Reconsideration criteria

LPython can be reconsidered only when a release passes the whole matrix and, at minimum:

1. Dynamic values: `Any`, a union type, or heterogeneous containers, plus a working `list` of
   structs and recursive struct fields.
2. Classes with explicit constructors and methods.
3. Closures, nested functions, and first-class function values.
4. `try`/`except` with typed exceptions.
5. `bytes` and `bytearray` with `encode` and `decode`.
6. Writable files, stdin, stderr, `os` environment and current directory, and `time.sleep`.
7. Arbitrary-precision integers, or a supported bignum path that fixtures can use.

Until then, the runtime and generated programs stay on CPython 3. Re-run
`pixi run python tests/lpython/run_probes.py` before reconsidering.

## Probe sources

Every probe is listed with its result. The compiler output is in the matrix above.

### `class_constructor.py`

Construct: classes: annotated fields, default constructor. Result: pass (`1`).

```python
class Ctor:
    tag: i32
    value: i32


def main() -> None:
    c: Ctor = Ctor(1, 2)
    print(c.tag)


main()
```

### `class_init.py`

Construct: classes: explicit `__init__`. Result: fail (`semantic error: Only default constructors implemented`).

```python
class Ctor:
    tag: i32
    value: i32

    def __init__(self, tag: i32, value: i32) -> None:
        self.tag = tag
        self.value = value


def main() -> None:
    c: Ctor = Ctor(1, 2)
    print(c.tag)


main()
```

### `class_method.py`

Construct: classes: methods. Result: fail (`semantic error: Argument does not have a type`).

```python
class Ctor:
    tag: i32

    def get(self) -> i32:
        return self.tag


def main() -> None:
    c: Ctor = Ctor()
    c.tag = 7
    print(c.get())


main()
```

### `class_param.py`

Construct: classes: struct as function parameter. Result: pass (`3`).

```python
class Ctor:
    tag: i32


def get_tag(c: Ctor) -> i32:
    return c.tag


def main() -> None:
    c: Ctor = Ctor()
    c.tag = 3
    print(get_tag(c))


main()
```

### `try_except.py`

Construct: exceptions: `try`/`except`. Result: fail (`Internal Compiler Error: Unhandled exception (LCompilersException: visit_Try() not implemented)`).

```python
def check(x: i32) -> i32:
    try:
        if x < 0:
            raise ValueError("negative")
        return x
    except ValueError:
        return 0


def main() -> None:
    print(check(-1))


main()
```

### `assert_abort.py`

Construct: exceptions: `assert` abort. Result: pass (`exit 1: AssertionError: negative`).

```python
def check(x: i32) -> i32:
    assert x > 0, "negative"
    return x


def main() -> None:
    print(check(-1))


main()
```

### `exit_code.py`

Construct: exceptions: `sys.exit`. Result: pass (`exit 3: 1 / STOP 3`).

```python
import sys


def main() -> None:
    print(1)
    sys.exit(3)


main()
```

### `closure.py`

Construct: closures: nested function. Result: fail (`semantic error: Internal FunctionDef: Not implemented`).

```python
def make_adder(n: i32) -> i32:
    def add(x: i32) -> i32:
        return x + n
    return add


def main() -> None:
    f: i32 = make_adder(3)
    print(f(4))


main()
```

### `lambda.py`

Construct: closures: `lambda`. Result: fail (`Internal Compiler Error: Unhandled exception (LCompilersException: visit_Lambda() not implemented)`).

```python
def main() -> None:
    f: i32 = lambda x: x + 1
    print(f(1))


main()
```

### `first_class_function.py`

Construct: closures: function passed as a value. Result: fail (`semantic error: Unsupported call type for f`).

```python
def inc(x: i32) -> i32:
    return x + 1


def apply_it(f: i32, x: i32) -> i32:
    return f(x)


def main() -> None:
    print(apply_it(inc, 1))


main()
```

### `comprehension.py`

Construct: comprehensions: list comprehension. Result: fail (`Internal Compiler Error: Unhandled exception (LCompilersException: visit_ListComp() not implemented)`).

```python
def main() -> None:
    xs: list[i32] = [1, 2, 3]
    ys: list[i32] = [x * 2 for x in xs]
    print(len(ys))


main()
```

### `bytearray_bytes.py`

Construct: bytes: `bytearray`. Result: fail (`semantic error: The type 'bytearray' is undeclared.`).

```python
def main() -> None:
    b: bytearray = bytearray(3)
    b[0] = 65
    print(len(b))


main()
```

### `bytes_literal.py`

Construct: bytes: `bytes` literal. Result: fail (`semantic error: The type 'bytes' is undeclared.`).

```python
def main() -> None:
    b: bytes = b"abc"
    print(len(b))


main()
```

### `file_write.py`

Construct: io: writable file. Result: fail (`semantic error: Function 'open' is not declared and not intrinsic`).

```python
def main() -> None:
    f: i32 = open("data.txt", "w")
    print(1)


main()
```

### `os_api.py`

Construct: io: `os.makedirs`. Result: fail (`semantic error: The symbol 'makedirs' not found in the module 'os'`).

```python
import os


def main() -> None:
    os.makedirs("out")
    print(1)


main()
```

### `os_environ.py`

Construct: io: environment read. Result: fail (`semantic error: The symbol 'getenv' not found in the module 'os'`).

```python
import os


def main() -> None:
    print(len(os.getenv("HOME")))


main()
```

### `os_cwd.py`

Construct: io: current directory. Result: fail (`semantic error: The symbol 'getcwd' not found in the module 'os'`).

```python
import os


def main() -> None:
    print(len(os.getcwd()))


main()
```

### `stdin_read.py`

Construct: io: standard input. Result: fail (`semantic error: Only Name type and constant integers supported in Call`).

```python
import sys


def main() -> None:
    line: str = sys.stdin.readline()
    print(len(line))


main()
```

### `stderr_write.py`

Construct: io: standard error. Result: fail (`semantic error: Only Name type and constant integers supported in Call`).

```python
import sys


def main() -> None:
    sys.stderr.write("bad\n")


main()
```

### `argv.py`

Construct: io: `sys.argv`. Result: pass (`1`).

```python
import sys


def main() -> None:
    print(len(sys.argv))


main()
```

### `bare_int.py`

Construct: numbers: bare `int`. Result: fail (`semantic error: int type is not supported yet.`).

```python
def add(a: int, b: int) -> int:
    return a + b


def main() -> None:
    print(add(1, 2))


main()
```

### `dynamic_values.py`

Construct: dynamic values: union annotation. Result: fail (`semantic error: Only Name, Subscript, and Call supported for now in annotation of annotated assignment.`).

```python
def main() -> None:
    x: i32 | str = 1
    print(x)


main()
```

### `typing_any.py`

Construct: dynamic values: `typing.Any`. Result: fail (`semantic error: Could not find the module 'typing'. If an import path is available, please use the `-I` option to specify it`).

```python
from typing import Any


def main() -> None:
    x: Any = 1
    print(x)


main()
```

### `heterogeneous_list.py`

Construct: dynamic values: heterogeneous list. Result: fail (`semantic error: All List elements must be of the same type for now`).

```python
def main() -> None:
    xs: list[i32] = [1, "a"]
    print(len(xs))


main()
```

### `dict_typed.py`

Construct: dynamic values: homogeneous typed dict. Result: pass (`1`).

```python
def main() -> None:
    d: dict[str, i32] = {"a": 1}
    print(d["a"])


main()
```

### `tagged_cell.py`

Construct: dynamic values: one tagged cell with typed slots. Result: pass (`1 / 2 / 1`).

```python
class Cell:
    tag: i32
    ints: list[i32]
    strs: list[str]


def main() -> None:
    c: Cell = Cell()
    c.tag = 1
    c.ints = [7, 8]
    c.strs = ["a"]
    print(c.tag)
    print(len(c.ints))
    print(len(c.strs))


main()
```

### `list_of_cells.py`

Construct: dynamic values: list of structs. Result: fail (`compiler crashed with signal 11, no diagnostic`).

```python
class Cell:
    tag: i32
    value: i32


def main() -> None:
    a: Cell = Cell()
    a.tag = 1
    a.value = 7
    cs: list[Cell] = [a]
    print(len(cs))


main()
```

### `recursive_cell.py`

Construct: dynamic values: recursive struct. Result: fail (`semantic error: The type 'Cell' is undeclared.`).

```python
class Cell:
    tag: i32
    kids: list[Cell]


def main() -> None:
    c: Cell = Cell()
    c.tag = 1
    c.kids = []
    print(c.tag)


main()
```

### `recursion.py`

Construct: recursion: 1000-deep non-tail. Result: pass (`1000`).

```python
def count(n: i32) -> i32:
    if n <= 0:
        return 0
    return 1 + count(n - 1)


def main() -> None:
    print(count(1000))


main()
```

### `string_ascii.py`

Construct: strings: ASCII operations. Result: pass (`5 / h / 2 / HELLO / hello! / 5`).

```python
def main() -> None:
    s: str = "hello"
    c: str = ""
    n: i32 = 0
    for c in s:
        n += 1
    print(len(s))
    print(s[0])
    print(s.find("llo"))
    print(s.upper())
    print(s + "!")
    print(str(n))


main()
```

### `string_utf8.py`

Construct: strings: UTF-8 bytes. Result: pass (`2 / -61 / é`).

```python
def main() -> None:
    s: str = "é"
    print(len(s))
    print(ord(s[0]))
    print(s.upper())


main()
```

### `string_escapes.py`

Construct: strings: escape decoding. Result: pass (`3 / 6`).

```python
def main() -> None:
    s: str = "a\nb"
    t: str = "\u00e9"
    print(len(s))
    print(len(t))


main()
```

