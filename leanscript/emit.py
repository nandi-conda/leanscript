"""Emits a Python module from a Lean IR program."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from leanscript_runtime import externs as runtime_externs

from .ir import (
    Alt,
    Ap,
    Arg,
    Box,
    Case,
    Ctor,
    CtorAlt,
    CtorInfo,
    Dec,
    Decl,
    Del,
    Fap,
    FnBody,
    Inc,
    IRType,
    IsShared,
    JDecl,
    Jmp,
    LitNum,
    LitStr,
    Pap,
    Param,
    Proj,
    Program,
    Reset,
    Ret,
    Reuse,
    SProj,
    SSet,
    Set,
    SetTag,
    UProj,
    Unreachable,
    USet,
    Unbox,
    VDecl,
)


class EmitError(Exception):
    """The program cannot be emitted as Python."""


@dataclass(frozen=True)
class EmitOutput:
    source: str
    # For each extern that the program uses but the runtime does not implement, a chain of calls from
    # where the program starts to the extern.
    unavailable: tuple[tuple[int, ...], ...]


def var_name(x: int) -> str:
    return f"x_{x}"


def jp_name(j: int) -> str:
    return f"block_{j}"


def arg_to_py(a: Arg) -> str:
    return var_name(a.x) if a.kind == "var" else "0"


def args_to_py(ys: tuple[Arg, ...]) -> str:
    return ", ".join(arg_to_py(y) for y in ys)


def quote_py(s: str) -> str:
    """Quotes `s` as a Python string literal."""
    r = '"'
    for c in s:
        if c == '"':
            r += '\\"'
        elif c == "\\":
            r += "\\\\"
        elif c == "\n":
            r += "\\n"
        elif c == "\r":
            r += "\\r"
        elif c == "\t":
            r += "\\t"
        else:
            n = ord(c)
            if n < 0x20 or n in (0x7F, 0x2028, 0x2029):
                r += f"\\u{n:04x}"
            else:
                r += c
    return r + '"'


def nat_lit_to_py(v: int, ty: IRType) -> str:
    # We target a 32-bit platform so that `USize` fits in a machine word.
    if ty.kind == "usize":
        return str(v % 2**32)
    if ty.kind in ("float", "float32"):
        return repr(float(v))
    return str(v)


def scalar_key(i: int, offset: int) -> int:
    """The key under which a scalar field at byte offset `sizeof(void*)*i + offset` is stored."""
    return 8 * i + offset


def ctor_to_py(info: CtorInfo, ys: tuple[Arg, ...]) -> str:
    if not ys and info.is_scalar:
        return str(info.cidx)
    scalars = "{}" if info.usize > 0 or info.ssize > 0 else "None"
    return f"_Ctor({info.cidx}, [{args_to_py(ys)}], {scalars})"


def collect_expr_fns(e: object) -> tuple[int, ...]:
    if isinstance(e, (Fap, Pap)):
        return (e.c,)
    return ()


def collect_body_fns(b: FnBody, acc: tuple[int, ...] = ()) -> tuple[int, ...]:
    if isinstance(b, VDecl):
        return collect_body_fns(b.b, acc + collect_expr_fns(b.e))
    if isinstance(b, JDecl):
        return collect_body_fns(b.b, collect_body_fns(b.v, acc))
    if isinstance(b, Case):
        for alt in b.alts:
            acc += collect_body_fns(alt.b, ())
        return acc
    if isinstance(b, (Ret, Jmp, Unreachable)):
        return acc
    return collect_body_fns(b.b, acc)


def contains_jdecl(b: FnBody) -> bool:
    if isinstance(b, JDecl):
        return True
    if isinstance(b, Case):
        return any(contains_jdecl(alt.b) for alt in b.alts)
    if isinstance(b, (Ret, Jmp, Unreachable)):
        return False
    return contains_jdecl(b.b)


_ABSENT = object()


def call_path(
    program: Program, roots: tuple[int, ...], target: int
) -> tuple[int, ...] | None:
    """Returns a shortest chain of calls from one of `roots` to `target`, if it exists."""
    decls = {d.name: d for d in program.decls}
    aliases = dict(program.aliases)
    callers: dict[int, int | None] = {r: None for r in roots}
    queue = list(roots)
    i = 0
    while i < len(queue):
        name = queue[i]
        i += 1
        if name == target:
            path = [name]
            while True:
                caller = callers.get(path[-1], _ABSENT)
                if caller is _ABSENT or caller is None:
                    break
                path.append(caller)
            return tuple(reversed(path))
        decl = decls.get(name)
        if name in aliases:
            callees = [aliases[name]]
        elif decl is not None and not decl.is_extern and decl.body is not None:
            callees = list(collect_body_fns(decl.body))
        else:
            callees = []
        if decl is not None and decl.init_fn is not None:
            callees.append(decl.init_fn)
        for callee in callees:
            if callee not in callers:
                callers[callee] = name
                queue.append(callee)
    return None


class _Emitter:
    """Emits the declarations of one program.

    A function body whose control flow stays within a single block is emitted directly. A body with
    join points or self tail calls is lowered to numbered blocks that a `_pc` dispatch loop selects
    between; this keeps joins from nesting Python loops, which CPython limits.
    """

    def __init__(self, program: Program, ctx_decls: dict[int, Decl]):
        self.program = program
        self.decls = ctx_decls
        self.out: list[str] = []
        self.indent = 0
        self.jp_params: dict[int, tuple[Param, ...]] = {}
        # The current lowered function, if any: its blocks, current block, and label of each join
        # point.
        self.blocks: list[list[str]] | None = None
        self.current = 0
        self.base_indent = 0
        self.jp_labels: dict[int, int] = {}
        self.curr_fn = -1
        self.curr_params: tuple[Param, ...] = ()
        self.has_loop = False

    def line(self, s: str) -> None:
        text = "    " * self.indent + s + "\n"
        if self.blocks is None:
            self.out.append(text)
        else:
            self.blocks[self.current].append(text)

    def indent_more(self):
        return _Indent(self)

    def new_block(self) -> int:
        assert self.blocks is not None
        self.blocks.append([])
        return len(self.blocks) - 1

    def start_block(self, label: int) -> None:
        self.current = label
        self.indent = self.base_indent

    def decl(self, name: int) -> Decl:
        try:
            return self.decls[name]
        except KeyError:
            raise EmitError(f"unknown declaration '{self.program.names[name].text}'") from None

    def _jp_params(self, j: int) -> tuple[Param, ...]:
        if j not in self.jp_params:
            raise EmitError(f"unknown join point {jp_name(j)}")
        return self.jp_params[j]

    def _jp_label(self, j: int) -> int:
        if j not in self.jp_labels:
            raise EmitError(f"unknown join point {jp_name(j)}")
        return self.jp_labels[j]

    def expr_to_py(self, ty: IRType, e: object) -> str:
        if isinstance(e, Ctor):
            return ctor_to_py(e.info, e.ys)
        if isinstance(e, Reset):
            return f"_rt.reset({var_name(e.x)}, {e.n})"
        if isinstance(e, Reuse):
            raise EmitError("`reuse` must be emitted with `emit_reuse`")
        if isinstance(e, Proj):
            return f"{var_name(e.x)}.f[{e.i}]"
        if isinstance(e, UProj):
            return f"{var_name(e.x)}.s[{scalar_key(e.i, 0)}]"
        if isinstance(e, SProj):
            return f"{var_name(e.x)}.s[{scalar_key(e.n, e.offset)}]"
        if isinstance(e, Fap):
            callee = self.program.names[e.c].js
            if not self.decl(e.c).params:
                return f"{callee}()"
            return f"{callee}({args_to_py(e.ys)})"
        if isinstance(e, Pap):
            arity = len(self.decl(e.c).params)
            return f"_rt.pap({self.program.names[e.c].js}, {arity}, [{args_to_py(e.ys)}])"
        if isinstance(e, Ap):
            return f"_rt.apply({var_name(e.x)}, [{args_to_py(e.ys)}])"
        if isinstance(e, (Box, Unbox)):
            return var_name(e.x)
        if isinstance(e, LitNum):
            return nat_lit_to_py(e.value, ty)
        if isinstance(e, LitStr):
            return f"_rt.mk_string({quote_py(e.value)})"
        if isinstance(e, IsShared):
            return f"_rt.is_shared({var_name(e.x)})"
        raise EmitError(f"cannot emit expression {e!r}")

    def is_self_tail_call(self, x: int, e: object, b: FnBody) -> bool:
        return (
            self.has_loop
            and isinstance(e, Fap)
            and e.c == self.curr_fn
            and isinstance(b, Ret)
            and b.y.kind == "var"
            and x == b.y.x
        )

    def has_self_tail_call(self, f: int, b: FnBody) -> bool:
        if isinstance(b, VDecl):
            if isinstance(b.e, Fap) and isinstance(b.b, Ret) and b.b.y.kind == "var":
                return b.e.c == f and b.x == b.b.y.x
            return self.has_self_tail_call(f, b.b)
        if isinstance(b, JDecl):
            return self.has_self_tail_call(f, b.v) or self.has_self_tail_call(f, b.b)
        if isinstance(b, Case):
            return any(self.has_self_tail_call(f, alt.b) for alt in b.alts)
        if isinstance(b, (Ret, Jmp, Unreachable)):
            return False
        return self.has_self_tail_call(f, b.b)

    def emit_self_tail_call(self, ys: tuple[Arg, ...]) -> None:
        updates = [
            (p, y) for p, y in zip(self.curr_params, ys) if y.kind != "var" or y.x != p.x
        ]
        # Evaluate every argument before assigning any parameter, as arguments may refer to
        # parameters.
        for i, (_, y) in enumerate(updates):
            self.line(f"_t{i} = {arg_to_py(y)}")
        for i, (p, _) in enumerate(updates):
            self.line(f"{var_name(p.x)} = _t{i}")
        self.line("_pc = 0")
        self.line("continue")

    def emit_reuse(
        self, x: int, y: int, info: CtorInfo, updt_header: bool, ys: tuple[Arg, ...]
    ) -> None:
        """Emits `let x := reuse y in ctor_i ys`."""
        self.line(f"{var_name(x)} = None")
        self.line(f"if {var_name(y)} == 0:")
        with self.indent_more():
            self.line(f"{var_name(x)} = {ctor_to_py(info, ys)}")
        self.line("else:")
        with self.indent_more():
            self.line(f"{var_name(x)} = {var_name(y)}")
            for i, arg in enumerate(ys):
                self.line(f"{var_name(x)}.f[{i}] = {arg_to_py(arg)}")
            if updt_header:
                self.line(f"{var_name(x)}.tag = {info.cidx}")
            if info.usize > 0 or info.ssize > 0:
                self.line(f"_rt.init_scalars({var_name(x)})")

    def emit_case(self, x: int, x_type: IRType, alts: tuple[Alt, ...]) -> None:
        discr = var_name(x) if x_type.is_scalar else f"_rt.tag({var_name(x)})"
        if self.blocks is None:
            self._emit_case_direct(discr, alts)
        else:
            self._emit_case_blocks(discr, alts)

    def _emit_case_direct(self, discr: str, alts: tuple[Alt, ...]) -> None:
        keyword = "if"
        has_default = False
        for alt in alts:
            if isinstance(alt, CtorAlt):
                self.line(f"{keyword} {discr} == {alt.info.cidx}:")
                keyword = "elif"
            else:
                self.line("else:")
                has_default = True
            with self.indent_more():
                self.emit_fn_body(alt.b)
        if not has_default:
            self.line("else:")
            with self.indent_more():
                self.line("return _rt.unreachable()")

    def _emit_case_blocks(self, discr: str, alts: tuple[Alt, ...]) -> None:
        labels = [self.new_block() for _ in alts]
        keyword = "if"
        has_default = False
        for alt, label in zip(alts, labels):
            if isinstance(alt, CtorAlt):
                self.line(f"{keyword} {discr} == {alt.info.cidx}:")
                keyword = "elif"
            else:
                self.line("else:")
                has_default = True
            with self.indent_more():
                self.line(f"_pc = {label}")
                self.line("continue")
        if not has_default:
            self.line("else:")
            with self.indent_more():
                self.line("return _rt.unreachable()")
        for alt, label in zip(alts, labels):
            saved = (self.current, self.indent)
            self.start_block(label)
            self.emit_fn_body(alt.b)
            self.current, self.indent = saved

    def emit_fn_body(self, b: FnBody) -> None:
        if isinstance(b, VDecl):
            if self.is_self_tail_call(b.x, b.e, b.b):
                if not isinstance(b.e, Fap):
                    raise EmitError("expected a full application in a self tail call")
                self.emit_self_tail_call(b.e.ys)
            elif isinstance(b.e, Reuse):
                self.emit_reuse(b.x, b.e.x, b.e.info, b.e.updt_header, b.e.ys)
                self.emit_fn_body(b.b)
            else:
                self.line(f"{var_name(b.x)} = {self.expr_to_py(b.ty, b.e)}")
                self.emit_fn_body(b.b)
        elif isinstance(b, JDecl):
            if self.blocks is None:
                raise EmitError("join point emitted outside the block lowering")
            self.jp_params[b.j] = b.xs
            label = self.new_block()
            self.jp_labels[b.j] = label
            if b.xs:
                self.line(", ".join(var_name(p.x) for p in b.xs) + " = None")
            self.emit_fn_body(b.b)
            self.start_block(label)
            self.emit_fn_body(b.v)
        elif isinstance(b, Set):
            self.line(f"{var_name(b.x)}.f[{b.i}] = {arg_to_py(b.y)}")
            self.emit_fn_body(b.b)
        elif isinstance(b, SetTag):
            self.line(f"{var_name(b.x)}.tag = {b.cidx}")
            self.emit_fn_body(b.b)
        elif isinstance(b, USet):
            self.line(f"{var_name(b.x)}.s[{scalar_key(b.i, 0)}] = {var_name(b.y)}")
            self.emit_fn_body(b.b)
        elif isinstance(b, SSet):
            self.line(f"{var_name(b.x)}.s[{scalar_key(b.i, b.offset)}] = {var_name(b.y)}")
            self.emit_fn_body(b.b)
        elif isinstance(b, Inc):
            if not b.persistent:
                if b.n == 1:
                    self.line(f"_rt.inc({var_name(b.x)})")
                else:
                    self.line(f"_rt.inc_n({var_name(b.x)}, {b.n})")
            self.emit_fn_body(b.b)
        elif isinstance(b, Dec):
            if not b.persistent:
                self.line(f"_rt.dec({var_name(b.x)})")
            self.emit_fn_body(b.b)
        elif isinstance(b, Del):
            self.line(f"_rt.del_({var_name(b.x)})")
            self.emit_fn_body(b.b)
        elif isinstance(b, Case):
            self.emit_case(b.x, b.xt, b.alts)
        elif isinstance(b, Ret):
            self.line(f"return {arg_to_py(b.y)}")
        elif isinstance(b, Jmp):
            for p, y in zip(self._jp_params(b.j), b.ys):
                self.line(f"{var_name(p.x)} = {arg_to_py(y)}")
            self.line(f"_pc = {self._jp_label(b.j)}")
            self.line("continue")
        elif isinstance(b, Unreachable):
            self.line("return _rt.unreachable()")
        else:
            raise EmitError(f"cannot emit instruction {b!r}")

    def emit_body(self, body: FnBody, has_loop: bool) -> None:
        if not has_loop and not contains_jdecl(body):
            self.emit_fn_body(body)
            return
        body_indent = self.indent
        self.blocks = []
        self.jp_labels = {}
        self.new_block()
        self.base_indent = body_indent + 2
        self.start_block(0)
        self.emit_fn_body(body)
        blocks = self.blocks
        self.blocks = None
        self.indent = body_indent
        self.line("_pc = 0")
        self.line("while True:")
        with self.indent_more():
            for label, block in enumerate(blocks):
                keyword = "if" if label == 0 else "elif"
                self.line(f"{keyword} _pc == {label}:")
                with self.indent_more():
                    if block:
                        self.out.extend(block)
                    else:
                        self.line("pass")
            self.line("else:")
            with self.indent_more():
                self.line('raise AssertionError("invalid program counter")')

    def emit_decl(self, decl: Decl) -> None:
        names = self.program.names
        name = names[decl.name].js
        if decl.is_extern:
            self.line(f"{name} = _ext[{quote_py(names[decl.name].text)}]")
        elif not decl.params:
            assert decl.body is not None
            if decl.init_fn is not None:
                self.line(f"{name} = _rt.init_cell()")
            else:
                initializer = f"_{name}_init"
                self.line(f"def {initializer}():")
                with self.indent_more():
                    self.emit_body(decl.body, False)
                self.line(f"{name} = _rt.lazy({initializer})")
        else:
            assert decl.body is not None
            has_loop = self.has_self_tail_call(decl.name, decl.body)
            params = ", ".join(var_name(p.x) for p in decl.params)
            self.line(f"def {name}({params}):")
            with self.indent_more():
                self.jp_params = {}
                saved = (self.curr_fn, self.curr_params, self.has_loop)
                self.curr_fn, self.curr_params, self.has_loop = (
                    decl.name,
                    decl.params,
                    has_loop,
                )
                self.emit_body(decl.body, has_loop)
                self.curr_fn, self.curr_params, self.has_loop = saved
        self.line("")


class _Indent:
    def __init__(self, e: _Emitter):
        self.e = e

    def __enter__(self):
        self.e.indent += 1

    def __exit__(self, *exc):
        self.e.indent -= 1
        return False


def emit_program(program: Program) -> EmitOutput:
    """Emits a Python program that runs `main`, containing every declaration reachable from it."""
    if sys.getrecursionlimit() < 20000:
        sys.setrecursionlimit(20000)
    names = program.names
    decls = program.decls
    available = frozenset(runtime_externs)
    externs = tuple(d.name for d in decls if d.is_extern)
    unavailable = tuple(
        sorted(
            (n for n in externs if names[n].text not in available),
            key=lambda n: names[n].text,
        )
    )
    ctx_decls = {d.name: d for d in decls}
    for ext, impl in program.aliases:
        try:
            ctx_decls[ext] = ctx_decls[impl]
        except KeyError:
            raise EmitError(
                f"no declaration found for '{names[impl].text}', which implements '{names[ext].text}'"
            ) from None
    inits = tuple(n for n in program.inits if n in ctx_decls)

    e = _Emitter(program, ctx_decls)

    def quote_names(ns: tuple[int, ...]) -> str:
        return ", ".join(quote_py(names[n].text) for n in ns)

    e.line("# Generated by LeanScript.")
    e.line("import leanscript_runtime as _rt")
    e.line("")
    e.line("_Ctor = _rt.Ctor")
    if not unavailable:
        e.line(f"_ext = _rt.resolve_externs([{quote_names(externs)}])")
    else:
        e.line(
            f"_ext = _rt.resolve_externs([{quote_names(externs)}], "
            f"[{quote_names(unavailable)}])"
        )
    e.line("")
    for decl in decls:
        # Join point ids are only unique within a declaration.
        e.jp_params = {}
        e.emit_decl(decl)
    # Aliases come last, since an implementation may be a constant that is not hoisted.
    for ext, impl in program.aliases:
        e.line(f"{names[ext].js} = {names[impl].js}")
    if program.aliases:
        e.line("")
    e.line("_inits = [")
    with e.indent_more():
        for n in inits:
            decl = ctx_decls[n]
            if decl.init_fn is not None:
                e.line(f"({names[decl.init_fn].js}, {names[n].js}),")
            else:
                e.line(f"({names[n].js}, None),")
    e.line("]")
    e.line(
        f"_rt.run_main(_inits, {names[program.main].js}, {program.main_arity}, "
        f"{names[program.error_to_string].js})"
    )

    io_unit_inits = tuple(
        n for n in program.inits if n in ctx_decls and ctx_decls[n].init_fn is None
    )
    roots = (program.main, program.error_to_string) + io_unit_inits
    paths = tuple(call_path(program, roots, n) or (n,) for n in unavailable)
    return EmitOutput("".join(e.out), paths)
