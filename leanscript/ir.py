"""The IR program that `leanscript-ir dump-json` produces."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Union

# The JSON schema version that this module understands.
SCHEMA_VERSION = 1


class ProgramError(Exception):
    """The dumped program is malformed or uses an unsupported schema."""


@dataclass(frozen=True)
class Name:
    """A Lean name, with the strings that the emitter needs for it."""

    text: str
    js: str
    display: str


@dataclass(frozen=True)
class IRType:
    kind: str
    name: int | None = None
    types: tuple["IRType", ...] = ()

    @property
    def is_scalar(self) -> bool:
        return self.kind in {
            "float",
            "float32",
            "uint8",
            "uint16",
            "uint32",
            "uint64",
            "usize",
        }


@dataclass(frozen=True)
class Param:
    x: int
    borrow: bool
    ty: IRType


@dataclass(frozen=True)
class CtorInfo:
    name: int
    cidx: int
    size: int
    usize: int
    ssize: int

    @property
    def is_scalar(self) -> bool:
        return not (self.size > 0 or self.usize > 0 or self.ssize > 0)


@dataclass(frozen=True)
class Arg:
    kind: str
    x: int = 0


@dataclass(frozen=True)
class Ctor:
    info: CtorInfo
    ys: tuple[Arg, ...]


@dataclass(frozen=True)
class Reset:
    n: int
    x: int


@dataclass(frozen=True)
class Reuse:
    x: int
    info: CtorInfo
    updt_header: bool
    ys: tuple[Arg, ...]


@dataclass(frozen=True)
class Proj:
    i: int
    x: int


@dataclass(frozen=True)
class UProj:
    i: int
    x: int


@dataclass(frozen=True)
class SProj:
    n: int
    offset: int
    x: int


@dataclass(frozen=True)
class Fap:
    c: int
    ys: tuple[Arg, ...]


@dataclass(frozen=True)
class Pap:
    c: int
    ys: tuple[Arg, ...]


@dataclass(frozen=True)
class Ap:
    x: int
    ys: tuple[Arg, ...]


@dataclass(frozen=True)
class Box:
    ty: IRType
    x: int


@dataclass(frozen=True)
class Unbox:
    x: int


@dataclass(frozen=True)
class LitNum:
    value: int


@dataclass(frozen=True)
class LitStr:
    value: str


@dataclass(frozen=True)
class IsShared:
    x: int


Expr = Union[
    Ctor,
    Reset,
    Reuse,
    Proj,
    UProj,
    SProj,
    Fap,
    Pap,
    Ap,
    Box,
    Unbox,
    LitNum,
    LitStr,
    IsShared,
]


@dataclass(frozen=True)
class VDecl:
    x: int
    ty: IRType
    e: Expr
    b: "FnBody"


@dataclass(frozen=True)
class JDecl:
    j: int
    xs: tuple[Param, ...]
    v: "FnBody"
    b: "FnBody"


@dataclass(frozen=True)
class Set:
    x: int
    i: int
    y: Arg
    b: "FnBody"


@dataclass(frozen=True)
class SetTag:
    x: int
    cidx: int
    b: "FnBody"


@dataclass(frozen=True)
class USet:
    x: int
    i: int
    y: int
    b: "FnBody"


@dataclass(frozen=True)
class SSet:
    x: int
    i: int
    offset: int
    y: int
    b: "FnBody"


@dataclass(frozen=True)
class Inc:
    x: int
    n: int
    c: bool
    persistent: bool
    b: "FnBody"


@dataclass(frozen=True)
class Dec:
    x: int
    n: int
    c: bool
    persistent: bool
    b: "FnBody"


@dataclass(frozen=True)
class Del:
    x: int
    b: "FnBody"


@dataclass(frozen=True)
class CtorAlt:
    info: CtorInfo
    b: "FnBody"


@dataclass(frozen=True)
class DefaultAlt:
    b: "FnBody"


Alt = Union[CtorAlt, DefaultAlt]


@dataclass(frozen=True)
class Case:
    tid: int
    x: int
    xt: IRType
    alts: tuple[Alt, ...]


@dataclass(frozen=True)
class Ret:
    y: Arg


@dataclass(frozen=True)
class Jmp:
    j: int
    ys: tuple[Arg, ...]


@dataclass(frozen=True)
class Unreachable:
    pass


FnBody = Union[
    VDecl,
    JDecl,
    Set,
    SetTag,
    USet,
    SSet,
    Inc,
    Dec,
    Del,
    Case,
    Ret,
    Jmp,
    Unreachable,
]


@dataclass(frozen=True)
class Decl:
    name: int
    params: tuple[Param, ...]
    ty: IRType | None
    body: FnBody | None
    init_fn: int | None
    is_extern: bool


@dataclass(frozen=True)
class Program:
    names: tuple[Name, ...]
    decls: tuple[Decl, ...]
    aliases: tuple[tuple[int, int], ...]
    inits: tuple[int, ...]
    main: int
    main_arity: int
    error_to_string: int


def _field(d: dict[str, Any], key: str, kind: type) -> Any:
    value = d.get(key)
    if not isinstance(value, kind):
        raise ProgramError(f"expected `{key}` to be a {kind.__name__}")
    return value


def _load_type(d: dict[str, Any] | str) -> IRType:
    if isinstance(d, str):
        return IRType(d)
    kind = _field(d, "k", str)
    if kind in ("struct", "union"):
        name = d.get("name")
        return IRType(kind, name, tuple(_load_type(t) for t in d["types"]))
    return IRType(kind)


def _load_param(d: dict[str, Any]) -> Param:
    return Param(_field(d, "x", int), _field(d, "borrow", bool), _load_type(d["ty"]))


def _load_ctor(d: dict[str, Any]) -> CtorInfo:
    return CtorInfo(
        _field(d, "name", int),
        _field(d, "cidx", int),
        _field(d, "size", int),
        _field(d, "usize", int),
        _field(d, "ssize", int),
    )


def _load_arg(d: dict[str, Any]) -> Arg:
    if _field(d, "k", str) == "var":
        return Arg("var", _field(d, "x", int))
    return Arg("erased")


def _load_args(d: dict[str, Any]) -> tuple[Arg, ...]:
    return tuple(_load_arg(a) for a in d["ys"])


def _load_expr(d: dict[str, Any]) -> Expr:
    kind = _field(d, "k", str)
    if kind == "ctor":
        return Ctor(_load_ctor(d["info"]), _load_args(d))
    if kind == "reset":
        return Reset(_field(d, "n", int), _field(d, "x", int))
    if kind == "reuse":
        return Reuse(
            _field(d, "x", int),
            _load_ctor(d["info"]),
            _field(d, "updtHeader", bool),
            _load_args(d),
        )
    if kind == "proj":
        return Proj(_field(d, "i", int), _field(d, "x", int))
    if kind == "uproj":
        return UProj(_field(d, "i", int), _field(d, "x", int))
    if kind == "sproj":
        return SProj(_field(d, "n", int), _field(d, "offset", int), _field(d, "x", int))
    if kind == "fap":
        return Fap(_field(d, "c", int), _load_args(d))
    if kind == "pap":
        return Pap(_field(d, "c", int), _load_args(d))
    if kind == "ap":
        return Ap(_field(d, "x", int), _load_args(d))
    if kind == "box":
        return Box(_load_type(d["ty"]), _field(d, "x", int))
    if kind == "unbox":
        return Unbox(_field(d, "x", int))
    if kind == "lit":
        if _field(d, "v", str) == "num":
            return LitNum(_field(d, "n", int))
        return LitStr(_field(d, "s", str))
    if kind == "isShared":
        return IsShared(_field(d, "x", int))
    raise ProgramError(f"unknown expression `{kind}`")


def _load_alt(d: dict[str, Any]) -> Alt:
    if _field(d, "k", str) == "ctor":
        return CtorAlt(_load_ctor(d["info"]), _load_body(d["b"]))
    return DefaultAlt(_load_body(d["b"]))


def _load_body(d: dict[str, Any]) -> FnBody:
    kind = _field(d, "k", str)
    if kind == "vdecl":
        return VDecl(_field(d, "x", int), _load_type(d["ty"]), _load_expr(d["e"]), _load_body(d["b"]))
    if kind == "jdecl":
        return JDecl(
            _field(d, "j", int),
            tuple(_load_param(p) for p in d["xs"]),
            _load_body(d["v"]),
            _load_body(d["b"]),
        )
    if kind == "set":
        return Set(_field(d, "x", int), _field(d, "i", int), _load_arg(d["y"]), _load_body(d["b"]))
    if kind == "setTag":
        return SetTag(_field(d, "x", int), _field(d, "cidx", int), _load_body(d["b"]))
    if kind == "uset":
        return USet(
            _field(d, "x", int),
            _field(d, "i", int),
            _field(d, "y", int),
            _load_body(d["b"]),
        )
    if kind == "sset":
        return SSet(
            _field(d, "x", int),
            _field(d, "i", int),
            _field(d, "offset", int),
            _field(d, "y", int),
            _load_body(d["b"]),
        )
    if kind == "inc":
        return Inc(
            _field(d, "x", int),
            _field(d, "n", int),
            _field(d, "c", bool),
            _field(d, "persistent", bool),
            _load_body(d["b"]),
        )
    if kind == "dec":
        return Dec(
            _field(d, "x", int),
            _field(d, "n", int),
            _field(d, "c", bool),
            _field(d, "persistent", bool),
            _load_body(d["b"]),
        )
    if kind == "del":
        return Del(_field(d, "x", int), _load_body(d["b"]))
    if kind == "case":
        return Case(
            _field(d, "tid", int),
            _field(d, "x", int),
            _load_type(d["xt"]),
            tuple(_load_alt(a) for a in d["alts"]),
        )
    if kind == "ret":
        return Ret(_load_arg(d["y"]))
    if kind == "jmp":
        return Jmp(_field(d, "j", int), _load_args(d))
    if kind == "unreachable":
        return Unreachable()
    raise ProgramError(f"unknown instruction `{kind}`")


def _load_decl(d: dict[str, Any]) -> Decl:
    name = _field(d, "name", int)
    params = tuple(_load_param(p) for p in d["params"])
    init_fn = d.get("initFn")
    if _field(d, "k", str) == "extern":
        return Decl(name, params, None, None, init_fn, True)
    return Decl(name, params, _load_type(d["ty"]), _load_body(d["body"]), init_fn, False)


def load_program(d: dict[str, Any]) -> Program:
    """Loads a program from the JSON object that `leanscript-ir dump-json` writes."""
    version = d.get("version")
    if version != SCHEMA_VERSION:
        raise ProgramError(
            f"unsupported IR JSON version {version!r}; rebuild `leanscript-ir`"
        )
    # IR bodies nest as deeply as the source program, so allow more recursion than Python does by
    # default.
    if sys.getrecursionlimit() < 20000:
        sys.setrecursionlimit(20000)
    return Program(
        names=tuple(
            Name(_field(n, "str", str), _field(n, "js", str), _field(n, "display", str))
            for n in d["names"]
        ),
        decls=tuple(_load_decl(x) for x in d["decls"]),
        aliases=tuple((a, b) for a, b in d["aliases"]),
        inits=tuple(d["inits"]),
        main=_field(d, "main", int),
        main_arity=_field(d, "mainArity", int),
        error_to_string=_field(d, "errorToString", int),
    )


def load_program_text(text: str) -> Program:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise ProgramError(f"malformed IR JSON: {err}") from err
    return load_program(data)
