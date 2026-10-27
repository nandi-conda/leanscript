# leanscript
Lean to JavaScript

leanscript compiles Lean 4 programs to JavaScript. Lean stays in the pipeline: the Lean frontend
elaborates the source and collects the compiler IR, and a backend turns that IR into JavaScript.
The backend is being ported from Lean to Python; see [the refactor plan](docs/refactor-plan.md) and
[the IR JSON boundary](docs/ir-json.md).

[![](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:mss5l446ynjlw6e67y6u5fsq/bafkreigi4fxmqpn2d7soi4d344tipzamivhwofnulhye4unjc3ljmlke5u)](https://bsky.app/profile/tonofcrates.bsky.social/post/3my3zodphxk2k)
