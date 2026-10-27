# Examples

Seven self-contained Lean programs for the pipeline "Lean frontend → IR JSON → CPython backend →
`leanscript_runtime`". They use only Lean's core library and CPython's standard library: no `Std`
imports and no fixture sidecars. The compiler emits ordinary CPython 3 source. Run the generated
files with `python` (`pixi run python`), not with `lpython`, which is a separate compiler project
and is used here only for the rejection evidence in
[`docs/lpython-subset.md`](../docs/lpython-subset.md).

## Prerequisites

- The Lean frontend from this repository. `pixi run build` in the repository root runs `lake
  build` and produces `.lake/build/bin/leanscript-ir`, which the backend invokes. With an elan
  setup, `lake build` uses the pinned Lean 4.35.0 instead.
- CPython 3.11 or newer.
- `lean` on `PATH`, or `LEAN_SYSROOT` set. The frontend runs `lean --print-prefix` to locate Lean's
  standard library, so `lean` must be reachable from the shell that runs the backend. `pixi run`
  provides it; a Python-only environment does not. Build and run the frontend with the same
  toolchain, because Lean rejects library files from a different version.

## Compile and run

`pixi run example <name>` compiles one example and runs it:

```sh
pixi run example hello
```

The task runs `pixi run build` first, compiles `examples/<name>.lean` to
`.lake/build/examples/<name>.py`, and runs that file, so a fresh checkout needs no separate build
step. The name is the file stem without `.lean`; every example below works (`hello`, `numbers`,
`arrays`, `strings`, `closures`, `inductives`, `refs`). An unknown or missing name prints the list
of names and exits with status 2.

The same steps by hand:

```sh
pixi run build
pixi run python -m leanscript compile examples/hello.lean -o .lake/build/examples/hello.py
pixi run python .lake/build/examples/hello.py
```

- `pixi run python -m leanscript compile` runs the Lean frontend, reads the IR JSON, and writes
  CPython source. A plain `python -m leanscript` works only when `lean` is on `PATH` (for example
  in the Nix dev shell) or `LEAN_SYSROOT` is set.
- `-o` keeps the generated `.py` in `.lake/build/examples/`, which Git ignores. Without `-o`, the
  backend writes `<input>.py` next to the input; that file is not ignored and can go stale, so
  prefer `-o` into `.lake/build/`.
- You do not need to set `PYTHONPATH`. A generated program searches upward from its own directory
  for `leanscript_runtime` and falls back to the project root recorded at compile time, so plain
  `python .lake/build/examples/hello.py` works from any working directory. Run the file with
  CPython, not `lpython`.
- Regenerate rather than reuse stale output. Every `pixi run example <name>` compiles the current
  source over `.lake/build/examples/<name>.py`. Files generated before the bootstrap existed still
  fail with `ModuleNotFoundError`, and older output may not match the current emitter; delete
  `.lake/build/examples/` if in doubt.

All seven examples pass under pixi's Lean 4.33.0 and under the pinned 4.35.0. `refs` calls the
`ST.Prim.Ref.set` extern; `leanscript_runtime/ref.py` registers both the `set` and `put` spellings,
so the example runs on either toolchain.

Each program prints to standard output and exits with status 0. Their output matches native Lean
4.35.0 (`lean -c` followed by `leanc`).

## What each example shows

| Example | Lean constructs | Output |
| --- | --- | --- |
| `hello.lean` | `IO.println`, string interpolation, structural recursion | `Hello, world!` and `55` |
| `numbers.lean` | tail recursion, `Nat` factorial, arbitrary-precision integers, `for` loop | `1000000`, `30!`, `2^100 - 2^99`, `714`, `4950` |
| `arrays.lean` | `Array` `push`, `foldl`, `map`, `set!`, `reverse`, `qsort`, `contains` | array listings, `10`, `285`, `(0, 100)`, `true` |
| `strings.lean` | UTF-8 strings, character and byte length, case conversion, `splitOn`, `trimAscii`, concatenation | `14` characters, `19` UTF-8 bytes, `HéLLO, WöRLD 👋`, `01234` |
| `closures.lean` | functions as values, composition, partial application, `filter` and `foldl` | `63`, `[11, 12, 13]`, `17`, `6`, `9` |
| `inductives.lean` | inductive types, pattern matching, structures, record update, `deriving Repr, BEq` | shape descriptions, `p@(...)`, `(some 2)`, `none`, `true` |
| `refs.lean` | `initialize`, `IO.Ref`, `ST.Ref` with `runST`, `try`/`catch` | `0 1 2 3`, `#[a, b, c] #[z]`, `55`, `caught: failed with 5` |
