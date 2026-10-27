# leanscript
Lean to CPython 3

leanscript compiles Lean 4 programs to CPython 3 source. Lean stays in the frontend: it elaborates
the input and collects the compiler IR, and a Python backend emits CPython 3 source (`.py`) that
imports `leanscript_runtime`. The target is CPython 3.11 or newer. The JavaScript emitter, runtime,
and tests are being retired.

LPython 0.22.0 was evaluated as an alternative target and rejected: 21 of 32 compiler probes fail.
The blockers include no object model, no arbitrary-precision integers (Lean `Nat` is unbounded),
no closures or exceptions, and no writable IO or stdin. [The probe report](docs/lpython-subset.md)
records the matrix and the exact diagnostics; [the refactor plan](docs/refactor-plan.md) records
the decision and the component scope. See also [the IR JSON boundary](docs/ir-json.md).

## Tests

`pixi run test` runs the fixture suite. The target runner is CPython 3.11 or newer; `tests/run.py`
still defaults to the rejected LPython runner until the harness change recorded in the refactor
plan lands. `tests/lpython/` holds the compiler probe matrix; it is evidence, not part of
`pixi run test`. See `tests/README.md`.

[![](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:mss5l446ynjlw6e67y6u5fsq/bafkreigi4fxmqpn2d7soi4d344tipzamivhwofnulhye4unjc3ljmlke5u)](https://bsky.app/profile/tonofcrates.bsky.social/post/3my3zodphxk2k)
