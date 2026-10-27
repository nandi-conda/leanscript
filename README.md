# leanscript
Lean to CPython 3

leanscript compiles Lean 4 programs to CPython 3 source. Lean stays in the frontend: it elaborates
the input and collects the compiler IR, and a Python backend emits CPython 3 source (`.py`) that
imports `leanscript_runtime`. The target is CPython 3.11 or newer. The JavaScript emitter, runtime,
and tooling, including the JS test harness, are retired; they are no longer in the repository.

LPython 0.22.0 was evaluated as an alternative target and rejected: 21 of 32 compiler probes fail.
The blockers include no object model, no arbitrary-precision integers (Lean `Nat` is unbounded),
no closures or exceptions, and no writable IO or stdin. [The probe report](docs/lpython-subset.md)
records the matrix and the exact diagnostics; [the refactor plan](docs/refactor-plan.md) records
the decision and the component scope. See also [the IR JSON boundary](docs/ir-json.md).

## Build and tests

`pixi run build` runs `lake build` and produces the Lean frontend,
`.lake/build/bin/leanscript-ir`. `pixi run test` runs the build first and then the fixture suite,
so a fresh checkout needs no separate build step. `pixi run example hello` builds the frontend and
then compiles and runs `examples/hello.lean`; every name in `examples/` works. See
[`examples/README.md`](examples/README.md).

Run the compiler through `pixi run`, for example `pixi run python -m leanscript compile
examples/hello.lean`. The frontend runs `lean --print-prefix` at run time to locate Lean's standard
library, so `lean` must be on `PATH`; a plain Python environment does not provide it. Build and run
with the same toolchain, because Lean rejects library files from a different version.

`pixi.toml` provides Lean 4.33.0 from conda-forge, the newest version available there.
`lean-toolchain` pins Lean 4.35.0 for elan-based setups; use the Nix dev shell or an elan install
when you need that exact toolchain (`flake.nix` provides elan and Python 3, with no Node or pnpm).

`tests/run.py` runs generated source with CPython 3.11 or newer. There is no runner switch.
The fixture suite is 22/22 and `tests/ir_json.py` passes. `tests/lpython/` and the pinned LPython
dependency are evidence for the rejected path, not part of `pixi run test`. See `tests/README.md`.

[![](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:mss5l446ynjlw6e67y6u5fsq/bafkreigi4fxmqpn2d7soi4d344tipzamivhwofnulhye4unjc3ljmlke5u)](https://bsky.app/profile/tonofcrates.bsky.social/post/3my3zodphxk2k)
