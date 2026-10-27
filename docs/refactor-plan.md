# Refactor plan: Lean frontend, LPython target

> **Target status.** The latest router correction names LPython, the LPython compiler, as the
> target. The runtime contract currently relies on classes with fields, exceptions, dicts,
> closures, and writable `os`/file APIs, which LPython 0.22's typed subset reportedly does not
> support. If that is confirmed, the target needs a different runtime and IR-lowering strategy, or
> it must return to CPython 3 source. Do not silently substitute one for the other; record the
> decision here.

## Decision

Lean stays in the pipeline, and the transpile target changes from JavaScript to LPython.

- **Lean remains the frontend.** Lean elaborates the source, runs compile-time code, and collects
  the compiler IR from a `Lean.Environment`. The elaborator, IR collection, alias resolution, init
  order, and name handling are unchanged.
- **The backend emits LPython source.** A Python program reads the IR and emits `.py` source for
  LPython. The target is LPython, the LPython compiler, not generic CPython.
- **The runtime and tests target LPython.** Generated programs import the `leanscript_runtime`
  package and are compiled and run by LPython. The test harness invokes the LPython toolchain.
- **JavaScript output is retired.** The Lean JS emitter stays only as a semantic reference until
  the LPython emitter passes the fixture suite, then it is removed.

This is a target change from JavaScript to LPython, not a translation of the compiler into
Python. The compiler core stays in Lean; the code generator and the target runtime are written for
LPython because LPython is the target. The backend is a compiler back end for LPython, not an
ad-hoc Python emitter.

## Why Lean stays

The frontend and IR collection depend on Lean itself:

- `elabFile` runs `Lean.Elab.runFrontend`, so user code can use macros, `#eval`, and other
  compile-time evaluation.
- `collectReachable` walks `Lean.Environment` with `findEnvDecl`, `getExportNameFor?`, and
  `getInitFnNameFor?`.
- The collected IR is Lean's own compiler IR, including `Name`s whose mangling and display forms
  the emitter needs.

Reimplementing those pieces in the backend would duplicate Lean's elaborator. The backend does not
need to: it consumes the IR that Lean produces.

## Non-goals

- Rewriting Lean's elaborator, IR collection, or `Environment` APIs in Python.
- Keeping JavaScript as an output target.
- Changing the IR that Lean collects beyond the target-neutral JSON boundary.
- Adding Lean language features during the migration.

## Target pipeline

Lean 4 source → Lean IR → JSON → LPython emitter → LPython source (`.py`) → LPython runtime.

| Stage | Language | Location | Responsibility |
| --- | --- | --- | --- |
| Frontend | Lean | `src/LeanScript/Frontend.lean` | Elaborate a source file and return its `Environment`. |
| IR collection | Lean | `src/LeanScript/Collect.lean` | Compute the declaration closure from `main`, `IO.Error.toString`, and `IO Unit` initializers; resolve exported aliases; record init functions and startup order. |
| Boundary | Lean | `src/LeanScript/DumpJson.lean`, `src/Main.lean` | Produce one JSON program for the LPython emitter. |
| IR loading | Python | `leanscript/ir.py` | Decode and validate the JSON program; resolve the name table. |
| Call paths | Python | `leanscript/emit.py` | Walk the dumped IR to explain unavailable externs. |
| Extern table | Python and LPython | `leanscript_runtime.externs` | A plain data module with the runtime's implemented externs. The emitter checks names against it; there is no generated extern file. |
| LPython emission | Python | `leanscript/emit.py` | Emit LPython source from the IR. |
| LPython runtime | LPython | `leanscript_runtime/` | Constructors, numbers, strings, references, IO, and the entry point, written in the Python subset that LPython supports. |
| CLI | Python | `leanscript/cli.py`, `leanscript/__main__.py` | Emit LPython source (default next to the input); delegate `dump-ir` and `list-externs` to `leanscript-ir`. |
| Tests | Python | `tests/run.py` | Compile fixtures to LPython source, compile and run them with LPython, and compare their behavior. |

The Lean frontend and the JSON boundary are the only Lean parts of the production path. The
JavaScript emitter, the JavaScript runtime, and the JavaScript tooling are not part of the LPython
target.

## What targeting LPython changes

The IR is target-neutral. The existing JavaScript emitter and runtime are the semantic reference
for the new target, but the LPython emitter is not a token-for-token translation of them. LPython
compiles a typed subset of Python, so the emitter and the runtime must stay inside that subset:

- **Source header.** Generated files start with `import leanscript_runtime as _rt`.
- **Subset.** Emitted code and the `leanscript_runtime` package must use only constructs that the
  pinned LPython version supports. The emitter and runtime plan must be checked against that
  version, not against CPython.
- **Identifiers.** `names[].js` is the mangled identifier. Lean names mangle to `l_...`, which is
  valid in LPython source. The emitter's own temporaries use names such as `_rt`, `_Ctor`, `_ext`,
  `_inits`, `x_0`, and `block_0`.
- **Types.** LPython is statically typed. The emitter must annotate functions and locals where
  LPython requires it, using the IR's types. The runtime's public functions need matching
  annotations. Dynamic Python types are not a substitute.
- **Control flow.** Blocks become indentation. `case` lowers to `if`/`elif` unless the pinned
  LPython version supports `match`. Join points and `jmp` need a lowering that uses only supported
  control flow; do not assume that `try`/`except` is available. A self tail call becomes a
  `while True` loop with parameter reassignment.
- **Constructors.** A runtime `Ctor` class holds the tag, object fields, and scalar fields. The
  class must be expressible in LPython.
- **Numbers.** LPython has fixed-width numeric types. Map the IR types to LPython types and preserve
  Lean's wrapping rules. Do not assume CPython's arbitrary-precision integers; large `Nat` and
  `Int` values need explicit runtime support or a documented limit.
- **Strings.** Lean strings are UTF-8 byte sequences. The runtime must preserve that behavior under
  LPython's string representation, including byte length and indexing.
- **Ownership.** LPython manages memory. `inc`, `dec`, and `del` may become no-ops if the semantics
  hold. `reset`, `isShared`, and `reuse` must still preserve exclusive-update semantics; a
  conservative `isShared` that always returns true makes `reuse` allocate and is correct, but it
  must be checked against the fixtures.
- **Startup.** Nullary declarations use the runtime's lazy cell or init cell. The `inits` list runs
  in order at startup, and `main` runs through `run_main` with `mainArity`.
- **Externs.** The emitter imports `leanscript_runtime.externs` directly. There is no generated
  extern file and no target selection. The module must be plain data that both the backend's Python
  and LPython can import. Without `--allow-unavailable`, a missing extern fails compilation; with
  it, the extern becomes a stub that raises the same diagnostic.
- **Errors.** `unreachable` and unavailable externs need an error path that LPython supports. If
  LPython's exception support is insufficient, use a runtime abort or error call with the same
  observable behavior.
- **Compilation model.** The generated `.py` is compiled by LPython ahead of time. It must not rely
  on CPython-only modules, dynamic imports, or runtime reflection.

This is the main new risk: the emitter and the runtime must be validated against the pinned
LPython compiler, not against CPython. A construct that works in CPython may be rejected by
LPython, and a type that CPython accepts may need an explicit LPython type.

### Known feasibility risk

The runtime contract uses classes with fields, exceptions, dicts, closures, and writable `os` and
file APIs. LPython 0.22's typed subset reportedly supports only default constructors in some
cases, no dataclasses, and no writable `os` or file APIs. The runtime threads report that the
current contract cannot compile under it.

There are two explicit options:

- **Keep LPython and restrict the runtime ABI.** The emitter, the runtime, and parts of the IR
  lowering would need a different design that stays inside LPython's subset. Some fixtures may be
  out of reach.
- **Return the target to CPython 3 source.** This is the implementation the runtime threads are
  building. It validates generated `.py` by running it under CPython.

The target decision must be made explicitly. The rest of this plan follows the latest router
correction, which names LPython; CPython is not a silent fallback.

## Lean-side interfaces

The Lean executable is `leanscript-ir`; the user-facing command is `leanscript`.

`leanscript-ir` provides three commands:

| Command | Output |
| --- | --- |
| `leanscript-ir dump-json <file.lean> [-o <out.json>]` | One compressed JSON program, on standard output or in `out.json`. |
| `leanscript-ir dump-ir <file.lean>` | Pretty-printed IR for debugging. |
| `leanscript-ir list-externs <file.lean>` | Pretty-printed extern declarations for debugging. |

`dump-ir` and `list-externs` stay in Lean because they print Lean's `Format` values. They are
developer tools; the `leanscript` CLI may delegate to them.

The `dump-json` command is the production boundary. Its contract is in `docs/ir-json.md`. In short:

- Arguments are `dump-json <file.lean> [-o <out.json>]`.
- The module name comes from the file stem, as before.
- Without `-o`, standard output contains one JSON object followed by a newline, and nothing else.
  With `-o`, the JSON is written to that file and standard output stays empty. The file has no
  trailing newline.
- Failures print `error: <message>` on standard error and exit with status 1.
- The module is elaborated with the interpreter enabled, so user code may run at compile time.
- The `leanscript` CLI must invoke it without changing its working directory, because the frontend
  resolves the source path and, potentially, compile-time file access relative to it.
- The JSON schema is unchanged from the current version. `names[].js` carries the mangled
  identifier, and that value is valid in LPython source.

### What stays in Lean

- `elabFile` and the frontend.
- `collectReachable`, `collectBodyFns`, `collectExprFns`, and `initDecls`.
- `dumpIrDecls`.
- `DumpJson.programJson` and the name table.

### What the backend owns

- IR loading and validation.
- Call-path reporting for unavailable externs.
- Extern availability checks against `leanscript_runtime.externs`.
- The LPython emitter.
- The LPython runtime package.
- The user-facing CLI and the test harness.

### What is retired

- `EmitJs.lean`, `Target.lean`, and `TargetExterns.lean`.
- The JavaScript runtime under `src/runtime` and its platform hosts.
- `tests/run.js` and `scripts/gen-target-externs.js`.

Retiring the JavaScript emitter does not remove Lean from the pipeline. The frontend, IR
collection, JSON dumper, and `leanscript-ir` remain, and every compile starts with Lean.

## Migration phases

1. **Freeze the semantic baseline.** Keep the 22 fixtures' `.expected`, `.exitcode`, `.args`, and
   `.stdin` files, which come from native Lean. Confirm that the current JavaScript path passes.
   (Done.)
2. **Finish the IR boundary.** Keep `dump-json` with `-o` and schema version 1; keep
   `names[].js` as the mangled identifier; build with Lake.
3. **Pin LPython and build the runtime skeleton.** Add the LPython compiler to the environment and
   record its supported subset. Add `Ctor`, extern resolution, lazy and init cells, `run_main`,
   and an error path. Compile and run a hand-written Hello module with LPython.
4. **Write the LPython emitter.** Emit LPython source for the fixtures, starting with Hello and
   expanding until every expression and body form is covered. The JavaScript emitter is the
   semantic reference, not a source template.
5. **Grow the runtime with the fixtures.** Add strings, arrays, fixed-width integers, ownership
   operations, IO, file system, and process support. Keep every module inside the LPython subset.
   Wire the emitter's extern checks to `leanscript_runtime.externs`.
6. **Replace the test harness.** `tests/run.py` compiles each fixture to LPython source, invokes
   the pinned LPython toolchain, runs the result, and compares stdout and exit codes. `--bless`
   still compiles and runs native Lean.
7. **Switch the build and CLI.** Update `pixi.toml`, `package.json`, `flake.nix`, and the README.
   Pin the LPython compiler. The CLI writes `<input>.py` next to the input by default and locates
   `leanscript-ir`.
8. **Retire the JavaScript path.** Remove the Lean JS emitter, the JavaScript runtime, and the
   JavaScript scripts after the LPython suite passes.

## Contracts to preserve

- **Program behavior.** Standard output, exit codes, arguments, standard input, initializer order,
  and error text.
- **Command-line shape.** `compile`, `-o` (default `<input>.py` next to the input), and
  `--allow-unavailable`. There is one target, LPython; there is no `--target` or `--runtime` flag.
  `dump-ir` and `list-externs` delegate to `leanscript-ir`. Error and warning text keeps the same
  wording.
- **Test semantics.** Each fixture runs in its own empty directory, with `.args` and `.stdin` if
  present; expected output comes from native Lean; `--bless` regenerates it with native Lean.
  Generated source is compiled and run by LPython, and the test harness makes
  `leanscript_runtime` visible to LPython.
- **LPython subset.** Emitted source and the runtime use only constructs supported by the pinned
  LPython version.
- **Diagnostics.** Errors and warnings keep the `error:` and `warning:` prefixes.
- **IR JSON.** Version 1; unchanged from the current schema.

The JavaScript output is not a compatibility target. The semantic baseline is the fixtures'
behavior on native Lean.

## Build and toolchain

`lean-toolchain` pins Lean 4.35.0, and `flake.nix` provides elan. Lake builds `leanscript-ir` from
`src/Main.lean`; `supportInterpreter` must stay enabled because user code can run at compile time.

The backend and test harness run on Python; that is the implementation language, not the target.
They need a Python environment in `pixi.toml`. The LPython compiler is a separate pinned
dependency; add it to `pixi.toml` or the flake and record its version and supported Python subset.
The `leanscript_runtime` package and generated code are compiled by LPython.

`python -m leanscript` depends on a built `leanscript-ir`. The CLI should look for it in a fixed
order and report a clear error that names the missing executable and the build command when it
cannot find it.

## Open questions

The JSON boundary is versioned at 1. Any breaking change to the schema must bump the version, and
the Python loader rejects versions it does not know.

- Which Python subset does the pinned LPython version support: `match`, exceptions, classes,
  dynamically sized arrays, string methods, and `sys` access?
- How does LPython import `leanscript_runtime`? Does it compile the package from source, and what
  module search path does it use?
- Can `leanscript_runtime.externs` stay a plain data module that both the backend's Python and
  LPython can import? If not, the no-generated-extern-file rule needs revisiting.
- How should the runtime map Lean `Nat`, `Int`, `uint64`, and `usize` to LPython's fixed-width
  types? Is big-integer support needed?
- How should the runtime represent strings: LPython `str` with byte-oriented helpers, or a byte
  buffer? Lean string operations are UTF-8 based.
- Does LPython expose enough of its memory model to implement `isShared`, or should the emitter
  treat objects as always shared? What happens to the reference-count debug mode?
- Does LPython support the error path needed for `unreachable` and unavailable externs?
