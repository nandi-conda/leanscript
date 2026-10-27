# Tests

`tests/run.py` compiles every `tests/fixtures/*.lean` program to CPython source and checks its
output and exit code against the adjacent `.expected` and `.exitcode` files. A missing `.exitcode`
file means the exit code must be 0. The target is CPython 3.11 or newer.

## Running

```sh
pixi run test
```

`pixi run test` runs `pixi run build` first, then `tests/run.py` and `tests/ir_json.py`. The build
produces `.lake/build/bin/leanscript-ir`, which the backend runs. The harness invokes the backend
as `python -m leanscript compile` and runs each generated program with the current interpreter in
a working directory outside the repository root, so the program's bootstrap must make
`leanscript_runtime` resolve to the in-tree package.

The pinned `lpython` dependency in `pixi.toml` exists only for the rejection evidence in
`tests/lpython/run_probes.py`; it is not part of `pixi run test`.

## Fixture files

Each fixture is a `.lean` file plus optional sidecars:

| File | Meaning |
| --- | --- |
| `.expected` | Expected standard output, from native Lean. |
| `.exitcode` | Expected exit code. Omit it when the exit code is 0. |
| `.args` | Command-line arguments, one per line. |
| `.stdin` | Standard input. |

Each program runs in its own empty working directory.

`.expected` and `.exitcode` are the semantic baseline. `tests/run.py --bless` regenerates them by
compiling each program with native Lean and running it, which needs `lean` and `leanc` on `PATH`.

## IR JSON boundary

`tests/ir_json.py` checks the `leanscript-ir dump-json` contract in `docs/ir-json.md`: schema
version 1, the top-level shape, name-index ranges, and the `-o` file contract. It uses
`LEANSCRIPT_IR`, then `.lake/build/bin/leanscript-ir`, then `PATH`, matching the CLI.
