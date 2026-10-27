# Refactor plan: Lean frontend, Python target

## Decision

Lean stays in the pipeline, and the transpile target changes from JavaScript to Python.

- **Lean remains the frontend.** Lean elaborates the source, runs compile-time code, and collects
  the compiler IR from a `Lean.Environment`. The elaborator, IR collection, alias resolution, init
  order, and name handling are unchanged.
- **The backend emits Python.** A Python program reads the IR and emits `.py` source. Generated
  programs run on CPython against a Python runtime.
- **The runtime, target externs, and tests are Python.** The JavaScript runtime and the JavaScript
  test harness leave the pipeline.
- **JavaScript output is retired.** The Lean JS emitter stays only as a semantic reference until
  the Python emitter passes the fixture suite, then it is removed.

This is a target change, not a Lean-to-Python translation of the compiler. The compiler core stays
in Lean; the code generator and the target runtime are Python because the target is Python.

## Why Lean stays

The frontend and IR collection depend on Lean itself:

- `elabFile` runs `Lean.Elab.runFrontend`, so user code can use macros, `#eval`, and other
  compile-time evaluation.
- `collectReachable` walks `Lean.Environment` with `findEnvDecl`, `getExportNameFor?`, and
  `getInitFnNameFor?`.
- The collected IR is Lean's own compiler IR, including `Name`s whose mangling and display forms
  the emitter needs.

Reimplementing those pieces in Python would duplicate Lean's elaborator. The Python backend does
not need to: it consumes the IR that Lean produces.

## Non-goals

- Translating Lean's elaborator, IR collection, or `Environment` APIs to Python.
- Keeping JavaScript as an output target.
- Changing the IR that Lean collects beyond the target-neutral JSON boundary.
- Adding Lean language features during the migration.

## Target pipeline

Lean 4 source → Lean IR → JSON → Python emitter → `.py` → Python runtime.

| Stage | Language | Location | Responsibility |
| --- | --- | --- | --- |
| Frontend | Lean | `src/LeanScript/Frontend.lean` | Elaborate a source file and return its `Environment`. |
| IR collection | Lean | `src/LeanScript/Collect.lean` | Compute the declaration closure from `main`, `IO.Error.toString`, and `IO Unit` initializers; resolve exported aliases; record init functions and startup order. |
| Boundary | Lean | `src/LeanScript/DumpJson.lean`, `src/Main.lean` | Produce one JSON program for the Python emitter. |
| IR loading | Python | `leanscript/ir.py` | Decode and validate the JSON program; resolve the name table. |
| Call paths | Python | `leanscript/emit.py` | Walk the dumped IR to explain unavailable externs. |
| Target externs | Python | `leanscript/target.py`, `scripts/gen_target_externs.py` | List the externs that the Python runtime implements. |
| Python emission | Python | `leanscript/emit.py` | Emit `.py` source from the IR. |
| Python runtime | Python | `leanscript_runtime/` | Constructors, numbers, strings, references, IO, and the entry point for generated programs. |
| CLI | Python | `leanscript/cli.py`, `leanscript/__main__.py` | Compile to `.py`; keep the command, flags, diagnostics, and exit codes. |
| Tests | Python | `tests/run.py` | Compile fixtures to `.py`, run them with CPython, and compare their behavior. |

The Lean frontend and the JSON boundary are the only Lean parts of the production path. The
JavaScript emitter, the JavaScript runtime, and the JavaScript tooling are not part of the Python
target.

## What "Python target" changes

The IR is target-neutral. The existing JavaScript emitter and runtime are the semantic reference
for the new target, but the Python emitter is not a token-for-token translation of them. It must
produce valid Python syntax and use the Python runtime ABI:

- **Identifiers.** `names[].js` is the mangled identifier. Lean names mangle to `l_...`, which is
  valid in Python. The emitter's own temporaries use Python-safe names (`_rt`, `_Ctor`, `_ext`,
  `_inits`, `x_0`, `block_0`), not the JavaScript `$...` names.
- **Control flow.** Blocks become indentation. `case` lowers to `match` or `if`/`elif`. Join
  points and `jmp` need a Python lowering that preserves labeled-block semantics; a self tail call
  becomes a `while True` loop with parameter reassignment.
- **Constructors.** A runtime `Ctor` class holds the tag, object fields, and scalar fields.
- **Numbers.** Python integers are arbitrary precision. Fixed-width operations must apply the same
  wrapping rules as the IR types; `uint64` and `usize` need explicit handling.
- **Strings.** Lean strings are UTF-8 byte sequences. The runtime must preserve that behavior, such
  as byte length and indexing, even if generated code carries Python `str` values.
- **Ownership.** `inc`, `dec`, `del`, `reset`, `isShared`, and `reuse` become runtime calls. A first
  implementation may treat objects as always shared, so `reuse` allocates and the reference-count
  operations are no-ops. That preserves semantics; optimized reference counting can follow.
- **Startup.** Nullary declarations use the runtime's lazy cell or init cell. The `inits` list runs
  in order at startup, and `main` runs through `run_main` with `mainArity`.
- **Externs.** The runtime provides the names in the target extern table. An unavailable extern
  becomes a runtime function that raises the same diagnostic.
- **Unreachable.** `unreachable` raises the runtime's unreachable exception.

## Lean-side interfaces

The Lean executable is `leanscript-ir`; the user-facing command is `leanscript`.

`leanscript-ir` provides three commands:

| Command | Output |
| --- | --- |
| `leanscript-ir dump-json <file.lean> [-o <out.json>]` | One compressed JSON program, on standard output or in `out.json`. |
| `leanscript-ir dump-ir <file.lean>` | Pretty-printed IR for debugging. |
| `leanscript-ir list-externs <file.lean>` | Pretty-printed extern declarations for debugging. |

`dump-ir` and `list-externs` stay in Lean because they print Lean's `Format` values. They are
developer tools; the Python CLI may delegate to them.

The `dump-json` command is the production boundary. Its contract is in `docs/ir-json.md`. In short:

- Arguments are `dump-json <file.lean> [-o <out.json>]`.
- The module name comes from the file stem, as before.
- Without `-o`, standard output contains one JSON object followed by a newline, and nothing else.
  With `-o`, the JSON is written to that file and standard output stays empty. The file has no
  trailing newline.
- Failures print `error: <message>` on standard error and exit with status 1.
- The module is elaborated with the interpreter enabled, so user code may run at compile time.
- The Python CLI must invoke it without changing its working directory, because the frontend
  resolves the source path and, potentially, compile-time file access relative to it.
- The JSON schema is unchanged from the current version. `names[].js` carries the mangled
  identifier, and that value is valid as a Python identifier.

### What stays in Lean

- `elabFile` and the frontend.
- `collectReachable`, `collectBodyFns`, `collectExprFns`, and `initDecls`.
- `dumpIrDecls`.
- `DumpJson.programJson` and the name table.

### What the Python backend owns

- IR loading and validation.
- Call-path reporting for unavailable externs.
- Target extern tables and availability checks.
- The Python emitter.
- The Python runtime.
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
3. **Build the Python runtime skeleton.** Add `Ctor`, extern resolution, lazy and init cells,
   `run_main`, and the unreachable exception. It must run hand-written Python emitted from Hello.
4. **Write the Python emitter.** Emit `.py` for the fixtures, starting with Hello and expanding
   until every expression and body form is covered. The JavaScript emitter is the semantic
   reference, not a source template.
5. **Grow the runtime with the fixtures.** Add strings, arrays, fixed-width integers, reference
   counting, IO, file system, and process support. Generate the target extern table from the
   runtime.
6. **Replace the test harness.** `tests/run.py` compiles each fixture to `.py`, runs it with
   CPython, and compares stdout and exit codes. `--bless` still compiles and runs native Lean.
7. **Switch the build and CLI.** Update `pixi.toml`, `package.json`, `flake.nix`, and the README.
   The CLI compiles to `.py` by default and locates `leanscript-ir`.
8. **Retire the JavaScript path.** Remove the Lean JS emitter, the JavaScript runtime, and the
   JavaScript scripts after the Python suite passes.

## Contracts to preserve

- **Program behavior.** Standard output, exit codes, arguments, standard input, initializer order,
  and error text.
- **Command-line shape.** `compile`, `-o` (default `<input>.py`), `--runtime` (runtime import
  name), and `--allow-unavailable`. There is one target, Python; there is no `--target` flag.
  Error and warning text keeps the same wording.
- **Test semantics.** Each fixture runs in its own empty directory, with `.args` and `.stdin` if
  present; expected output comes from native Lean; `--bless` regenerates it with native Lean.
- **Diagnostics.** Errors and warnings keep the `error:` and `warning:` prefixes.
- **IR JSON.** Version 1; unchanged from the current schema.

The JavaScript output is not a compatibility target. The semantic baseline is the fixtures'
behavior on native Lean.

## Build and toolchain

`lean-toolchain` pins Lean 4.35.0, and `flake.nix` provides elan. Lake builds `leanscript-ir` from
`src/Main.lean`; `supportInterpreter` must stay enabled because user code can run at compile time.

The Python backend, runtime, and tests need a Python 3.11 or newer environment in `pixi.toml`. The
JavaScript tooling leaves the dev shell when the JavaScript path is retired.

`python -m leanscript` depends on a built `leanscript-ir`. The CLI should look for it in a fixed
order and report a clear error that names the missing executable and the build command when it
cannot find it.

## Open questions

The JSON boundary is versioned at 1. Any breaking change to the schema must bump the version, and
the Python loader rejects versions it does not know.

- How should the runtime represent strings: Python `str` with byte-oriented helpers, or a byte
  buffer? Lean string operations are UTF-8 based.
- How should the runtime handle reference counting? A conservative no-op implementation preserves
  semantics; an explicit count enables in-place reuse. What happens to the RC debug mode?
- How do generated `.py` files find `leanscript_runtime` outside the repository? Tests add the
  project root to `PYTHONPATH`; packaging for other users is still open.
