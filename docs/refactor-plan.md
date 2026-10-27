# Refactor plan: Lean frontend, CPython 3 target

> **Decision: CPython 3 is the target. LPython 0.22.0 is rejected.** 21 of 32 compiler probes fail,
> including every probe for dynamic values, exceptions, closures, byte arrays, and file or standard
> IO. The probe matrix, the exact diagnostics, and the probe sources are in
> [`docs/lpython-subset.md`](lpython-subset.md). The probes are in `tests/lpython/probes/`, and
> `pixi run python tests/lpython/run_probes.py` reproduces the matrix.
>
> There is no LPython redesign. The runtime modules and the generated programs run on CPython 3.11
> or newer. The Lean frontend, the IR JSON boundary, the emitter, the CLI, and the test harness are
> host tools and are unaffected by the compiler choice.

## Decision

Lean stays in the pipeline. The transpile target is CPython 3. LPython 0.22.0 is rejected.

- **Lean remains the frontend.** Lean elaborates the source, runs compile-time code, and collects
  the compiler IR from a `Lean.Environment`. The elaborator, IR collection, alias resolution, init
  order, and name handling are unchanged.
- **The backend emits CPython 3 source.** A Python program reads the IR and emits `.py` source for
  CPython 3.11 or newer. The emitter does not annotate types for a static compiler.
- **The runtime and tests target CPython 3.** Generated programs import the `leanscript_runtime`
  package and run under CPython. The test harness runs generated source with the interpreter.
- **LPython 0.22.0 is evidence only.** It stays pinned so the probe matrix is reproducible. It is
  not a build target, a test target, or a dependency of generated programs.
- **JavaScript output is retired.** The Lean JS emitter and the JavaScript runtime are no longer in
  the repository. The native-Lean fixtures are the semantic reference.

### Why LPython 0.22.0 is rejected

The compiler accepts a statically typed leaf-program subset, not a dynamic language runtime:

1. **The IR value model is dynamic.** A value is a tagged constructor whose fields mix strings,
   integers, floats, closures, arrays, and other constructors. LPython has no `Any`, no union
   type, and no heterogeneous container. A `list` of structs crashes the compiler with `SIGSEGV`,
   and a recursive struct field is rejected.
2. **The runtime objects are heap objects with methods.** LPython accepts annotated fields and the
   generated default constructor, but rejects an explicit `__init__` and rejects methods. It also
   crashes when a class instance is returned from a function or stored in a list, rejects
   class-typed fields, and rejects mutation through a parameter.
3. **The runtime uses closures and first-class functions.** LPython rejects nested functions and
   `lambda`, and has no callable type.
4. **The error paths use exceptions.** `try`/`except` is an internal compiler error.
5. **Strings and byte arrays are UTF-8 bytes.** LPython has no `bytes` or `bytearray`, no
   `encode`/`decode`, and its `str` has byte semantics that do not preserve Lean's API.
6. **IO is essential.** LPython has no writable files, no stdin, no `sys.stderr.write`, and no
   `os` environment, current-directory, or file APIs. Only `print` and `sys.argv` work.
7. **Lean integers are unbounded.** LPython has only `i8` through `i64`. Fixtures print `30!`,
   `2^100`, `10^20`, and `fib(200)`, so the runtime needs a bignum layer.

The passing probes are real capabilities, but they describe a different program shape, not a
runtime port. Details and per-construct evidence are in `docs/lpython-subset.md`.

## Scope

### Component scope

LPython can accept source only where the runtime or generated code is its input. The frontend, the
IR JSON, the emitter, the CLI, and the harness are host tools; they were never inside the LPython
subset and need no LPython-specific variant.

| Component | Compiled by LPython? | Scope decision | Reason |
| --- | --- | --- | --- |
| Lean frontend (`src/LeanScript/`, `src/Main.lean`) | No | Keep in Lean 4. | Lean elaborates the input and collects the IR. LPython never sees it. |
| IR JSON schema v1 (`docs/ir-json.md`) | No | Keep version 1 unchanged. | JSON is data at the boundary. The decision changes the consumer, not the schema. |
| Runtime (`leanscript_runtime/`) | Yes | CPython 3 only. | Uses classes with methods, closures, exceptions, `bytearray`/`bytes`, file and `os` APIs, and dynamic values. See the matrix. |
| Emitter (`leanscript/emit.py`) | No | Keep on CPython 3; emit CPython 3 source. | Host tool. The LPython annotation, dispatch, and subset rules are withdrawn. |
| CLI (`leanscript/cli.py`, `leanscript/__main__.py`) | No | Keep on CPython 3. | Host tool; it writes generated `.py` next to the input. |
| Tests (`tests/run.py`, `tests/ir_json.py`) | No | Keep on CPython 3; CPython is the only runner. | The harness runs generated programs and compares behavior. |
| Generated programs | Yes | CPython 3 only. | They consume dynamic IR values and need exceptions, closures, strings, arrays, and IO. |
| Probe matrix (`tests/lpython/`) | Yes | Keep as evidence, not as a target. | Reproduces the rejection. It is not part of `pixi run test`. |

### Construct scope

| Construct | Needed by | LPython 0.22 | Consequence |
| --- | --- | --- | --- |
| Dynamic values: `Any`, unions, heterogeneous containers | `Ctor`, every IR value | Rejected. | There is no value representation. |
| `list` of structs, recursive struct fields | Any value graph or heap | Rejected; `list[Cell]` crashes with `SIGSEGV`. | Values cannot be collected into a heap. |
| Classes: annotated fields, default constructor, free functions | Typed leaf structs | Accepted. | Useful for a leaf program, not for the runtime's objects. |
| Classes: explicit `__init__`, methods | `Ctor`, `Closure`, `Ref`, `Thunk`, `LeanString`, `LeanArray` | Rejected. | No heap object with behavior. |
| Closures, nested functions, function values | `Closure`, `pap`, `apply`, the extern table | Rejected. | No callable values or dynamic dispatch. |
| `try`/`except` | `ExitCode`, `UncaughtError`, `InitializeError` | Rejected; internal compiler error. | Only `assert` and `sys.exit` abort paths remain. |
| Comprehensions | Runtime helpers and emitter output | Rejected; internal compiler error. | Workaround is a loop; it adds no capability. |
| `bytes`, `bytearray`, `encode`, `decode` | `LeanString`, `ByteArray` | Rejected. | No byte model and no text/byte conversion. |
| `str` with ASCII operations | `LeanString` | Partial: ASCII works; `str` is UTF-8 bytes; `\u` escapes are not decoded. | No Unicode case mapping or character indexing, and no byte-offset API. |
| Writable files, stdin, stderr, `os`, environment, current directory | IO runtime, CLI, `Cli`, `WordFrequency` | Rejected. | File and interactive fixtures cannot run. |
| `print`, `sys.argv`, `sys.exit`, `assert` | Startup, diagnostics | Accepted. | Exit codes work; `sys.exit` adds `STOP n` on stderr. |
| 1,000-deep non-tail recursion | `ExprParser`, runtime dispatch | Accepted. | Recursion alone is not a blocker. |
| Bare `int`, arbitrary-precision `Nat`/`Int` | `Nat`, `Int`, `Loops`, `NumberCrunching`, `Caching`, `Builtins`, `ExprParser` | Rejected; only fixed-width types such as `i32` and `i64` work. | Lean's unbounded integers need a bignum layer. Fixtures print `30!`, `2^100`, `10^20`, and `fib(200)`. |

### What runs on CPython 3

- Every `leanscript_runtime` module, including `Ctor`, `Closure`, `Ref`, `Thunk`, `LeanString`,
  `LeanArray`, `ByteArray`, and the extern table.
- Every generated program.
- Every fixture, including `Cli`, `WordFrequency`, `ExitCode`, `UncaughtError`, and `ExprParser`.
- The test harness, the CLI, the IR loader, and the emitter.

The CPython target keeps the current runtime contract. The retired JavaScript runtime established
it, and the native-Lean fixtures pin it.

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

- Targeting LPython or any other statically typed Python subset.
- Rewriting Lean's elaborator, IR collection, or `Environment` APIs in Python.
- Keeping JavaScript as an output target.
- Changing the IR that Lean collects beyond the target-neutral JSON boundary.
- Adding Lean language features during the migration.

## Target pipeline

Lean 4 source → Lean IR → JSON → CPython emitter → CPython 3 source (`.py`) → CPython runtime.

| Stage | Language | Location | Responsibility |
| --- | --- | --- | --- |
| Frontend | Lean | `src/LeanScript/Frontend.lean` | Elaborate a source file and return its `Environment`. |
| IR collection | Lean | `src/LeanScript/Collect.lean` | Compute the declaration closure from `main`, `IO.Error.toString`, and `IO Unit` initializers; resolve exported aliases; record init functions and startup order. |
| Boundary | Lean | `src/LeanScript/DumpJson.lean`, `src/Main.lean` | Produce one JSON program for the backend. |
| IR loading | Python | `leanscript/ir.py` | Decode and validate the JSON program; resolve the name table. |
| Call paths | Python | `leanscript/emit.py` | Walk the dumped IR to explain unavailable externs. |
| Extern table | Python | `leanscript_runtime.externs` | The runtime's extern names and implementations, keyed by Lean name. |
| CPython emission | Python | `leanscript/emit.py` | Emit CPython 3 source from the IR. |
| CPython runtime | Python | `leanscript_runtime/` | Constructors, numbers, strings, references, IO, and the entry point. |
| CLI | Python | `leanscript/cli.py`, `leanscript/__main__.py` | Emit CPython 3 source (default next to the input); delegate `dump-ir` and `list-externs` to `leanscript-ir`. |
| Tests | Python | `tests/run.py` | Run generated source with CPython and compare its behavior. |

The Lean frontend and the JSON boundary are the only Lean parts of the production path. The
JavaScript emitter, runtime, and tooling are retired and are not part of the target.

## What targeting CPython 3 changes

The IR is target-neutral. The retired JavaScript emitter and runtime were the semantic reference
for the backend; they are no longer in the repository. The fixtures are the behavioral baseline.
CPython 3 is a dynamic language, so the emitter and the runtime keep the shapes that the IR
expects:

- **Source header.** The first statement in a generated file is `import leanscript_runtime as
  _rt`. A leading `# Generated by LeanScript.` comment is allowed.
- **Types.** No annotations are required. The emitter uses the IR's types to choose lowering and
  runtime calls, not to satisfy a static checker.
- **Identifiers.** `names[].js` is the mangled identifier. Lean names mangle to `l_...`, which is
  valid in CPython source. The emitter's own temporaries use names such as `_rt`, `_Ctor`, `_ext`,
  `_inits`, `x_0`, and `block_0`.
- **Control flow.** Blocks become indentation. `case` lowers to `if`/`elif`. A body with join
  points becomes numbered blocks selected by a `_pc` dispatch loop. A self tail call becomes a
  `while True` loop with parameter reassignment.
- **Constructors.** `Ctor` is a class with an `rc` field, a `tag`, an object-field vector `f`, and
  a scalar dictionary `s`. `inc`, `dec`, `reset`, `reuse`, and `isShared` operate on it.
- **Numbers.** Python integers are arbitrary precision, which matches Lean's `Nat` and `Int`.
  Fixed-width operations keep Lean's wrapping rules in `leanscript_runtime.fixed`.
- **Strings.** `LeanString` stores the UTF-8 bytes in a growable `bytearray`; the Python text and
  the scalar count are cached. Byte offsets index the exact bytes, including invalid UTF-8.
- **Ownership.** The `rc` field is real. `inc`, `dec`, `del`, `reset`, `isShared`, and `reuse`
  implement the reference-counting contract. Python reclaims memory; the counts decide exclusivity.
- **Startup.** Nullary declarations use the runtime's lazy cell or init cell. The `inits` list runs
  in order at startup. `run_main(inits, main, arity, error_to_string)` takes callables.
- **Externs.** The runtime exposes `externs` as a dict of callables keyed by Lean name. The emitter
  checks availability at emission time. Without `--allow-unavailable`, a missing extern fails
  compilation; with it, the extern becomes a stub on the runtime's abort path.
- **Errors.** `unreachable`, unavailable externs, and panic paths raise runtime errors with the
  `LeanScript: ` prefix. `ExitCode` uses `sys.exit`.
- **IO.** The runtime uses `sys.stdout`, `sys.stderr`, `sys.stdin`, `open`, `os`, and the platform
  host modules. The CLI, file-system fixtures, and process fixtures use the same contract.
- **Compilation model.** Generated `.py` is run by CPython. The harness puts the repository root on
  `PYTHONPATH` so `leanscript_runtime` resolves to the in-tree package.

The LPython-specific redesign, including typed cells, tag dispatch with `if` chains, finite extern
dispatch, and `assert`-based aborts, is withdrawn. Do not reintroduce it.

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
- The `leanscript` CLI runs `leanscript-ir` from the project root and passes an absolute input
  path, so compile-time file access resolves relative to the project root and elan-based setups
  find the pinned toolchain.
- The JSON schema is unchanged from version 1. `names[].js` carries the mangled identifier, and
  that value is valid in CPython source.

### What stays in Lean

- `elabFile` and the frontend.
- `collectReachable`, `collectBodyFns`, `collectExprFns`, and `initDecls`.
- `dumpIrDecls`.
- `DumpJson.programJson` and the name table.

### What the backend owns

- IR loading and validation.
- Call-path reporting for unavailable externs.
- Extern availability checks against the runtime's extern names.
- The CPython emitter.
- The CPython runtime package.
- The user-facing CLI and the test harness.

### What is retired

- `EmitJs.lean`, `Target.lean`, and `TargetExterns.lean`.
- The JavaScript runtime under `src/runtime` and its platform hosts.
- `package.json`, `pnpm-lock.yaml`, the Prettier and oxlint configs, `tests/run.js`,
  `scripts/gen-target-externs.js`, and all `*.browser-error` fixtures.

The JavaScript path is retired. This does not remove Lean from the pipeline. The frontend, IR
collection, JSON dumper, and `leanscript-ir` remain, and every compile starts with Lean.

## Migration phases

0. **Record the target decision.** CPython 3 is the target. LPython 0.22.0 is rejected with the
   probe matrix in `docs/lpython-subset.md`. (Done.)
1. **Freeze the semantic baseline.** Keep the 22 fixtures' `.expected`, `.exitcode`, `.args`, and
   `.stdin` files, which come from native Lean. Confirm that the current path passes. (Done.)
2. **Finish the IR boundary.** Keep `dump-json` with `-o` and schema version 1; keep `names[].js`
   as the mangled identifier; build with Lake. This phase is target-independent. (Done.)
3. **Land the CPython runtime.** Complete `leanscript_runtime`: `core`, `nat`, `fixed`, `float`,
   `string`, `array`, `bytearray`, `misc`, `hash`, `io`, `stream`, `platform`, and `ref`. The
   runtime contract is the current JavaScript-equivalent one; no LPython subset rules apply.
   (Done.)
4. **Finish the CPython emitter.** Emit CPython 3 source for every expression and body form, and
   check extern availability at emission time. The retired JavaScript emitter was the semantic
   reference; the fixtures are the source of truth. (Done.)
5. **Switch the test harness to CPython.** CPython is the only runner. The LPython branch,
   `LEANSCRIPT_TEST_RUNNER`, and `.unsupported-lpython` handling are removed, and the `Cli` sidecar
   is deleted. `tests/lpython/` and the pinned LPython dependency remain only for probe evidence.
   (Done.)
6. **Switch the build and CLI.** Update `pixi.toml`, `flake.nix`, and the README. The CLI writes
   `<input>.py` next to the input by default and locates `leanscript-ir`. (Done.)
7. **Retire the JavaScript path.** The Lean JS emitter, the JavaScript runtime, `package.json`,
   `pnpm-lock.yaml`, the JavaScript configs, and the JavaScript scripts are removed. (Done.)
8. **Keep the rejection reproducible.** Keep `tests/lpython/probes/` and
   `tests/lpython/run_probes.py`. They are evidence, not a target, and they are not part of
   `pixi run test`.

## Test harness status

`tests/run.py` compiles every fixture with `python -m leanscript compile` and runs the generated
source with CPython, with the repository root on `PYTHONPATH`. CPython is the only runner. The
LPython branch, the `LEANSCRIPT_TEST_RUNNER` switch, and the `.unsupported-lpython` handling are
gone; the `Cli` sidecar is deleted. `tests/lpython/` and the pinned LPython dependency remain only
for `run_probes.py` evidence and are not part of `pixi run test`.

`tests/ir_json.py` checks `dump-json` directly: version 1, top-level shape, name-index ranges,
`main` and `errorToString` inside `decls`, and the `-o` file contract. `.expected` and `.exitcode`
remain native-Lean output and stay the semantic baseline.

Verified after building `leanscript-ir` from Lean 4.35.0:

- The fixture suite is 22/22 on CPython.
- `tests/ir_json.py` passes against the real dumper.
- `Cli` passes; `run_main` catches the worker thread's `SystemExit` and exits with its status.
- `InPlace` passes within the 300s timeout.

Remaining gaps:

- `Cli.browser-error` is deleted. There is no negative test for `--allow-unavailable` until the
  single-target missing-extern wording is pinned. A fixture using `@[extern "..."]` is the stable
  candidate.
- Reference-count leak checking is gone with `LEANSCRIPT_DEBUG_RC`. The runtime owns the counts;
  reinstate a debug mode only if a fixture needs it.
- The `LeanScript: ` stderr prefix is pinned as the runtime's internal error marker.
- `ExprParser` has 1,000-deep non-tail recursion. CPython's default recursion limit is too low;
  the runtime raises it in `core.run_main` (`sys.setrecursionlimit`). Keep that behavior and test
  it under CPython.

## Contracts to preserve

- **Target.** CPython 3.11 or newer. Generated source is ordinary CPython 3 source. LPython is not
  a target.
- **Program behavior.** Standard output, exit codes, arguments, standard input, initializer order,
  and error text.
- **Command-line shape.** `compile`, `-o` (default `<input>.py` next to the input), and
  `--allow-unavailable`. There is one target, CPython; there is no `--target` or `--runtime` flag.
  `dump-ir` and `list-externs` delegate to `leanscript-ir`. Error and warning text keeps the same
  wording.
- **Test semantics.** Each fixture runs in its own empty directory, with `.args` and `.stdin` if
  present; expected output comes from native Lean; `--bless` regenerates it with native Lean.
  Generated source runs under CPython, and the harness puts `leanscript_runtime` on `PYTHONPATH`.
- **Diagnostics.** Compiler errors and warnings keep the `error:` and `warning:` prefixes.
  Runtime internal errors keep the `LeanScript: ` prefix on stderr.
- **IR JSON.** Version 1; unchanged from the current schema.

The JavaScript output is not a compatibility target. The semantic baseline is the fixtures'
behavior on native Lean.

## Build and toolchain

`lean-toolchain` pins Lean 4.35.0 for elan-based setups. `flake.nix` provides elan and Python 3;
Node and pnpm are no longer part of the dev shell. Lake builds `leanscript-ir` from `src/Main.lean`;
`supportInterpreter` must stay enabled because user code can run at compile time.

`pixi run build` runs `lake build` with Lean 4.33.0, the newest version that conda-forge provides.
`pixi run test` runs the build first and then the fixtures. Conda-forge has no Lean 4.35.0, so use
the Nix dev shell or an elan install when the exact `lean-toolchain` pin matters.

The backend, runtime, and test harness run on CPython 3.11 or newer; that is the implementation
language and the target. `pixi.toml` provides the Python environment.

LPython 0.22.0 stays pinned in `pixi.toml` only for `tests/lpython/run_probes.py`. It is not
needed to build, test, or run leanscript. If the pinned compiler becomes a problem for `pixi
install`, move it to a separate pixi feature environment; the probe script must keep working.

`python -m leanscript` depends on a built `leanscript-ir`. The CLI and tests look for it in this
order: `LEANSCRIPT_IR`, `.lake/build/bin/leanscript-ir`, then `PATH`. If none exist, the error names
the missing executable and the build command.

## Open questions

The JSON boundary is versioned at 1. Any breaking change to the schema must bump the version, and
the Python loader rejects versions it does not know.

- Should reference-count leak checking return as an opt-in debug mode, now that the runtime owns
  the counts?
- What is the final negative-test wording for `--allow-unavailable`, and which `@[extern]` fixture
  pins it?
- Should the LPython probe dependency move to a pixi feature environment so `pixi install` does not
  fetch the compiler by default?
