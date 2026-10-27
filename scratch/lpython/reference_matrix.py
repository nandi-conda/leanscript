"""Print the reference results for `string_matrix.py` from the CPython string module.

Set `LEANSCRIPT_RUNTIME_STUBS` to a directory that provides the package's `core.py` and `hash.py`
when they are not checked in yet; `leanscript_runtime` is a namespace package, so the two
directories merge.

Usage: python scratch/lpython/reference_matrix.py [out.txt]
"""

import os
import sys
from pathlib import Path

stubs = os.environ.get("LEANSCRIPT_RUNTIME_STUBS")
if stubs:
    sys.path.insert(0, stubs)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from leanscript_runtime import string

ex = string.externs
SAMPLES = ["", "a", "héllo", "日本語", "🙂🙂", "aé日🙂z", "abcabc"]
CHARS = [65, 233, 26085, 128578]


def fresh(text):
    return string.mk_string(text)


out = []


def emit(n):
    out.append(int(n))


for text in SAMPLES:
    s = fresh(text)
    emit(len(s.utf8))
    emit(ex["String.length"](s))
    for i in range(len(text.encode("utf-8", "surrogateescape")) + 2):
        emit(ex["String.get"](s, i))
        emit(ex["String.next"](s, i))
        emit(ex["String.prev"](s, i))
        emit(ex["String.Pos.Raw.isValid"](s, i))
        emit(ex["String.Pos.Raw.get'"](s, i, 0))
    n = len(text.encode("utf-8", "surrogateescape"))
    for b in range(n + 2):
        for e in range(n + 2):
            t = ex["String.Pos.Raw.extract"](s, b, e)
            emit(len(t.utf8))
            emit(ex["String.length"](t))
    for i in range(n + 1):
        for c in CHARS:
            u = ex["String.set"](fresh(text), i, c)
            emit(len(u.utf8))
            emit(ex["String.length"](u))
            emit(ex["String.compare"](u, fresh(text)))
    emit(len(ex["String.push"](fresh(text), 26085).utf8))

for a in SAMPLES:
    for b in SAMPLES:
        emit(ex["String.compare"](fresh(a), fresh(b)))
        emit(ex["String.decEq"](fresh(a), fresh(b)))
        emit(ex["String.decidableLT"](fresh(a), fresh(b)))

path = sys.argv[1] if len(sys.argv) > 1 else "reference_matrix.txt"
Path(path).write_text("\n".join(str(x) for x in out) + "\n")
print(len(out))
