"""The runtime support for programs that leanscript emits."""

from __future__ import annotations

from . import array, bytearray, fixed, hash, io, misc, nat, platform, ref, stream, string
from . import float as float_module
from .core import (
    FREED,
    Closure,
    Ctor,
    Ref,
    Thunk,
    apply,
    array_to_list,
    dec,
    del_,
    flush_output,
    inc,
    inc_n,
    init_cell,
    init_scalars,
    is_shared,
    lazy,
    list_to_array,
    mark_persistent,
    mk_string,
    panic,
    pap,
    reset,
    resolve_externs,
    run_main,
    tag,
    track,
    unreachable,
    write_stderr,
    write_stdout,
)

# The implementations of the externs that generated programs may call, keyed by Lean name.
externs: dict[str, object] = {}
for module in (
    nat,
    fixed,
    float_module,
    string,
    array,
    bytearray,
    misc,
    hash,
    io,
    stream,
    platform,
    ref,
):
    externs.update(module.externs)


def _panic_core(_alpha, default_value, msg):
    text = msg.data if isinstance(msg, string.LeanString) else str(msg)
    dec(msg)
    # The default value is borrowed, but we return it as an owned reference.
    inc(default_value)
    return panic(default_value, text)


externs["panicCore"] = _panic_core

__all__ = [
    "FREED",
    "Closure",
    "Ctor",
    "Ref",
    "Thunk",
    "apply",
    "array_to_list",
    "dec",
    "del_",
    "externs",
    "flush_output",
    "inc",
    "inc_n",
    "init_cell",
    "init_scalars",
    "is_shared",
    "lazy",
    "list_to_array",
    "mark_persistent",
    "mk_string",
    "panic",
    "pap",
    "reset",
    "resolve_externs",
    "run_main",
    "tag",
    "track",
    "unreachable",
    "write_stderr",
    "write_stdout",
]
