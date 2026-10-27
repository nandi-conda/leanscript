"""Compiles the LPython subset probes and reports which constructs the pinned compiler accepts.

Each probe in `probes/` isolates one construct that the runtime, the emitter, or generated code
needs. The probe compiles with the pinned LPython and, if it compiles, runs. The output is a
Markdown table with the compiler's diagnostic, which backs the evidence table in
`docs/lpython-subset.md`.

Probes are deliberately small and independent. No probe imports `leanscript_runtime`: the point is
to measure the compiler, not the runtime.

Usage: pixi run python tests/lpython/run_probes.py [--lpython PATH] [name...]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

here = Path(__file__).resolve().parent
probes = here / "probes"

# The construct each probe measures, in the order of the evidence table.
constructs = {
    "class_constructor": "classes: annotated fields, default constructor",
    "class_init": "classes: explicit `__init__`",
    "class_method": "classes: methods",
    "class_param": "classes: struct as function parameter",
    "try_except": "exceptions: `try`/`except`",
    "assert_abort": "exceptions: `assert` abort",
    "exit_code": "exceptions: `sys.exit`",
    "closure": "closures: nested function",
    "lambda": "closures: `lambda`",
    "first_class_function": "closures: function passed as a value",
    "comprehension": "comprehensions: list comprehension",
    "bytearray_bytes": "bytes: `bytearray`",
    "bytes_literal": "bytes: `bytes` literal",
    "file_write": "io: writable file",
    "os_api": "io: `os.makedirs`",
    "os_environ": "io: environment read",
    "os_cwd": "io: current directory",
    "stdin_read": "io: standard input",
    "stderr_write": "io: standard error",
    "argv": "io: `sys.argv`",
    "bare_int": "numbers: bare `int`",
    "dynamic_values": "dynamic values: union annotation",
    "typing_any": "dynamic values: `typing.Any`",
    "heterogeneous_list": "dynamic values: heterogeneous list",
    "dict_typed": "dynamic values: homogeneous typed dict",
    "tagged_cell": "dynamic values: one tagged cell with typed slots",
    "list_of_cells": "dynamic values: list of structs",
    "recursive_cell": "dynamic values: recursive struct",
    "recursion": "recursion: 1000-deep non-tail",
    "string_ascii": "strings: ASCII operations",
    "string_utf8": "strings: UTF-8 bytes",
    "string_escapes": "strings: escape decoding",
}

# Probes whose supported construct ends in a nonzero exit. `sys.exit(3)` and `assert` abort are
# the exit paths, so their exit status is expected rather than a failure.
expected_exit = {"assert_abort": 1, "exit_code": 3}

ansi = re.compile(r"\x1b\[[0-9;]*m")


def diagnostic(completed: subprocess.CompletedProcess[str]) -> str:
    """The compiler's own summary line, with ANSI colors and source spans removed."""
    text = ansi.sub("", completed.stderr or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    exception = next((line for line in lines if line.startswith("LCompilersException:")), None)
    first = next((line for line in lines if line.split(":")[0] in (
        "semantic error", "syntax error", "tokenizer error", "Internal Compiler Error")), "")
    if exception is not None:
        return f"{first} ({exception})" if first else exception
    return first or f"compiler exited {completed.returncode} with no diagnostic"


def check(lpython: str, probe: Path, work: Path) -> tuple[str, str]:
    """Returns the status and detail for one probe."""
    exe = work / (probe.stem + ".out")
    compiled = subprocess.run(
        [lpython, str(probe), "-o", str(exe)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if compiled.returncode < 0:
        return "fail", f"compiler crashed with signal {-compiled.returncode}, no diagnostic"
    if compiled.returncode != 0:
        return "fail", diagnostic(compiled)
    ran = subprocess.run([str(exe)], cwd=work, capture_output=True, timeout=120)
    output = (ran.stdout + ran.stderr).decode("utf-8", "replace").strip()
    want = expected_exit.get(probe.stem, 0)
    if ran.returncode != want:
        return "fail", f"runtime exit {ran.returncode}: {output}"
    detail = output.replace("\n", " / ").replace("|", "\\|")
    if want != 0:
        detail = f"exit {want}: {detail}"
    return "pass", detail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lpython", default=os.environ.get("LPYTHON", "lpython"))
    parser.add_argument("names", nargs="*", help="probe names to run; default: all")
    args = parser.parse_args()

    selected = args.names or list(constructs)
    rows = []
    with tempfile.TemporaryDirectory(prefix="leanscript-lpython-probes-") as tmp:
        work = Path(tmp)
        for name in selected:
            probe = probes / (name + ".py")
            if not probe.exists() or probe.stat().st_size == 0:
                print(f"error: probe {name} is missing or empty", file=sys.stderr)
                return 1
            status, detail = check(args.lpython, probe, work)
            rows.append((name, constructs[name], status, detail))

    print("| Probe | Construct | Result | Output or compiler diagnostic |")
    print("| --- | --- | --- | --- |")
    for name, construct, status, detail in rows:
        print(f"| `{name}.py` | {construct} | {status} | `{detail}` |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
