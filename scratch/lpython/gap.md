# LPython 0.22 runtime gap

LPython 0.22.0 is the stated target. The modules in `leanscript_runtime/` are currently
CPython-shaped and stay as the semantic reference; this note records, per file, exactly which
constructs LPython 0.22 rejects and what has to replace them. Every verdict below was produced by
compiling a probe with the pinned compiler, not inferred.

Compiler: `lpython 0.22.0` from conda-forge (linux-64), the newest GitHub release (v0.22.0,
2024-07-08). Probe project: a scratch pixi workspace with `pixi add lpython`; probes are run with
`lpython probe.py -o probe.out && ./probe.out`.

## Cross-file rejections

These appear in all three modules:

| Construct | Verdict |
| --- | --- |
| `from __future__ import annotations` | `Could not find the module '__future__'` |
| `class` with `__init__(self, ...)` | `Only default constructors implemented` |
| class inheritance (`class LeanArray(list)`) | `Inheritance in classes isn't supported yet` |
| `__slots__` | `AnnAssign expected inside struct` |
| methods, `@property`, `__len__`, `__str__`, `describe` | `Argument does not have a type`; `Only Name, Subscript, and Call supported … in annotation`; `The type 'Ctor' is undeclared` |
| lambda | rejected (expression has no type) |
| `dict[str, callable]` as an extern table | no function type; a module-level `dict[str, str]` or `dict[str, int]` works |
| f-strings | compiler crash (`Internal Compiler Error: Unhandled exception`) |
| list/generator comprehensions | compiler crash |
| `isinstance` | `Function 'isinstance' is not declared and not intrinsic` |
| `try` / `except` | compiler crash (`visit_Try() not implemented`) |
| `bytearray` | `The type 'bytearray' is undeclared` |
| `bytes` and `b"..."` | `Variable 'b' not declared` (no bytes type) |
| `str.encode`, `bytes.decode` | unavailable with `bytes`; `str` already is UTF-8 bytes |
| `raise` (uncaught) | prints `ERROR STOP` with **no message** on stderr, exits 1 |
| `assert cond, msg` | prints `AssertionError: msg` on stderr, exits 1; the usable abort path |
| type annotations with `\|` (`bytes \| None`) | annotation rejected |
| `x = 1` without an annotation | `Variable 'x' not declared`; every binding needs `i32`/`i64`/`f64`/`str`/`list[T]`/`dict[K, V]` |
| `for x in ...` with an undeclared `x` | same; declare `x: i32 = 0` (or `x: str = ""`) first |
| default arguments, `print` with several arguments, module-level constants and dicts | work |

## `leanscript_runtime/string.py`

| Construct | Verdict | Replacement |
| --- | --- | --- |
| `from __future__ import annotations` (line 14) | rejected | omit |
| `class LeanString` with `__init__(data, encoded=None)` (29-52) | rejected | no class: `str` plus free functions, or a data-only class with a default constructor and post-construction assignment |
| `@property utf8` (47-52) | rejected | `def utf8(s): return s` (`str` is already UTF-8) |
| `data: str` holding decoded text, `_encoded: bytes` cache | `bytes` does not exist; `str.encode`/`bytes.decode` unavailable | `str` holds the UTF-8 bytes directly; no cache and no codec |
| `bytes` in `_string_of_bytes`, `_byte_at`, `_encode_char`, `_decode_char_at`, `_compare_bytes` (65-136, 254-262) | no `bytes` type | `str` (byte container) or `list[i32]`; `s[i]` is a one-byte `str`, `ord(s[i]) & 255` is the byte |
| `raw[b:e]` slicing and `raw[:i] + ... + raw[end:]` (190, 195-197, 237, 242) | **unreliable**: slicing a `str` parameter works when the slice is returned directly, but `len(s[b:e])` inside a function produces nothing and `s[0:i] + x + s[i:]` segfaults the compiler | copy bytes in a loop (`r += s[k]`) |
| `bytearray()` in `_of_list` (267) | no `bytearray` | build a `str` by concatenation, or `list[i32]` |
| `int | Ctor` type hint (174, 265, 276) | union rejected | `i32` handle once the value model exists |
| `Ctor(1, [char], None)` (178) | depends on the value model; a list of mixed values is rejected (`All List elements must be of the same type for now`) | tagged handle from the arena |
| `externs` mapping names to lambdas/functions (329-389) | no function values, lambda rejected | `dict[str, str]` from Lean extern name to runtime function name (plain data, importable by the backend and by LPython) |
| `hash_bytes(s.utf8, len, 11)` (296, 354) | `bytes` type missing; `u64` literals above `i64` maximum are rejected and large `u64` arguments printed incorrectly in one probe | pass `str` bytes; build 64-bit constants from shifts and adds; verify `u64` printing before relying on it |
| f-strings in `describe`/`__repr__` (42, 45) | compiler crash | plain concatenation, or omit |

Proven alternative: `scratch/lpython/string_lp.py` is a complete LPython 0.22 implementation of the
same byte-level semantics with `str` as the UTF-8 container, free functions, no reference counts
(strings are immutable and values), and byte-copy loops instead of slicing. Its output is
byte-identical to `leanscript_runtime/string.py` over a 2081-value matrix: byte and scalar lengths,
`get`/`next`/`prev`/`isValid`/`decode` at every position and past the end, the full extract grid,
`set` with 1-, 2-, 3-, and 4-byte chars, `push`, and `compare`/`decEq`/`decLt` on all pairs.

Reproduce:

```
lpython -I scratch/lpython scratch/lpython/string_matrix.py -o /tmp/string_matrix
/tmp/string_matrix > /tmp/lpython.txt
LEANSCRIPT_RUNTIME_STUBS=<dir with core.py and hash.py> \
  python scratch/lpython/reference_matrix.py /tmp/reference.txt
diff /tmp/lpython.txt /tmp/reference.txt
```

`string_matrix.expected` is the captured LPython output. `reference_matrix.py` needs `core.py` and
`hash.py`; `core.py` is checked in, `hash.py` is not yet, so the reference was taken against a
scratch copy of the package with a stub `hash.py`.

Two LPython facts the module relies on: `str` is a UTF-8 **byte** string (`len` counts bytes,
`s[i]` is one byte, `print` writes the bytes unchanged), and `ord(s[i])` is the **signed** value of
the byte, so it must be masked with `255`.

## `leanscript_runtime/array.py`

| Construct | Verdict | Replacement |
| --- | --- | --- |
| `class LeanArray(list)` (14) | inheritance rejected | no class; a bare `list[T]` or an arena index range |
| `__slots__ = ("rc",)` (17) | rejected | counts live in a separate `list[i32]` |
| `__init__`, `_children`, `describe` (19-29) | rejected | free functions |
| element type | `list[T]` is homogeneous: `list[i32] = [1, "a"]` → `All List elements must be of the same type for now` | every Lean value is one `i32` handle; see "the value model" below |
| `raise MemoryError(...)` (94) | compiles, but the message is lost (`ERROR STOP`, exit 1) | `assert n <= 0xFFFFFFFF, "out of memory"` |
| lambdas in the extern table (144-158) | rejected | `dict[str, str]` name table plus direct calls |
| `list` slicing, `append`, `pop`, `len`, item assignment | work on `list[T]` | as is |
| `isinstance` (removed already) | rejected | nothing |

Blocked, not fixable in this file: the array element type. See "the value model".

## `leanscript_runtime/bytearray.py`

| Construct | Verdict | Replacement |
| --- | --- | --- |
| `class ByteArray` with `__init__(data: bytearray)` (14-27) | `bytearray` undeclared; `__init__` rejected | `list[i32]` for a mutable byte buffer, or `str` for an immutable one, with a parallel `list[i32]` of counts |
| `bytearray(...)`, `bytes(...)` (32, 39, 55, 94, 99, 126) | undeclared | `list[i32]` or `str` |
| `try: bytes(a.data).decode("utf-8") / except UnicodeDecodeError` (97-103) | `try` crashes the compiler | hand-written UTF-8 validation over bytes |
| `bytearray(v & 0xFF for v in data)` generator (55) | comprehensions crash the compiler | `while` loop |
| `[b for b in a.data]` comprehension (61) | crashes | `while` loop |
| `raw[:size]`, `dest.data[:at]` slicing (32, 91) | `list` slicing works; `str` slicing is unreliable inside functions | loops for `str`, slicing for `list` |
| `set!`/`get!` out-of-bounds behavior | LPython has no silent out-of-bounds writes on `list[i32]`; index errors abort | keep the bounds checks from the reference |
| lambdas (112-129) | rejected | name table |

## The value model (blocks `Array` and `ByteArray`)

The Lean IR is dynamically typed: an object field holds a string, a Nat, a float, a closure, or
another constructor. LPython 0.22 has no `Any` (`from typing import Any` → `Could not find the
module 'typing'`), no union annotation, and homogeneous lists only. Classes cannot substitute for
heap cells either:

| Need | Probe result |
| --- | --- |
| construct a class instance and assign fields | works (annotated fields, default constructor) |
| pass an instance to a function and read a field | works |
| return an instance from a function | **compiler segfault** |
| store instances in a `list[Class]` | **compiler segfault** |
| mutate a field through a function parameter | `Assignment to an input function parameter 'p' is not allowed` |
| class-typed field in another class | `'node' must be initialized with an instance of struct Node` |

Consequence: a LPython runtime cannot use classes as heap objects. The only representation that
fits the compiler is a global arena of monomorphic tables with `i32` handles:

- `list[i32]` parallel arrays for the cell kind, tag, reference count, field count, first field, and
  next sibling, plus a value list per payload type (`list[i64]` for integers, `list[f64]` for
  floats, `list[str]` for strings, `list[i32]` for captured closure arguments).
- Every Lean value is an `i32` handle; tag dispatch is an `if`/`elif` chain, since there are no
  methods and no function values.
- Closures dispatch on an integer function id.
- `isShared` can conservatively return 1 (always copy) to stay correct.
- `inc`/`dec` operate on `list[i32]` counts; there is no GC interaction to worry about.

This is a redesign of the runtime and of the emitter's calling convention, not a port.

## Other constraints that change the emitted code

- No first-class functions: an extern reference cannot be a value. The emitter must emit a direct
  call to the runtime function for each extern instead of `$ext[...]` indirection, using a static
  `dict[str, str]` name table for the availability check.
- No exceptions: `unreachable`, unavailable externs, and panics use `assert cond, msg` (message on
  stderr, exit 1). `raise` loses the message.
- `sys.exit(n)` prints `STOP n` on stderr and exits `n`; earlier stdout is preserved.
- Extern functions must be annotated: erased type arguments arrive as `i32` placeholders, and the
  world token as `i32`.
- `-I <dir>` is required to import modules; there is no package import from source without it.
- LPython compiles ahead of time to a native executable, so `ls`/`readDir`/process externs are
  native calls, not CPython calls.

## Open questions

- Where does the arena live: module-level lists in `leanscript_runtime/core.py` (single translation
  unit), or a growable `list[i32]` passed to every function?
- Does LPython support `list[i64]`/`list[f64]` with the same operations as `list[i32]`?
- Does `u64` printing and arithmetic stay correct for all MurmurHash64A intermediates? One probe
  printed `u64(9223372036854775807)` as `4611709631586744390`, while `(u64(1) << u64(63)) - u64(1)`
  printed correctly, so decimal literals above `i64` maximum are not trustworthy.
- Is `str` stable enough for hashing and byte-array payloads, given the slicing bugs?
- How are class-free constructors initialized without a factory: fill a preallocated cell through an
  out-parameter, since returning an instance segfaults?
