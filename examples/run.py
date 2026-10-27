"""Compile and run one of the programs in `examples/`.

The compiler emits ordinary CPython 3 source, so the result runs with `sys.executable`, never
`lpython`. Each run recompiles the source into the target path and runs the result, so a stale
file is never run.

Usage: `pixi run example <name>` to compile and run, `pixi run transpile <name>` to compile only.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

examples = Path(__file__).resolve().parent
root = examples.parent
build = root / ".lake" / "build" / "examples"


def available() -> list[str]:
    """Returns the names of the examples, sorted."""
    return sorted(path.stem for path in examples.glob("*.lean"))


def usage() -> str:
    return (
        "usage: pixi run example <name>\n"
        "       pixi run transpile <name>\n"
        f"\nexamples: {', '.join(available())}"
    )


def main(argv: list[str]) -> int:
    run = True
    if argv and argv[0] == "--no-run":
        run = False
        argv = argv[1:]
    if len(argv) != 1:
        print(usage(), file=sys.stderr)
        return 2
    name = argv[0]
    source = examples / f"{name}.lean"
    if not source.is_file():
        print(f"error: unknown example '{name}'\n\n{usage()}", file=sys.stderr)
        return 2
    target = build / f"{name}.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    compile_command = [
        sys.executable,
        "-m",
        "leanscript",
        "compile",
        str(source),
        "-o",
        str(target),
    ]
    compiled = subprocess.run(compile_command, cwd=root)
    if compiled.returncode != 0:
        return compiled.returncode
    if not run:
        print(f"wrote {target.relative_to(root)}")
        return 0
    return subprocess.run([sys.executable, str(target)], cwd=root).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
