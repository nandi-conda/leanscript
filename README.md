# leanscript
Lean to CPython 3

leanscript compiles Lean 4 programs to CPython 3 source. Lean stays in the frontend: it elaborates
the input and collects the compiler IR, and a Python backend emits CPython 3 source (`.py`) that
imports `leanscript_runtime`. The target is CPython 3.11 or newer. The JavaScript emitter, runtime,
and tooling, including the JS test harness, are retired; they are no longer in the repository.

LPython 0.22.0, a separate compiler project, was evaluated as an alternative target and rejected:
21 of 32 compiler probes fail. The blockers include no object model, no arbitrary-precision
integers (Lean `Nat` is unbounded), no closures or exceptions, and no writable IO or stdin.
leanscript neither targets nor invokes LPython: generated `.py` files are ordinary CPython 3
source and run with `python`, not `lpython`. [The probe report](docs/lpython-subset.md) records the
matrix and the exact diagnostics; [the refactor plan](docs/refactor-plan.md) records the decision
and the component scope. See also [the IR JSON boundary](docs/ir-json.md).

## Build and tests

`pixi run build` runs `lake build` and produces the Lean frontend,
`.lake/build/bin/leanscript-ir`. `pixi run test` runs the build first and then the fixture suite,
so a fresh checkout needs no separate build step. `pixi run example hello` builds the frontend and
then compiles and runs `examples/hello.lean`; every name in `examples/` works. See
[`examples/README.md`](examples/README.md).

Run the compiler through `pixi run`, for example `pixi run python -m leanscript compile
examples/hello.lean -o .lake/build/examples/hello.py`, then run the generated file with
`pixi run python .lake/build/examples/hello.py`. The frontend runs `lean --print-prefix` at run time
to locate Lean's standard library, so `lean` must be on `PATH`; a plain Python environment does not
provide it. Build and run with the same toolchain, because Lean rejects library files from a
different version.

`pixi.toml` provides Lean 4.33.0 from conda-forge, the newest version available there.
`lean-toolchain` pins Lean 4.35.0 for elan-based setups; use the Nix dev shell or an elan install
when you need that exact toolchain (`flake.nix` provides elan and Python 3, with no Node or pnpm).

Lean 4's language server needs no separate package: the `lean4` dependency installs `lean`, `lake`,
and the server they start. `pixi run lsp` runs `lean --server` on stdio, and `pixi run lake serve`
runs the same server with the project's Lake configuration.

An editor started from a desktop icon does not inherit the shell `PATH` or `ELAN_HOME`, and Zed's
Lean 4 extension does not look in `.pixi`, so give it the pixi `lake` explicitly:

```json
{
  "lsp": {
    "lean4-lsp": {
      "binary": {
        "path": "/home/you/leanscript/.pixi/envs/default/bin/lake",
        "arguments": ["serve", "--"]
      }
    }
  }
}
```

The path must be absolute: the extension uses it as given, not relative to the worktree. Run
`pixi install` once so the environment exists, and confirm the path with
`pixi run bash -c 'command -v lake'`, which also covers a detached environment in the pixi cache
instead of `.pixi/envs`. This server is Lean 4.33.0, so keep building with pixi; Lean rejects
`.olean` files from another version. For the 4.35.0 pin, point Zed at `~/.elan/bin/lake` after
`elan toolchain install`, or enable the extension's `elan_auto_install` setting instead.

`tests/run.py` runs generated source with CPython 3.11 or newer. There is no runner switch.
The fixture suite is 22/22 and `tests/ir_json.py` passes. `tests/lpython/` and the pinned LPython
dependency are evidence for the rejected path, not part of `pixi run test`. See `tests/README.md`.

[![](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:mss5l446ynjlw6e67y6u5fsq/bafkreigi4fxmqpn2d7soi4d344tipzamivhwofnulhye4unjc3ljmlke5u)](https://bsky.app/profile/tonofcrates.bsky.social/post/3my3zodphxk2k)
