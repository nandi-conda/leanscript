# IR JSON boundary

`leanscript-ir dump-json <file.lean> [-o <out.json>]` produces one JSON object. This document is
the contract between `src/LeanScript/DumpJson.lean` and the LPython emitter. The JSON is compact,
with no whitespace, and is written on a single line.

## Top-level object

| Field | Type | Meaning |
| --- | --- | --- |
| `version` | number | Schema version. The current version is 1. |
| `names` | array of name | The name table. Every name in the document is an index into this array. |
| `decls` | array of declaration | The declaration closure reachable from the roots, in emission order. |
| `aliases` | array of two name indexes | Pairs `[extern, implementation]` for externs whose C symbol a Lean declaration exports. |
| `inits` | array of name indexes | The initializers of every imported module and the current module, in startup order. |
| `main` | name index | The name `main`. |
| `mainArity` | number | The number of parameters of `main`. |
| `errorToString` | name index | The name `IO.Error.toString`. |

The current schema version is 1. The backend loader must reject any other version rather than
assume the shape of the document. Name indexes are local to one document and must not be stored
across runs or compared with indexes from another document.

`inits` can contain names that are not in `decls`, because it covers every imported module. The
emitter must filter it to the declarations that are present.

Order is significant: `decls` is emitted in the given order, aliases are emitted after the
declarations in the given order, and `inits` is emitted in the given order.

## Name

```json
{"str": "Lean.Name.toString", "js": "l_mangled", "display": "user-facing"}
```

| Field | Meaning |
| --- | --- |
| `str` | `Name.toString`. Used for extern lookup and matching against the runtime's extern table. |
| `js` | The mangled identifier, from `Name.mangle "l_"`. The key is historical; the value is a valid identifier in LPython source and is used in the emitted source. |
| `display` | The private name stripped with `privateToUserName?`, or the name itself, as a string. Used in diagnostics. |

## Target conventions

- The target is LPython 0.22.0. The emitted source is LPython 0.22 source and must stay within the
  Python subset that compiler supports.
- LPython is statically typed. The emitter derives parameter, return, and local annotations from
  the IR types; the runtime's public signatures need matching annotations.
- Every `js` value is a valid identifier in LPython source. Lean names mangle to `l_...`.
- Generated files start with `import leanscript_runtime as _rt`. The runtime package lives at the
  project root and must be importable by LPython; the test harness makes it visible to the
  compiler.
- The current contract imports `leanscript_runtime.externs` as a dict of callables. LPython has no
  common callable type and `dict[str, T]` is homogeneous, so the LPython path must resolve externs
  at emission time and emit direct calls or a finite `if` chain. There is no generated extern file.
- LPython has fixed-width numeric types. The runtime maps the IR's integer types to LPython types
  and preserves Lean's wrapping rules. Do not assume arbitrary-precision Python integers.
- Lean strings are UTF-8 byte sequences. The LPython runtime must preserve that behavior,
  including byte length and indexing, under LPython's string representation.
- Reference-count operations become runtime calls. LPython manages memory, so `inc`, `dec`, and
  `del` may be no-ops. `reset`, `isShared`, and `reuse` must preserve exclusive-update semantics;
  a conservative `isShared` that always returns true is correct but allocates.
- `unreachable` cannot use exceptions; LPython 0.22 has no usable `try`/`except`. Use an
  `assert`-based abort or an explicit return code.
- The generated module is compiled by LPython ahead of time. It must not rely on CPython-only
  modules or dynamic features.
- LPython 0.22.0 rejects classes with non-default constructors and methods, exceptions, closures,
  `bytearray`/`bytes`, and writable `os`/file APIs. The type model is the main blocker: Lean IR
  values are dynamically typed and LPython has no `Any`, union, or object type. The JSON schema can
  stay unchanged, but the emitter and runtime shape must change as described in
  `docs/lpython-subset.md`. CPython 3 source is an explicitly flagged fallback that requires user
  approval.

## Declaration

Both declaration kinds have `k`, `name`, `params`, and `initFn`.

```json
{"k": "fdecl", "name": 0, "params": [], "ty": "void", "body": {...}, "initFn": null}
{"k": "extern", "name": 1, "params": [], "initFn": null}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `k` | `"fdecl"` or `"extern"` | Declaration kind. |
| `name` | name index | Declaration name. |
| `params` | array of parameter | Parameters, in order. |
| `ty` | IR type | Return type. Only on `fdecl`. |
| `body` | function body | Body. Only on `fdecl`. |
| `initFn` | name index or `null` | The `[init]` initializer for this declaration, if it has one. A nullary `fdecl` with an `initFn` is an init cell; a nullary `fdecl` without one is a lazy constant. |

## Parameter

```json
{"x": 0, "borrow": false, "ty": "object"}
```

`x` is a variable index, `borrow` is its ownership flag, and `ty` is its IR type.

## IR type

Simple types are a string:

`"float"`, `"uint8"`, `"uint16"`, `"uint32"`, `"uint64"`, `"usize"`, `"erased"`, `"object"`,
`"tobject"`, `"float32"`, `"tagged"`, `"void"`.

Compound types are objects:

```json
{"k": "struct", "name": 3, "types": ["usize", "object"]}
{"k": "struct", "name": null, "types": ["usize"]}
{"k": "union", "name": 4, "types": ["object", "float"]}
```

`name` is a name index, or `null` for an anonymous struct. `types` are the field types in order.

## Expression

Every expression has a `k` tag.

| `k` | Additional fields |
| --- | --- |
| `ctor` | `info`: constructor info; `ys`: arguments. |
| `reset` | `n`: number; `x`: variable index. |
| `reuse` | `x`: variable index; `info`: constructor info; `updtHeader`: boolean; `ys`: arguments. |
| `proj` | `i`: field index; `x`: variable index. |
| `uproj` | `i`: field index; `x`: variable index. |
| `sproj` | `n`: field index; `offset`: byte offset; `x`: variable index. |
| `fap` | `c`: name index of the callee; `ys`: arguments. |
| `pap` | `c`: name index of the callee; `ys`: arguments. |
| `ap` | `x`: variable index of the callee; `ys`: arguments. |
| `box` | `ty`: IR type; `x`: variable index. |
| `unbox` | `x`: variable index. |
| `lit` | `v`: `"num"` with `n`: number, or `"str"` with `s`: string. |
| `isShared` | `x`: variable index. |

## Argument

```json
{"k": "var", "x": 0}
{"k": "erased"}
```

## Constructor info

```json
{"name": 5, "cidx": 0, "size": 1, "usize": 1, "ssize": 0}
```

`name` is a name index. The remaining fields are numbers. `size` is the total field count, `usize`
the number of object fields, and `ssize` the number of scalar fields.

## Function body

Every body has a `k` tag.

| `k` | Additional fields |
| --- | --- |
| `vdecl` | `x`: variable index; `ty`: IR type; `e`: expression; `b`: continuation body. |
| `jdecl` | `j`: join-point index; `xs`: parameters; `v`: continuation body; `b`: body inside the labeled block. The emitter emits `b` inside the label and then `v`. |
| `set` | `x`: variable index; `i`: field index; `y`: argument; `b`: continuation body. |
| `setTag` | `x`: variable index; `cidx`: constructor index; `b`: continuation body. |
| `uset` | `x`: variable index; `i`: field index; `y`: variable index; `b`: continuation body. |
| `sset` | `x`: variable index; `i`: field index; `offset`: byte offset; `y`: variable index; `b`: continuation body. The scalar type is omitted because the emitter does not use it. |
| `inc` | `x`: variable index; `n`: count; `c`: boolean; `persistent`: boolean; `b`: continuation body. |
| `dec` | `x`: variable index; `n`: count; `c`: boolean; `persistent`: boolean; `b`: continuation body. |
| `del` | `x`: variable index; `b`: continuation body. |
| `case` | `tid`: name index; `x`: variable index; `xt`: IR type; `alts`: alternatives. |
| `ret` | `y`: argument. |
| `jmp` | `j`: join-point index; `ys`: arguments. |
| `unreachable` | none. |

`tid` on `case` is diagnostic and has no effect on emission. Join-point indexes are only unique
within a declaration.

## Alternative

```json
{"k": "ctor", "info": {...}, "b": {...}}
{"k": "default", "b": {...}}
```

Alternatives are emitted in the given order. A `case` with no `default` alternative uses the
runtime's unreachable path.
