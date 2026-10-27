# Tests

`tests/run.py` compiles every `tests/fixtures/*.lean` program to Python source and checks its
output and exit code against the adjacent `.expected` and `.exitcode` files. A missing `.exitcode`
file means the exit code must be 0. The target is CPython 3.11 or newer.

## Running

```sh
pixi run test
```

`pixi run test` runs `tests/run.py` and then `tests/ir_json.py`.

The runner is selected with `LEANSCRIPT_TEST_RUNNER`:

- `cpython` (default, and the target) runs each emitted file with the project interpreter, with the
  repository root on `PYTHONPATH` so that `leanscript_runtime` resolves to the in-tree package.
- `lpython` is the rejected target. It stays selectable only to reproduce the rejection evidence in
  [`docs/lpython-subset.md`](../docs/lpython-subset.md), and it is not part of `pixi run test`.

The LPython compiler is pinned in `pixi.toml` only for that evidence and for
`tests/lpython/run_probes.py`. It publishes only a linux-64 build on conda-forge.

## Fixture files

Each fixture is a `.lean` file plus optional sidecars:

| File | Meaning |
| --- | --- |
| `.expected` | Expected standard output, from native Lean. |
| `.exitcode` | Expected exit code. Omit it when the exit code is 0. |
| `.args` | Command-line arguments, one per line. |
| `.stdin` | Standard input. |
| `.unsupported-lpython` | Why the fixture cannot run under the rejected LPython compiler. |

An `.unsupported-lpython` file makes the harness print a skip and the reason, but only under
`LEANSCRIPT_TEST_RUNNER=lpython`. The target run never reads it. A skip never counts as a pass, and
`--bless` ignores it. Use it only for fixtures that the pinned compiler structurally cannot run,
not to silence failures; `Cli` is the only one, because LPython has no standard input and a
read-only `os`. `Cli` passes on CPython and needs no sidecar there.

Each program runs in its own empty working directory.

## IR JSON boundary

`tests/ir_json.py` checks the `leanscript-ir dump-json` contract in `docs/ir-json.md`: schema
version 1, the top-level shape, name-index ranges, and the `-o` file contract. It uses
`LEANSCRIPT_IR`, then `.lake/build/bin/leanscript-ir`, then `PATH`, matching the CLI.
