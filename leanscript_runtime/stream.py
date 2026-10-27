"""`IO.FS.Stream`s, and the standard streams."""

from .core import Ctor, dec, inc, mark_persistent, pap
from .io import attempt
from .string import LeanString


def decode_bytes(data):
    """Returns the string whose UTF-8 bytes are `data`.

    Lean strings are byte sequences, so bytes that are not valid UTF-8 are kept as lone surrogates,
    which `LeanString.utf8` turns back into the same bytes.
    """
    raw = bytes(data)
    return LeanString(raw.decode("utf-8", errors="surrogateescape"), raw)


def _write_bytes(handle, b):
    """Writes the bytes of the owned `ByteArray` `b` to `handle`, consuming `b`."""
    result = attempt(None, lambda: handle.write(b.data))
    dec(b)
    return result


def _write_string(handle, s):
    """Writes the UTF-8 of the owned string `s` to `handle`, consuming `s`."""
    result = attempt(None, lambda: handle.write(s.utf8))
    dec(s)
    return result


def mk_stream(handle):
    """Returns a persistent `IO.FS.Stream` backed by `handle`, like `IO.FS.Stream.ofHandle`.

    `handle` must have the methods `flush()`, `read(n)`, which returns a `ByteArray`, `write(data)`,
    `get_line()`, which returns the bytes of the line, and `is_tty()`. Each field of the stream is a
    closure, which takes ownership of its arguments.
    """
    stream = Ctor(
        0,
        [
            # flush : IO Unit
            pap(lambda _w: attempt(None, handle.flush), 1, []),
            # read : USize → IO ByteArray
            pap(lambda n, _w: attempt(None, lambda: handle.read(n)), 2, []),
            # write : ByteArray → IO Unit
            pap(lambda b, _w: _write_bytes(handle, b), 2, []),
            # getLine : IO String
            pap(lambda _w: attempt(None, lambda: decode_bytes(handle.get_line())), 1, []),
            # putStr : String → IO Unit
            pap(lambda s, _w: _write_string(handle, s), 2, []),
            # isTty : BaseIO Bool. `BaseIO` results are not wrapped in `EST.Out`.
            pap(lambda _w: 1 if handle.is_tty() else 0, 1, []),
        ],
        None,
    )
    return mark_persistent(stream)


def std_stream_externs(name, stream):
    """Returns the externs `IO.get<name>` and `IO.set<name>`, which get and set a standard stream.

    The stream is initially `stream`.
    """
    current = [stream]

    def get_stream(_w):
        inc(current[0])
        return current[0]

    # The old stream's reference moves from the global to the caller.
    def set_stream(s, _w):
        old = current[0]
        current[0] = s
        return old

    return {f"IO.get{name}": get_stream, f"IO.set{name}": set_stream}


# The module provides the stream type and the standard stream externs, which `platform` registers.
externs = {}
