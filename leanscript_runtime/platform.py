"""Host services, file handles, and file system operations using the standard library."""

import errno
import os
import stat
import sys
import threading
import time

from .array import mk_array
from .bytearray import mk_byte_array
from .core import Ctor, dec, inc, mark_persistent, track
from .io import attempt
from .stream import decode_bytes, mk_stream, std_stream_externs
from .string import mk_string, to_python

# The stack size of the thread that runs Lean code. Python frames are small, but the generated
# program can recurse deeply, so the thread gets a large stack.
_STACK_SIZE_MB = 256

# The exit code that the program finishes with, set by `set_exit_code`.
_exit_code = 0

# The libuv message for each system error name, which is the text the native Lean runtime reports.
# It differs from `os.strerror` in wording and capitalization.
_libuv_messages = {
    "E2BIG": "argument list too long",
    "EACCES": "permission denied",
    "EADDRINUSE": "address already in use",
    "EADDRNOTAVAIL": "address not available",
    "EAFNOSUPPORT": "address family not supported",
    "EAGAIN": "resource temporarily unavailable",
    "EALREADY": "connection already in progress",
    "EBADF": "bad file descriptor",
    "EBUSY": "resource busy or locked",
    "ECANCELED": "operation canceled",
    "ECHARSET": "invalid Unicode character",
    "ECONNABORTED": "software caused connection abort",
    "ECONNREFUSED": "connection refused",
    "ECONNRESET": "connection reset by peer",
    "EDESTADDRREQ": "destination address required",
    "EEXIST": "file already exists",
    "EFAULT": "bad address in system call argument",
    "EFBIG": "file too large",
    "EFTYPE": "inappropriate file type or format",
    "EHOSTDOWN": "host is down",
    "EHOSTUNREACH": "host is unreachable",
    "EILSEQ": "illegal byte sequence",
    "EINTR": "interrupted system call",
    "EINVAL": "invalid argument",
    "EIO": "i/o error",
    "EISCONN": "socket is already connected",
    "EISDIR": "illegal operation on a directory",
    "ELOOP": "too many symbolic links encountered",
    "EMFILE": "too many open files",
    "EMLINK": "too many links",
    "EMSGSIZE": "message too long",
    "ENAMETOOLONG": "name too long",
    "ENETDOWN": "network is down",
    "ENETUNREACH": "network is unreachable",
    "ENFILE": "file table overflow",
    "ENOBUFS": "no buffer space available",
    "ENODATA": "no data available",
    "ENODEV": "no such device",
    "ENOENT": "no such file or directory",
    "ENOEXEC": "exec format error",
    "ENOMEM": "not enough memory",
    "ENONET": "machine is not on the network",
    "ENOPROTOOPT": "protocol not available",
    "ENOSPC": "no space left on device",
    "ENOSYS": "function not implemented",
    "ENOTCONN": "socket is not connected",
    "ENOTDIR": "not a directory",
    "ENOTEMPTY": "directory not empty",
    "ENOTSOCK": "socket operation on non-socket",
    "ENOTSUP": "operation not supported on socket",
    "ENOTTY": "inappropriate ioctl for device",
    "ENXIO": "no such device or address",
    "EOVERFLOW": "value too large for defined data type",
    "EPERM": "operation not permitted",
    "EPIPE": "broken pipe",
    "EPROTO": "protocol error",
    "EPROTONOSUPPORT": "protocol not supported",
    "EPROTOTYPE": "protocol wrong type for socket",
    "ERANGE": "result too large",
    "EREMOTEIO": "remote I/O error",
    "EROFS": "read-only file system",
    "ESHUTDOWN": "cannot send after transport endpoint shutdown",
    "ESOCKTNOSUPPORT": "socket type not supported",
    "ESPIPE": "invalid seek",
    "ESRCH": "no such process",
    "ETIMEDOUT": "connection timed out",
    "ETXTBSY": "text file is busy",
    "EUNATCH": "protocol driver not attached",
    "EXDEV": "cross-device link not permitted",
}


class HostError(OSError):
    """A host error whose Lean message is known and is not the libuv message for its code."""

    def __init__(self, code, message):
        super().__init__(code, message)
        self.details = message


def _path(p):
    """Returns the C string for the path `p`, rejecting an embedded null byte."""
    if "\0" in p:
        raise HostError(errno.EINVAL, "string contains NUL bytes")
    return p


def write_bytes(fd, data, position=None):
    """Writes all of `data` to the file descriptor `fd`.

    Writes at the file offset `position` if it is given and at the current file offset otherwise.
    """
    view = memoryview(data)
    offset = 0
    size = len(view)
    while offset < size:
        if position is None:
            written = os.write(fd, view[offset:])
        else:
            written = os.pwrite(fd, view[offset:], position)
        offset += written
        if position is not None:
            position += written


def flush_output(_fd):
    """Writes any output held back for the file descriptor `fd`.

    Writes are unbuffered, so there is none.
    """


def write_stderr(s):
    """Writes the string `s` to standard error."""
    write_bytes(2, s.encode("utf-8"))


def is_tty(fd):
    """Returns whether the file descriptor `fd` refers to a terminal."""
    return os.isatty(fd)


def get_env(name):
    """Returns the value of the environment variable `name`, or `None` if it is not set."""
    return os.environ.get(name)


def debug_option(name):
    """Returns whether the debug option `name` is set, as a nonempty environment variable."""
    return bool(os.environ.get(name))


def command_line_args():
    """Returns the arguments the program was run with, without the program name."""
    return sys.argv[1:]


def set_exit_code(code):
    """Records the exit code that the program finishes with."""
    global _exit_code
    _exit_code = code


def exit_process(code):
    """Ends the process immediately with the exit code `code`."""
    raise SystemExit(code)


def process_id():
    """Returns the process identifier."""
    return os.getpid()


def sleep(ms):
    """Blocks the thread for `ms` milliseconds."""
    time.sleep(ms / 1000)


def monotonic_nanos():
    """Returns the time in nanoseconds since an arbitrary point."""
    return time.monotonic_ns()


def run_with_large_stack(run):
    """Runs `run` on a thread with a large stack, then exits with the exit code it set.

    Python frames are smaller than JavaScript frames, but the generated program can recurse deeply,
    so the thread gets a generous stack.
    """
    if threading.current_thread() is not threading.main_thread():
        run()
        exit_process(_exit_code)
        return
    failure = []

    def target():
        try:
            run()
        except BaseException as exc:
            failure.append(exc)

    previous = threading.stack_size(_STACK_SIZE_MB * 1024 * 1024)
    try:
        thread = threading.Thread(target=target)
        thread.start()
    finally:
        threading.stack_size(previous)
    thread.join()
    if failure:
        raise failure[0]
    exit_process(_exit_code)


# The names of the errno values that Python reports under an alias of the name Lean uses.
_errno_aliases = {"EDEADLOCK": "EDEADLK", "EOPNOTSUPP": "ENOTSUP", "EWOULDBLOCK": "EAGAIN"}


def system_error(err):
    """Returns the name, number, and message of the system error `err`.

    Returns `None` if `err` is some other kind of error.
    """
    if not isinstance(err, OSError) or err.errno is None:
        return None
    name = errno.errorcode.get(err.errno)
    if name is None:
        return None
    name = _errno_aliases.get(name, name)
    # libuv reports an error code it does not know with the code as it was passed, which is
    # negated.
    message = getattr(err, "details", None)
    if message is None:
        message = _libuv_messages.get(name, f"Unknown system error {-err.errno}")
    return {"name": name, "errno": err.errno, "message": message}


def open_file(path, flags):
    """Opens the file at `path` with the `fopen`-style `flags`, and returns its file descriptor."""
    return os.open(_path(path), flags, 0o666)


def close_file(fd):
    """Closes the file descriptor `fd`."""
    os.close(fd)


def is_regular_file(fd):
    """Returns whether the file descriptor `fd` refers to a regular file, which supports seeking."""
    return stat.S_ISREG(os.fstat(fd).st_mode)


def read_into(fd, buffer, offset, length, position):
    """Reads up to `length` bytes from `fd` into `buffer` at `offset`.

    Reads from the file offset `position` if it is not `None` and from the current file offset
    otherwise. Returns the number of bytes read, which is 0 only at the end of the file.
    """
    while True:
        try:
            if position is None:
                data = os.read(fd, length)
            else:
                data = os.pread(fd, length, position)
            break
        except BlockingIOError:
            # A descriptor shared with a parent process may be in non-blocking mode, so block
            # ourselves.
            sleep(1)
    buffer[offset : offset + len(data)] = data
    return len(data)


def truncate_file(fd, length):
    """Truncates the file behind `fd` to `length` bytes."""
    os.ftruncate(fd, length)


def make_dir(path):
    """Creates the directory at `path`."""
    os.mkdir(_path(path))


def remove_file(path):
    """Removes the file at `path`."""
    os.unlink(_path(path))


def remove_dir(path):
    """Removes the empty directory at `path`."""
    os.rmdir(_path(path))


def rename_path(from_path, to_path):
    """Renames the path `from_path` to `to_path`."""
    os.rename(_path(from_path), _path(to_path))


def hard_link(target, path):
    """Creates the hard link `path` to the file `target`."""
    os.link(_path(target), _path(path))


def real_path(path):
    """Returns the canonical path of the existing path `path`, with symbolic links resolved."""
    return os.path.realpath(_path(path), strict=True)


def current_dir():
    """Returns the current directory of the process."""
    return os.getcwd()


def change_dir(path):
    """Changes the current directory of the process."""
    try:
        os.chdir(_path(path))
    except ValueError:
        # The path is a string, so the only other error is a path containing a null byte.
        raise OSError(errno.EINVAL, os.strerror(errno.EINVAL)) from None


def read_dir_names(path):
    """Returns the names of the entries of the directory at `path` as bytes, in directory order."""
    return os.listdir(os.fsencode(_path(path)))


def file_metadata(path, follow):
    """Returns the metadata of the file at `path`, following a final symbolic link if `follow`.

    Times are in nanoseconds since the epoch, and the type is `"dir"`, `"file"`, `"symlink"`, or
    `"other"`.
    """
    stats = os.stat(_path(path), follow_symlinks=follow)
    if stat.S_ISDIR(stats.st_mode):
        kind = "dir"
    elif stat.S_ISREG(stats.st_mode):
        kind = "file"
    elif stat.S_ISLNK(stats.st_mode):
        kind = "symlink"
    else:
        kind = "other"
    return {
        "accessed_ns": stats.st_atime_ns,
        "modified_ns": stats.st_mtime_ns,
        "size": stats.st_size,
        "num_links": stats.st_nlink,
        "type": kind,
    }


# The number of bytes `get_line` reads at a time.
_LINE_CHUNK_SIZE = 4096

# The `fopen` mode of each `IO.FS.Mode`.
_OPEN_FLAGS = [
    os.O_RDONLY,
    os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
    os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_EXCL,
    os.O_RDWR,
    os.O_WRONLY | os.O_CREAT | os.O_APPEND,
]


class Handle:
    """An open file, `IO.FS.Handle`.

    Writes are unbuffered, so flushing does nothing. `get_line` may read past the end of the line,
    so reads first consume the bytes it left over. The file is closed when the handle is freed.
    """

    def __init__(self, fd, seekable):
        """Opens a handle on the file descriptor `fd`.

        `seekable` is whether the file supports positioned reads and writes, in which case the
        handle tracks its own position so that it can be rewound.
        """
        self.rc = 1
        self.fd = fd
        # The file offset of the next read or write, or `None` to use the current file offset.
        self.pos = 0 if seekable else None
        # Bytes read past the logical position of the handle, which the next read returns first.
        self.pending = b""
        self._closed = False
        track(self)

    def describe(self):
        """Returns a description of the handle for diagnostics."""
        return f"handle for file descriptor {self.fd}"

    def finalize(self):
        """Closes the file descriptor, if it is not already closed."""
        if not self._closed:
            self._closed = True
            try:
                close_file(self.fd)
            except OSError:
                pass

    def __del__(self):
        # The core runtime does not finalize freed objects, so the collector closes the file.
        # Persistent handles, such as the standard streams, are never closed.
        if self.rc != 0:
            self.finalize()

    def is_tty(self):
        """Returns whether the file descriptor refers to a terminal."""
        return is_tty(self.fd)

    def flush(self):
        """Does nothing, as writes are unbuffered."""

    def _read_file(self, buffer, offset, length):
        """Reads from the file into `buffer` at `offset`, returning the number of bytes read."""
        n = read_into(self.fd, buffer, offset, length, self.pos)
        if self.pos is not None:
            self.pos += n
        return n

    def read(self, n):
        """Reads `n` bytes, or fewer at the end of the file."""
        data = bytearray(min(n, max(len(self.pending), _LINE_CHUNK_SIZE)))
        size = min(n, len(self.pending))
        data[0:size] = self.pending[:size]
        self.pending = self.pending[size:]
        while size < n:
            if size == len(data):
                grown = bytearray(min(n, 2 * len(data)))
                grown[0:size] = data
                data = grown
            read = self._read_file(data, size, len(data) - size)
            if read == 0:
                break
            size += read
        return mk_byte_array(data[:size])

    def get_line(self):
        """Reads up to and including the next newline, or to the end of the file."""
        search_from = 0
        while True:
            end = self.pending.find(b"\n", search_from)
            if end != -1:
                line = self.pending[: end + 1]
                self.pending = self.pending[end + 1 :]
                return line
            search_from = len(self.pending)
            buffer = bytearray(len(self.pending) + _LINE_CHUNK_SIZE)
            buffer[0 : len(self.pending)] = self.pending
            read = self._read_file(buffer, len(self.pending), _LINE_CHUNK_SIZE)
            if read == 0:
                line = self.pending
                self.pending = b""
                return line
            self.pending = bytes(buffer[: len(self.pending) + read])

    def discard_pending(self):
        """Discards any bytes read ahead, so that the file position is the logical one."""
        if self.pos is not None:
            self.pos -= len(self.pending)
        self.pending = b""

    def write(self, data):
        """Writes all of `data` at the logical position of the handle."""
        self.discard_pending()
        write_bytes(self.fd, data, self.pos)
        if self.pos is not None:
            self.pos += len(data)

    def rewind(self):
        """Moves the logical position to the start of the file."""
        if self.pos is not None:
            self.pos = 0
            self.pending = b""

    def truncate(self):
        """Truncates the file at the current position."""
        self.discard_pending()
        truncate_file(self.fd, 0 if self.pos is None else self.pos)


# The `IO.FS.FileType` of each file type reported by the platform.
_file_types = {"dir": 0, "file": 1, "symlink": 2, "other": 3}

_NANOS_PER_SECOND = 1000000000


def _system_time(ns):
    """Returns an `IO.FS.SystemTime` for a time given in nanoseconds since the epoch."""
    return Ctor(0, [ns // _NANOS_PER_SECOND], {8: ns % _NANOS_PER_SECOND})


def _metadata(p, follow):
    """Returns an `IO.FS.Metadata` for the borrowed path `p`, as an `EST.Out`."""

    def build():
        m = file_metadata(to_python(p), follow)
        return Ctor(
            0,
            [_system_time(m["accessed_ns"]), _system_time(m["modified_ns"])],
            {
                16: m["size"],
                24: m["num_links"],
                32: _file_types[m["type"]],
            },
        )

    return attempt(p, build)


def _handle_mk(path, mode, _w):
    def open_handle():
        fd = open_file(to_python(path), _OPEN_FLAGS[mode])
        # Appends ignore the position, so there is no need to track it.
        return Handle(fd, mode != 4 and is_regular_file(fd))

    return attempt(path, open_handle)


def _handle_is_tty(h, _w):
    return 1 if h.is_tty() else 0


def _handle_flush(h, _w):
    return attempt(None, h.flush)


def _handle_rewind(h, _w):
    return attempt(None, h.rewind)


def _handle_truncate(h, _w):
    return attempt(None, h.truncate)


def _handle_read(h, n, _w):
    return attempt(None, lambda: h.read(n))


def _handle_write(h, b, _w):
    return attempt(None, lambda: h.write(b.data))


def _handle_get_line(h, _w):
    return attempt(None, lambda: decode_bytes(h.get_line()))


def _handle_put_str(h, s, _w):
    return attempt(None, lambda: h.write(s.utf8))


def _create_dir(p, _w):
    return attempt(p, lambda: make_dir(to_python(p)))


def _remove_file(p, _w):
    return attempt(p, lambda: remove_file(to_python(p)))


def _remove_dir(p, _w):
    return attempt(p, lambda: remove_dir(to_python(p)))


def _rename(from_path, to_path, _w):
    return attempt(
        from_path, lambda: rename_path(to_python(from_path), to_python(to_path))
    )


def _hard_link(target, link, _w):
    return attempt(target, lambda: hard_link(to_python(target), to_python(link)))


def _real_path(p, _w):
    result = attempt(p, lambda: mk_string(real_path(to_python(p))))
    dec(p)
    return result


def _current_dir(_w):
    return attempt(None, lambda: mk_string(current_dir()))


def _set_current_dir(p, _w):
    return attempt(p, lambda: change_dir(to_python(p)))


def _read_dir(p, _w):
    def build():
        entries = []
        for name in read_dir_names(to_python(p)):
            inc(p)
            entries.append(Ctor(0, [p, decode_bytes(name)], None))
        return mk_array(entries)

    return attempt(p, build)


def _get_pid(_w):
    return process_id()


def _exit(_alpha, code, _w):
    exit_process(code)


def _std_stream(fd):
    return mk_stream(mark_persistent(Handle(fd, False)))


externs = {
    "IO.FS.Handle.mk": _handle_mk,
    "IO.FS.Handle.isTty": _handle_is_tty,
    "IO.FS.Handle.flush": _handle_flush,
    "IO.FS.Handle.rewind": _handle_rewind,
    "IO.FS.Handle.truncate": _handle_truncate,
    "IO.FS.Handle.read": _handle_read,
    "IO.FS.Handle.write": _handle_write,
    "IO.FS.Handle.getLine": _handle_get_line,
    "IO.FS.Handle.putStr": _handle_put_str,
    "IO.FS.createDir": _create_dir,
    "IO.FS.removeFile": _remove_file,
    "IO.FS.removeDir": _remove_dir,
    "IO.FS.rename": _rename,
    "IO.FS.hardLink": _hard_link,
    "IO.FS.realPath": _real_path,
    "IO.currentDir": _current_dir,
    "IO.Process.getCurrentDir": _current_dir,
    "IO.Process.setCurrentDir": _set_current_dir,
    "System.FilePath.readDir": _read_dir,
    "System.FilePath.metadata": lambda p, _w: _metadata(p, True),
    "System.FilePath.symlinkMetadata": lambda p, _w: _metadata(p, False),
    "IO.Process.getPID": _get_pid,
    "IO.Process.exit": _exit,
    "IO.Process.forceExit": _exit,
}

externs.update(std_stream_externs("Stdin", _std_stream(0)))
externs.update(std_stream_externs("Stdout", _std_stream(1)))
externs.update(std_stream_externs("Stderr", _std_stream(2)))
