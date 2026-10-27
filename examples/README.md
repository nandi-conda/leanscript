# Examples

Seven self-contained Lean programs for the pipeline "Lean frontend → IR JSON → CPython backend →
`leanscript_runtime`". They use only Lean's core library and CPython's standard library: no `Std`
imports, no fixture sidecars, and no LPython subset rules or workarounds.

## Prerequisites

- Lean 4.35.0 from elan, with `lake` on `PATH`. `lake build` in the repository root builds
  `.lake/build/bin/leanscript-ir`, which the backend invokes. The pixi environment alone cannot
  elaborate Lean source; see the repository README for the elan setup.
- CPython 3.11 or newer. The commands below use `python`; inside the pixi environment, prefix them
  with `pixi run`.

## Compile and run

Build the frontend once from the repository root:

```sh
lake build
```

Then compile one example and run the emitted source:

```sh
python -m leanscript compile examples/hello.lean -o .lake/build/examples/hello.py
PYTHONPATH=. python .lake/build/examples/hello.py
```

- `python -m leanscript compile` runs the Lean frontend, reads the IR JSON, and writes CPython
  source.
- `-o` keeps the generated `.py` in `.lake/build/examples/`, which Git ignores. Without `-o`, the
  backend writes `<input>.py` next to the input.
- `PYTHONPATH=.` lets the generated program import `leanscript_runtime` from the repository root.

To compile and run all of them:

```sh
for name in hello numbers arrays strings closures inductives refs; do
  python -m leanscript compile "examples/$name.lean" -o ".lake/build/examples/$name.py"
  PYTHONPATH=. python ".lake/build/examples/$name.py"
done
```

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
