# leanscript
Lean to Python

leanscript compiles Lean 4 programs to Python. Lean stays in the frontend: it elaborates the input
and collects the compiler IR, and a Python backend emits `.py` against a Python runtime. The
JavaScript emitter, runtime, and tests are being retired in favor of the Python target.

See [the refactor plan](docs/refactor-plan.md) and [the IR JSON boundary](docs/ir-json.md).

[![](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:mss5l446ynjlw6e67y6u5fsq/bafkreigi4fxmqpn2d7soi4d344tipzamivhwofnulhye4unjc3ljmlke5u)](https://bsky.app/profile/tonofcrates.bsky.social/post/3my3zodphxk2k)
