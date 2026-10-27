# leanscript
Lean to LPython

leanscript compiles Lean 4 programs to LPython source. Lean stays in the frontend: it elaborates
the input and collects the compiler IR, and a Python backend emits LPython source (`.py`) that
imports `leanscript_runtime`. LPython is the target compiler, not CPython; it compiles the
generated source. The JavaScript emitter, runtime, and tests are being retired in favor of the
LPython target.

See [the refactor plan](docs/refactor-plan.md) and [the IR JSON boundary](docs/ir-json.md).

[![](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:mss5l446ynjlw6e67y6u5fsq/bafkreigi4fxmqpn2d7soi4d344tipzamivhwofnulhye4unjc3ljmlke5u)](https://bsky.app/profile/tonofcrates.bsky.social/post/3my3zodphxk2k)
