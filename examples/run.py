"""Compile and run one of the programs in `examples/`.

Usage: `pixi run example <name>`.
"""

from __future__ import annotations

import os
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
    return f"usage: pixi run example <name>\n\nexamples: {', '.join(available())}"


def main(argv: list[str]) -> int:
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
    # The generated source imports `leanscript_runtime` from the repository root.
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(root) if not existing else str(root) + os.pathsep + existing
    return subprocess.run([sys.executable, str(target)], cwd=root, env=env).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
