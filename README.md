# leanscript
Lean to LPython

leanscript compiles Lean 4 programs to LPython source. Lean stays in the frontend: it elaborates
the input and collects the compiler IR, and a Python backend emits LPython source (`.py`) that
imports `leanscript_runtime`. The target is LPython 0.22.0. The JavaScript emitter, runtime, and
tests are being retired.

LPython 0.22.0 cannot compile the current runtime contract, so the runtime and IR lowering need the
redesign described in [the refactor plan](docs/refactor-plan.md). [The LPython subset
notes](docs/lpython-subset.md) record the probe results and the area-by-area shape changes. CPython
3 source is an explicitly flagged fallback that requires user approval; it is not a silent
substitute. See also [the IR JSON boundary](docs/ir-json.md).

[![](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:mss5l446ynjlw6e67y6u5fsq/bafkreigi4fxmqpn2d7soi4d344tipzamivhwofnulhye4unjc3ljmlke5u)](https://bsky.app/profile/tonofcrates.bsky.social/post/3my3zodphxk2k)
