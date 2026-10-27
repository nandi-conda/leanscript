# Refactor plan: Python backend with a Lean frontend

## Decision

Lean stays in the pipeline. leanscript still compiles Lean 4 programs to JavaScript:

- **Lean remains the source language and the frontend.** Lean elaborates the input, runs
  compile-time code, and collects the compiler IR from a `Lean.Environment`.
- **Python implements everything after IR collection.** This covers call-path reporting, target
  extern checks, JavaScript emission, the user-facing command-line interface, tests, and generation
  scripts.
- **The output language stays JavaScript.** Here, "transpiling Lean 4 to Python" means that the
  transpiler's downstream is written in Python. It does not mean that Python replaces JavaScript
  as the output.

This is a port of the compiler's implementation, not a port of Lean. There is no Python parser,
elaborator, or `Environment` equivalent, and this plan does not replace Lean's frontend with
Python. There is also no Python-only mode: every compile invokes `leanscript-ir` to elaborate the
source.

## Why Lean stays

The frontend and IR collection depend on Lean itself:

- `elabFile` runs `Lean.Elab.runFrontend`, so user code can use macros, `#eval`, and other
  compile-time evaluation.
- `collectReachable` walks `Lean.Environment` with `findEnvDecl`, `getExportNameFor?`, and
  `getInitFnNameFor?`.
- The collected IR is Lean's own compiler IR, including `Name`s whose `mangle` and display forms
  the emitter needs.

Reimplementing those pieces in Python would be a compiler rewrite. The downstream stages are data
and string processing, which Python handles well.

## Non-goals

- A Python parser, elaborator, or `.olean` reader for Lean.
- Changing the emitted language from JavaScript to Python.
- Changing the JavaScript runtime or the generated program ABI.
- Adding compiler features during the port.

## Target pipeline

| Stage | Language | Location | Responsibility |
| --- | --- | --- | --- |
| Frontend | Lean | `src/LeanScript/Frontend.lean` | Elaborate a source file and return its `Environment`. |
| IR collection | Lean | `src/LeanScript/Collect.lean` | Compute the declaration closure from `main`, `IO.Error.toString`, and `IO Unit` initializers; resolve exported aliases; record init functions and startup order. |
| Boundary | Lean | `src/LeanScript/DumpJson.lean`, `src/Main.lean` | Produce one JSON program for the Python backend. |
| IR loading | Python | `leanscript/ir.py` | Decode and validate the JSON program; resolve the name table. |
| Call paths | Python | `leanscript/emit.py` | Port `Program.callPath` and the call-graph walk that explains unavailable externs. |
| Target externs | Python | `leanscript/target.py`, `scripts/gen_target_externs.py` | Derive the extern set of each target from the JavaScript runtime. |
| JS emission | Python | `leanscript/emit.py` | Port `EmitJs.lean` and produce the `.mjs` output. |
| CLI | Python | `leanscript/cli.py`, `leanscript/__main__.py` | Keep `compile`, its flags, diagnostics, and exit codes; call `leanscript-ir dump-json -o`. |
| Tooling | Python | `tests/run.py`, `scripts/gen_target_externs.py` | Replace `tests/run.js` and `scripts/gen-target-externs.js`. |

The runtime under `src/runtime` stays JavaScript. The generated programs and the runtime are not
rewritten.

## Lean-side interfaces

The Lean executable is renamed from `leanscript` to `leanscript-ir`, so the name `leanscript`
belongs to the user-facing Python CLI.

`leanscript-ir` provides three commands:

| Command | Output |
| --- | --- |
| `leanscript-ir dump-json <file.lean> [-o <out.json>]` | One compressed JSON program, on standard output or in `out.json`. |
| `leanscript-ir dump-ir <file.lean>` | Pretty-printed IR for debugging. |
| `leanscript-ir list-externs <file.lean>` | Pretty-printed extern declarations for debugging. |

`dump-ir` and `list-externs` stay in Lean because they print Lean's `Format` values. They are
developer tools; the Python CLI may delegate to them but does not need to reimplement them.

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

The JSON schema is shared by `DumpJson.lean` and `leanscript/ir.py`. A change on either side
requires the same change on the other, and the fixture suite verifies the round trip.

### What stays in Lean

- `elabFile` and the frontend.
- `collectReachable`, `collectBodyFns`, `collectExprFns`, and `initDecls`.
- `dumpIrDecls`.
- `DumpJson.programJson` and the name table.

### What moves to Python

- `emitProgram`, `EmitOptions`, `EmitOutput`, and all of `EmitJs.lean`.
- `Program.callPath`, with Python's own call-graph walk over the dumped IR.
- `Target`, `Target.externs`, `nodeExterns`, and `browserExterns`.
- `CompileArgs`, `parseCompileArgs`, `compile`, and `describeUnavailable` from `Main.lean`.
- `tests/run.js` and `scripts/gen-target-externs.js`.

Declaration closure stays in Lean. Only the *call-path* walk moves to Python. These are different
algorithms: closure needs `Lean.Environment`, while call paths only need the collected declarations
and aliases.

## Phases

1. **Freeze the baseline.** Build the current Lean compiler, run all 22 fixtures for both targets,
   and save the emitted `.mjs` files and their hash. (Done.)
2. **Add the JSON boundary.** Add `DumpJson.lean` and `leanscript-ir dump-json`; build with Lake;
   check that every IR variant is serialized.
3. **Load IR in Python.** Add `leanscript/ir.py` and validate it against the fixtures. Compare
   reconstructed names, declaration order, aliases, and init order with `dump-ir`.
4. **Port call paths and target externs.** Reproduce `Program.callPath` and the target extern sets;
   check every unavailable-extern message and browser compile error.
5. **Port the emitter.** Port `EmitJs.lean` verbatim in structure. Compare every fixture's `.mjs`
   byte for byte with the saved baseline.
6. **Port the CLI and tooling.** Keep the command name, flags, messages, and exit codes. Move
   `tests/run.js` and the extern generator to Python.
7. **Switch the build.** Update `pixi.toml` tasks, `package.json` scripts, `flake.nix`, the README,
   and this plan. Make the Python CLI build or locate `leanscript-ir`.
8. **Remove the old backend.** Delete the Lean emitter, target tables, call-path code, and the
   JavaScript tooling only after the fixture suite passes on the new path. Run the suite again
   afterwards.

Deleting `EmitJs.lean`, `Target.lean`, and `TargetExterns.lean` does not remove Lean from the
pipeline. It removes the backend that Python replaces; `Frontend.lean`, `Collect.lean`,
`DumpJson.lean`, and `leanscript-ir` remain.

## Contracts to preserve

- **Command-line behavior.** `compile`, `-o`, `--runtime`, `--target`, and `--allow-unavailable`
  keep their names and meanings. Error and warning text stays the same.
- **Exit codes.** A missing `main`, a noncomputable declaration, or an unavailable extern without
  `--allow-unavailable` exits with status 1. Successful compilation exits with 0.
- **Emitted JavaScript.** During the port, output must be byte-identical to the baseline. After the
  port, changes to formatting are allowed only if the fixture programs still produce the same
  stdout and exit codes.
- **Test semantics.** Each fixture runs in its own empty directory, with `.args` and `.stdin` if
  present; reference counting checks are on; the browser variant runs under the `browser` export
  condition; `--bless` still compiles the native executable.
- **Runtime resolution.** The default import specifier remains `leanscript/runtime`.

## Build and toolchain

`lean-toolchain` pins Lean 4.35.0, and `flake.nix` provides elan, Node, and pnpm. Lake builds
`leanscript-ir` from `src/Main.lean`; `supportInterpreter` must stay enabled because user code can
run at compile time. The Python backend uses the standard library only and needs a Python
environment in `pixi.toml`.

`python -m leanscript` depends on a built `leanscript-ir`. The CLI should look for it in a fixed
order and report a clear error that names the missing executable and the build command when it
cannot find it.

## Open questions

The JSON boundary is versioned at 1. Any breaking change to the schema must bump the version, and
the Python loader rejects versions it does not know.

- Where does the Python CLI look for `leanscript-ir`? The candidates are an environment variable,
  `PATH`, and `.lake/build/bin/leanscript-ir` relative to the package root.
- Does the Python CLI expose `dump-ir` and `list-externs` by delegating to `leanscript-ir`, or are
  those commands Lean-only developer tools?
