"""`IO` results and errors, and `IO` actions that do not involve files."""

import os

from .bytearray import mk_byte_array
from .core import Ctor, inc
from .string import mk_string, to_python


def _platform():
    """Returns the platform module, imported on first use so that the import graph stays acyclic."""
    from . import platform

    return platform


def io_ok(a):
    """Returns a successful `EST.Out`. Its `Void σ` field is erased, so it has a single field."""
    return Ctor(0, [a], None)


def io_error(e):
    """Returns a failed `EST.Out`."""
    return Ctor(1, [e], None)


# The `IO.Error` constructor that `lean_decode_io_error` uses for each error name, other than
# `otherError`.
_error_kinds = {
    "alreadyExists": ["EEXIST", "EINPROGRESS", "EISCONN"],
    "resourceBusy": ["EADDRINUSE", "EBUSY", "EDEADLK", "ETXTBSY"],
    "resourceVanished": ["ECONNRESET", "EIDRM", "ENETDOWN", "ENETRESET", "ENOLINK", "EPIPE"],
    "unsupportedOperation": [
        "EADDRNOTAVAIL",
        "EAFNOSUPPORT",
        "ENODEV",
        "ENOPROTOOPT",
        "ENOSYS",
        "ENOTSUP",
        "EOPNOTSUPP",
        "ERANGE",
        "ESPIPE",
        "EXDEV",
    ],
    "hardwareFault": ["EIO"],
    "unsatisfiedConstraints": ["ENOTEMPTY"],
    "illegalOperation": ["ENOTTY"],
    "protocolError": ["EBADMSG", "EPROTO", "EPROTONOSUPPORT", "EPROTOTYPE"],
    "timeExpired": ["ETIME", "ETIMEDOUT"],
    "interrupted": ["EINTR"],
    "noFileOrDirectory": ["ENOENT"],
    "invalidArgument": [
        "EBADF",
        "EDESTADDRREQ",
        "EDOM",
        "EILSEQ",
        "EINVAL",
        "ELOOP",
        "ENAMETOOLONG",
        "ENOEXEC",
        "ENOSTR",
        "ENOTCONN",
        "ENOTSOCK",
    ],
    "permissionDenied": ["EACCES", "ECONNABORTED", "EFBIG", "EPERM", "EROFS"],
    "resourceExhausted": [
        "E2BIG",
        "EAGAIN",
        "EMFILE",
        "EMLINK",
        "EMSGSIZE",
        "ENFILE",
        "ENOBUFS",
        "ENOLCK",
        "ENOMEM",
        "ENOSPC",
        "ENOSR",
        "EWOULDBLOCK",
    ],
    "inappropriateType": ["EISDIR", "ENOTDIR"],
    "noSuchThing": [
        "ECHILD",
        "ECONNREFUSED",
        "EHOSTUNREACH",
        "ENETUNREACH",
        "ENODATA",
        "ENOMSG",
        "ENXIO",
        "ESRCH",
    ],
}

_error_kind_of = {
    name: kind for kind, names in _error_kinds.items() for name in names
}

# Error messages for the errors whose message in the C runtime differs from the one the host
# reports, because the C runtime translates them to a related error first.
_error_messages = {
    "EBADMSG": "protocol error",
    "ECHILD": "no such process",
    "EDEADLK": "resource busy or locked",
    "EDOM": "invalid argument",
    "EIDRM": "broken pipe",
    "EINPROGRESS": "socket is already connected",
    "ENETRESET": "connection reset by peer",
    "ENOEXEC": "Unknown system error -8",
    "ENOLCK": "resource temporarily unavailable",
    "ENOLINK": "connection reset by peer",
    "ENOMSG": "no data available",
    "ENOSR": "no buffer space available",
    "ENOSTR": "invalid argument",
    "ETIME": "connection timed out",
}

# The constructor index of each `IO.Error` constructor.
_error_tags = {
    "alreadyExists": 0,
    "otherError": 1,
    "resourceBusy": 2,
    "resourceVanished": 3,
    "unsupportedOperation": 4,
    "hardwareFault": 5,
    "unsatisfiedConstraints": 6,
    "illegalOperation": 7,
    "protocolError": 8,
    "timeExpired": 9,
    "interrupted": 10,
    "noFileOrDirectory": 11,
    "invalidArgument": 12,
    "permissionDenied": 13,
    "resourceExhausted": 14,
    "inappropriateType": 15,
    "noSuchThing": 16,
}

# The error kinds whose `IO.Error` constructor takes the filename directly.
_plain_filename_kinds = ("interrupted", "noFileOrDirectory")

# The error kinds whose `IO.Error` constructor takes an `Option String` filename.
_option_filename_kinds = (
    "alreadyExists",
    "invalidArgument",
    "permissionDenied",
    "resourceExhausted",
    "inappropriateType",
    "noSuchThing",
)


def decode_io_error(err, fname):
    """Converts the host error `err` to an `IO.Error`, like `lean_decode_io_error`.

    Re-raises `err` if it is not a system error. `fname` is the borrowed name of the file involved,
    or `None`.
    """
    sys_err = _platform().system_error(err)
    if sys_err is None:
        raise err
    kind = _error_kind_of.get(sys_err["name"], "otherError")
    tag = _error_tags[kind]
    details = mk_string(_error_messages.get(sys_err["name"], sys_err["message"]))
    if kind in _plain_filename_kinds:
        name = mk_string("") if fname is None else fname
        return Ctor(tag, [name, details], {16: sys_err["errno"]})
    if kind in _option_filename_kinds:
        name = 0 if fname is None else Ctor(1, [fname], None)
        return Ctor(tag, [name, details], {16: sys_err["errno"]})
    return Ctor(tag, [details], {8: sys_err["errno"]})


def attempt(fname, f):
    """Calls `f` and returns its result as an `EST.Out`, converting a host error to an `IO.Error`.

    `fname` is the borrowed name of the file involved, if any. A result of `None` is returned as
    `Unit`.
    """
    try:
        result = f()
    except OSError as err:
        error = decode_io_error(err, fname)
        if fname is not None:
            inc(fname)
        return io_error(error)
    return io_ok(0 if result is None else result)


def _get_env(name, _w):
    value = _platform().get_env(to_python(name))
    return 0 if value is None else Ctor(1, [mk_string(value)], None)


def _mono_ms_now(_w):
    return _platform().monotonic_nanos() // 1000000


def _mono_nanos_now(_w):
    return _platform().monotonic_nanos()


def _get_random_bytes(n, _w):
    return io_ok(mk_byte_array(os.urandom(n)))


def _is_windows(_unit):
    return 0


def _is_osx(_unit):
    return 0


def _is_emscripten(_unit):
    return 0


# `BaseIO` results are not wrapped in `EST.Out`.
externs = {
    "IO.getEnv": _get_env,
    "IO.monoMsNow": _mono_ms_now,
    "IO.monoNanosNow": _mono_nanos_now,
    "IO.getRandomBytes": _get_random_bytes,
    "System.Platform.getIsWindows": _is_windows,
    "System.Platform.getIsOSX": _is_osx,
    "System.Platform.getIsEmscripten": _is_emscripten,
}
