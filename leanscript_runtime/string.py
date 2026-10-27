"""`String`, represented as UTF-8 bytes that can grow without copying.

`String.Pos` and `String.Pos.Raw` are single-field structures over `Nat`, so a position is just its
byte offset. A position may be arbitrarily large, in which case it is past the end.

Each extern follows the ownership conventions of its C counterpart: an exclusive string is updated
in place, and a shared one is copied first.

The bytes are authoritative and live in a `bytearray`, which grows in amortized constant time; the
Python text and the scalar count are cached and invalidated on mutation. Keeping the bytes rather
than the text also makes byte offsets exact, because `surrogateescape` round-trips any byte
sequence, valid UTF-8 or not.
"""

from __future__ import annotations

from .bytearray import mk_byte_array
from .core import Ctor, array_to_list, dec, track
from .hash import hash_bytes

ENCODING = "utf-8"
# Byte sequences that are not valid UTF-8 become lone surrogates and back, instead of being
# replaced, so that byte offsets and hashes are those of the original bytes.
ERRORS = "surrogateescape"

# `Char.default`, which `String.Pos.Raw.get` returns for an invalid position.
DEFAULT_CHAR = 65


class LeanString:
    """A Lean `String`, stored as its UTF-8 bytes with a reference count."""

    def __init__(self, data: str, encoded: bytes | bytearray | None = None) -> None:
        self.rc = 1
        self._buf = bytearray(data.encode(ENCODING, ERRORS) if encoded is None else encoded)
        self._text: str | None = data
        self._length: int | None = None
        track(self)

    @property
    def data(self) -> str:
        """The contents as Python text, which may hold lone surrogates for invalid UTF-8."""
        if self._text is None:
            self._text = bytes(self._buf).decode(ENCODING, ERRORS)
        return self._text

    @data.setter
    def data(self, text: str) -> None:
        self._buf = bytearray(text.encode(ENCODING, ERRORS))
        self._text = text
        self._length = None

    @property
    def utf8(self) -> bytes:
        """The UTF-8 bytes of the contents."""
        return bytes(self._buf)

    def __str__(self) -> str:
        return self.data

    def __repr__(self) -> str:
        return f"LeanString({self.data!r})"

    def describe(self) -> str:
        return f"string {self.data!r}"


def mk_string(text: str) -> LeanString:
    """Makes a Lean `String` from the Python text `text`."""
    return LeanString(text)


def to_python(s: LeanString) -> str:
    """Returns the contents of `s` as Python text, without affecting its reference count."""
    return s.data


def _string_of_bytes(raw: bytes | bytearray) -> LeanString:
    """Makes a Lean `String` from UTF-8 bytes, keeping the bytes as they are."""
    text = bytes(raw).decode(ENCODING, ERRORS)
    return LeanString(text, raw)


def _count_scalars(raw: bytes | bytearray) -> int:
    return sum(1 for b in raw if b & 0xC0 != 0x80)


def _length(s: LeanString) -> int:
    """The number of Unicode scalar values, cached because counts are queried in loops."""
    if s._length is None:
        s._length = _count_scalars(s._buf)
    return s._length


def _byte_at(raw: bytes | bytearray, i: int) -> int:
    """Returns the byte at `i`, or 0, as reading past the end of a JS buffer does."""
    return raw[i] if 0 <= i < len(raw) else 0


def _is_char_boundary(raw: bytes | bytearray, i: int) -> bool:
    return 0 <= i < len(raw) and (raw[i] & 0xC0) != 0x80


def _sequence_size(b: int) -> int:
    """Returns the size of the UTF-8 sequence that starts with the byte `b`."""
    if b < 0x80:
        return 1
    if (b & 0xE0) == 0xC0:
        return 2
    if (b & 0xF0) == 0xE0:
        return 3
    return 4


def _encode_char(c: int) -> bytes:
    if c < 0x80:
        return bytes((c,))
    if c < 0x800:
        return bytes((0xC0 | (c >> 6), 0x80 | (c & 0x3F)))
    if c < 0x10000:
        return bytes((0xE0 | (c >> 12), 0x80 | ((c >> 6) & 0x3F), 0x80 | (c & 0x3F)))
    return bytes(
        (
            0xF0 | (c >> 18),
            0x80 | ((c >> 12) & 0x3F),
            0x80 | ((c >> 6) & 0x3F),
            0x80 | (c & 0x3F),
        )
    )


def _decode_char_at(raw: bytes | bytearray, i: int) -> int:
    """Decodes the UTF-8 sequence that starts at byte `i`, without validating it."""
    c = _byte_at(raw, i)
    if c < 0x80:
        return c
    if (c & 0xE0) == 0xC0:
        return ((c & 0x1F) << 6) | (_byte_at(raw, i + 1) & 0x3F)
    if (c & 0xF0) == 0xE0:
        return (
            ((c & 0x0F) << 12)
            | ((_byte_at(raw, i + 1) & 0x3F) << 6)
            | (_byte_at(raw, i + 2) & 0x3F)
        )
    return (
        ((c & 0x07) << 18)
        | ((_byte_at(raw, i + 1) & 0x3F) << 12)
        | ((_byte_at(raw, i + 2) & 0x3F) << 6)
        | (_byte_at(raw, i + 3) & 0x3F)
    )


def _chars(raw: bytes | bytearray) -> list[int]:
    """Returns the scalar values of the UTF-8 in `raw`."""
    chars = []
    i = 0
    while i < len(raw):
        chars.append(_decode_char_at(raw, i))
        i += _sequence_size(raw[i])
    return chars


def _reserve(s: LeanString) -> LeanString:
    """Takes ownership of `s` and returns an exclusive string with its contents."""
    if s.rc == 1:
        return s
    r = LeanString(s.data, s._buf)
    dec(s)
    return r


def _append_bytes(s: LeanString, raw: bytes | bytearray) -> LeanString:
    """Appends the UTF-8 bytes `raw` to the owned string `s`."""
    r = _reserve(s)
    # Count before extending, because `raw` may be `r`'s own buffer when a string is appended to
    # itself.
    added = _count_scalars(raw) if r._length is not None else 0
    if raw is r._buf:
        # Appending a string to itself would extend a buffer that is still borrowed as the source.
        raw = bytes(raw)
    r._buf += raw
    r._text = None
    if r._length is not None:
        r._length += added
    return r


def string_append(s: LeanString, t: LeanString) -> LeanString:
    """`String.append`: takes ownership of `s` and `t`."""
    if not t._buf:
        return s
    return _append_bytes(s, t._buf)


def string_push(s: LeanString, c: int) -> LeanString:
    """`String.push`: takes ownership of `s` and adds the char `c`."""
    return _append_bytes(s, _encode_char(c))


def string_get(s: LeanString, i: int) -> int:
    raw = s._buf
    return _decode_char_at(raw, i) if _is_char_boundary(raw, i) else DEFAULT_CHAR


def string_get_opt(s: LeanString, i: int) -> Ctor | int:
    """Returns `Option Char`: the char at `i` if it is a valid position before the end."""
    raw = s._buf
    if _is_char_boundary(raw, i):
        return Ctor(1, [_decode_char_at(raw, i)], None)
    return 0


def string_set(s: LeanString, i: int, c: int) -> LeanString:
    """`String.set`: takes ownership of `s` and replaces the char at the position `i`."""
    raw = s._buf
    if not _is_char_boundary(raw, i):
        return s
    old_size = _sequence_size(raw[i])
    encoded = _encode_char(c)
    if s.rc == 1 and old_size == len(encoded):
        raw[i : i + old_size] = encoded
        s._text = None
        s._length = None
        return s
    end = i + old_size
    r = _string_of_bytes(bytes(raw[:i]) + encoded + bytes(raw[end:]))
    dec(s)
    return r


def string_next(s: LeanString, i: int) -> int:
    """`String.Pos.Raw.next`, which steps one byte past an invalid position."""
    raw = s._buf
    return i + _sequence_size(raw[i]) if _is_char_boundary(raw, i) else i + 1


def string_prev(s: LeanString, i: int) -> int:
    """`String.Pos.Raw.prev`: the start of the char before position `i`, or 0 if there is none."""
    if i == 0:
        return 0
    raw = s._buf
    if i > len(raw):
        return i - 1
    j = i - 1
    while j > 0 and (raw[j] & 0xC0) == 0x80:
        j -= 1
    return j


def string_is_valid_pos(s: LeanString, i: int) -> bool:
    raw = s._buf
    return _is_char_boundary(raw, i) if i < len(raw) else i == len(raw)


def string_extract(s: LeanString, b: int, e: int) -> LeanString:
    """`String.Pos.Raw.extract`.

    Matching `lean_string_utf8_extract`, the result is empty if `b` is not a valid position, and
    runs to the end of the string if `e` is not.
    """
    raw = s._buf
    if b >= e or b >= len(raw) or not _is_char_boundary(raw, b):
        return mk_string("")
    if e > len(raw) or (e < len(raw) and not _is_char_boundary(raw, e)):
        e = len(raw)
    return _string_of_bytes(raw[b:e])


def _extract_valid(s: LeanString, b: int, e: int) -> LeanString:
    """Returns the string between two positions known to be valid, with `b <= e`."""
    return _string_of_bytes(s._buf[b:e])


def string_eq(s: LeanString, t: LeanString) -> bool:
    return s._buf == t._buf


def string_lt(s: LeanString, t: LeanString) -> bool:
    """Lexicographic order on bytes, which coincides with lexicographic order on scalar values."""
    return s._buf < t._buf


def _compare_bytes(a, a_start: int, a_end: int, b, b_start: int, b_end: int) -> int:
    """Compares the byte ranges `a[a_start, a_end)` and `b[b_start, b_end)`."""
    n = min(a_end - a_start, b_end - b_start)
    for i in range(n):
        x = a[a_start + i]
        y = b[b_start + i]
        if x != y:
            return -1 if x < y else 1
    return (a_end - a_start > b_end - b_start) - (a_end - a_start < b_end - b_start)


def _of_list(lst: int | Ctor) -> LeanString:
    """`String.mk`: takes ownership of the `List Char` `lst`."""
    raw = bytearray()
    head = lst
    while lst != 0:
        raw += _encode_char(lst.f[0])
        lst = lst.f[1]
    dec(head)
    return _string_of_bytes(raw)


def _to_list(s: LeanString) -> int | Ctor:
    """`String.toList`: takes ownership of `s` and returns its `List Char`."""
    list_ = array_to_list(_chars(s._buf))
    dec(s)
    return list_


def _bool(b: bool) -> int:
    return int(b)


def _slice_parts(slice_: Ctor) -> tuple[LeanString, int, int]:
    """Returns the string, start, and end of a `String.Slice`, which is a constructor."""
    s, start, end = slice_.f
    return s, start, end


def _slice_hash(slice_: Ctor) -> int:
    s, start, end = _slice_parts(slice_)
    raw = s._buf
    return hash_bytes(raw[start:end], end - start, 11)


def _slice_lt(x: Ctor, y: Ctor) -> int:
    s, s_start, s_end = _slice_parts(x)
    t, t_start, t_end = _slice_parts(y)
    return _bool(_compare_bytes(s._buf, s_start, s_end, t._buf, t_start, t_end) < 0)


def _of_byte_array(a, _h: int) -> LeanString:
    r = _string_of_bytes(a.data)
    dec(a)
    return r


def _to_byte_array(s: LeanString) -> object:
    r = mk_byte_array(s._buf)
    dec(s)
    return r


def _to_utf8(s: LeanString) -> object:
    return mk_byte_array(s._buf)


def _get_utf8_byte(s: LeanString, i: int, _h: int) -> int:
    r = _byte_at(s._buf, i)
    dec(s)
    return r


externs = {
    # The proof argument guarantees that `n` is a valid scalar value.
    "Char.ofNatAux": lambda n, _h: n,
    "String.mk": _of_list,
    "String.ofList": _of_list,
    "String.data": _to_list,
    "String.toList": _to_list,
    "String.ofByteArray": _of_byte_array,
    "String.toByteArray": _to_byte_array,
    "String.toUTF8": _to_utf8,
    "String.markLinear": lambda s: s,
    "String.propagateMark": lambda _s, t: t,
    # `Ordering` is `lt`, `eq`, or `gt`, with tags 0, 1, and 2.
    "String.compare": lambda s, t: _compare_bytes(s._buf, 0, len(s._buf), t._buf, 0, len(t._buf))
    + 1,
    "String.getUtf8Byte": _get_utf8_byte,
    "String.get": string_get,
    "String.get!": string_get,
    "String.get'": lambda s, i, _h: _decode_char_at(s._buf, i),
    "String.get?": string_get_opt,
    "String.set": string_set,
    "String.next": string_next,
    "String.next'": lambda s, i, _h: i + _sequence_size(_byte_at(s._buf, i)),
    "String.prev": string_prev,
    "String.atEnd": lambda s, i: _bool(i >= len(s._buf)),
    "String.Slice.hash": _slice_hash,
    "String.Slice.instDecidableLt": _slice_lt,
    "String.hash": lambda s: hash_bytes(s._buf, len(s._buf), 11),
    "String.length": _length,
    "String.utf8ByteSize": lambda s: len(s._buf),
    "String.append": string_append,
    "String.push": string_push,
    "String.decEq": lambda s, t: _bool(string_eq(s, t)),
    "String.decidableLT": lambda s, t: _bool(string_lt(s, t)),
    "String.getUTF8Byte": lambda s, i, _h: _byte_at(s._buf, i),
    "String.decodeChar": lambda s, i, _h: _decode_char_at(s._buf, i),
    "String.extract": lambda s, b, e: _extract_valid(s, b, e) if b < e else mk_string(""),
    "String.Pos.next": lambda s, i, _h: i + _sequence_size(_byte_at(s._buf, i)),
    "String.Pos.set": lambda s, i, c, _h: string_set(s, i, c),
    "String.Pos.Raw.get": string_get,
    "String.Pos.Raw.get!": string_get,
    "String.Pos.Raw.get'": lambda s, i, _h: _decode_char_at(s._buf, i),
    "String.Pos.Raw.get?": string_get_opt,
    "String.Pos.Raw.isValid": lambda s, i: _bool(string_is_valid_pos(s, i)),
    "String.Pos.Raw.next'": lambda s, i, _h: i + _sequence_size(_byte_at(s._buf, i)),
    "String.Pos.Raw.prev": string_prev,
    "String.Pos.Raw.set": string_set,
    "String.Pos.Raw.next": string_next,
    "String.Pos.Raw.atEnd": lambda s, i: _bool(i >= len(s._buf)),
    "String.Pos.Raw.extract": string_extract,
    # Whether `length` bytes of `l` and `r`, starting at `ls` and `rs`, are equal. The proofs
    # guarantee that both ranges are in bounds.
    "String.Slice.Pattern.Internal.memcmpStr": lambda l, r, ls, rs, length, _h1, _h2: _bool(
        _compare_bytes(l._buf, ls, ls + length, r._buf, rs, rs + length) == 0
    ),
    "String.Internal.append": string_append,
    "String.Internal.length": _length,
    "String.Internal.next": string_next,
    "String.Internal.extract": string_extract,
    "String.Internal.atEnd": lambda s, i: _bool(i >= len(s._buf)),
    "String.Internal.get": string_get,
    "String.Internal.getUTF8Byte": lambda s, i, _h: _byte_at(s._buf, i),
    "String.Internal.ugetUTF8Byte": lambda s, i, _h: _byte_at(s._buf, i),
}
