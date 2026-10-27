# Tests

`tests/run.py` compiles every `tests/fixtures/*.lean` program and checks its output and exit code
against the adjacent `.expected` and `.exitcode` files. A missing `.exitcode` file means the exit
code must be 0.

## Running

```sh
pixi run test
```

`pixi run test` runs `tests/run.py` and then `tests/ir_json.py`.

The target runner is selected with `LEANSCRIPT_TEST_RUNNER`:

- `lpython` (default, and the stated target) compiles each emitted file with the pinned LPython
  compiler and runs the executable.
- `cpython` is the explicitly flagged fallback, which requires user approval. While the LPython
  backend is incomplete, `LEANSCRIPT_TEST_RUNNER=cpython pixi run test` is the green path.

The LPython compiler is pinned in `pixi.toml` for linux-64, the only platform conda-forge
publishes it for.

## Fixture files

Each fixture is a `.lean` file plus optional sidecars:

| File | Meaning |
| --- | --- |
| `.expected` | Expected standard output, from native Lean. |
| `.exitcode` | Expected exit code. Omit it when the exit code is 0. |
| `.args` | Command-line arguments, one per line. |
| `.stdin` | Standard input. |
| `.unsupported-lpython` | Why the fixture cannot run under LPython. |

An `.unsupported-lpython` file makes the harness print a skip and the reason under the LPython
runner. A skip never counts as a pass, and `--bless` ignores it. Use it only for fixtures that the
pinned compiler structurally cannot run, not to silence failures.

Each program runs in its own empty working directory.

## IR JSON boundary

`tests/ir_json.py` checks the `leanscript-ir dump-json` contract in `docs/ir-json.md`: schema
version 1, the top-level shape, name-index ranges, and the `-o` file contract. It uses
`LEANSCRIPT_IR`, then `.lake/build/bin/leanscript-ir`, then `PATH`, matching the CLI.
