"""Compiles each `tests/fixtures/*.lean` program to Python source, runs it, and compares its
stdout and exit code against the adjacent `.expected` and `.exitcode` files. A missing `.exitcode`
file means the exit code must be 0.

The backend is `python -m leanscript compile <input> -o <output>`, run from the repository root.
The emitted file must start with `import leanscript_runtime as _rt`, as `docs/ir-json.md` requires.

The generated program runs on the target selected by `LEANSCRIPT_TEST_RUNNER`:

- `cpython` (the default): run the source with the current interpreter, with the repository root
  on `PYTHONPATH` so that `leanscript_runtime` resolves to the in-tree package.
- `lpython`: compile the source with `lpython -I <root> -o <executable> <source>` and run the
  executable.

The target is not settled yet; see `docs/refactor-plan.md`. Keeping the runner in one place lets
the suite switch without changing its expectations.

Each program runs in its own empty working directory, with the arguments in the adjacent `.args`
file (one per line) and the contents of the adjacent `.stdin` file as standard input, if those
files exist.

Memory is owned by the target runtime (CPython's or LPython's), so the suite does not check for
reference-count leaks. A fixture fails if the runtime writes a `LeanScript: ` diagnostic to
standard error.

With `--bless`, instead regenerates the `.expected` and `.exitcode` files by compiling each
program with native Lean and running it (`lean --run` is not used because it skips the main
module's initializers).

Usage: python tests/run.py [--bless] [--timeout SECONDS] [name...]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
fixtures = root / "tests" / "fixtures"
build = root / ".lake" / "build" / "tests"
native_dir = build / "native"
work_dir = build / "work"
bin_dir = build / "bin"

# The target convention from `docs/ir-json.md`: every generated module starts with this import.
runtime_header = "import leanscript_runtime as _rt"
# The runtime uses this prefix for diagnostics that do not by themselves change the exit code.
runtime_error_marker = "LeanScript: "
runner = os.environ.get("LEANSCRIPT_TEST_RUNNER", "cpython")
lpython = os.environ.get("LPYTHON", "lpython")
default_timeout = 300.0


def with_runtime_path(env: dict[str, str]) -> dict[str, str]:
    """Puts the repository root first on `PYTHONPATH` and keeps the working tree clean."""
    env["PYTHONPATH"] = str(root) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def backend_env() -> dict[str, str]:
    return with_runtime_path(os.environ.copy())


def remove(path: Path) -> None:
    path.unlink(missing_ok=True)


def backend_available() -> bool:
    probe = subprocess.run(
        [sys.executable, "-c", "import leanscript"],
        cwd=root,
        env=backend_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return probe.returncode == 0


def compile_to_source(
    input_path: Path, source_path: Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "leanscript",
            "compile",
            str(input_path),
            "-o",
            str(source_path),
        ],
        cwd=root,
        env=backend_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


def prepare_execution(
    source_path: Path, exe_path: Path, timeout: float
) -> tuple[list[str] | None, dict[str, str], str | None]:
    """Returns the command prefix and environment for the generated source, or a failure message."""
    if runner == "cpython":
        return [sys.executable, str(source_path)], with_runtime_path(os.environ.copy()), None
    if runner == "lpython":
        remove(exe_path)
        remove(Path(f"{exe_path}.tmp.o"))
        try:
            compiled = subprocess.run(
                [
                    lpython,
                    "--no-color",
                    "-I",
                    str(root),
                    "-o",
                    str(exe_path),
                    str(source_path),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
            )
        except FileNotFoundError:
            return None, {}, f"`{lpython}` was not found; install the pinned compiler"
        except subprocess.TimeoutExpired:
            return None, {}, f"lpython compile timed out after {timeout:g}s"
        if compiled.returncode != 0:
            return None, {}, f"lpython compile failed\n{compiled.stderr}"
        if not exe_path.exists():
            return None, {}, f"lpython compile did not write {exe_path}"
        return [str(exe_path)], os.environ.copy(), None
    return None, {}, f"unknown LEANSCRIPT_TEST_RUNNER '{runner}'; expected 'cpython' or 'lpython'"


def run_program(
    command: list[str],
    env: dict[str, str],
    program_args: list[str],
    stdin: str,
    cwd: Path,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*command, *program_args],
        cwd=cwd,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


def check_runtime_header(source: str) -> str | None:
    """Returns why `source` violates the runtime import convention, or `None` if it does not."""
    first_line = source.splitlines()[0] if source.splitlines() else ""
    if first_line.strip() != runtime_header:
        return f"the emitted source does not start with `{runtime_header}`"
    return None


def check_run(
    label: str, run: subprocess.CompletedProcess[str], expected: str, expected_status: int
) -> bool:
    """Reports whether `run` printed `expected` and exited with `expected_status`, without a
    runtime diagnostic, and returns whether it did."""
    if (
        run.returncode != expected_status
        or run.stdout != expected
        or runtime_error_marker in run.stderr
    ):
        expected_exit = "" if run.returncode == expected_status else f", expected {expected_status}"
        print(f"FAIL {label} (exit {run.returncode}{expected_exit})")
        print(f"--- expected\n{expected}--- actual\n{run.stdout}--- stderr\n{run.stderr}")
        return False
    print(f"ok   {label}")
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Compile the fixtures and check their output and exit codes."
    )
    parser.add_argument("--bless", action="store_true", help="regenerate .expected and .exitcode")
    parser.add_argument(
        "--timeout",
        type=float,
        default=default_timeout,
        metavar="SECONDS",
        help=f"per-program compile and run timeout (default: {default_timeout:g})",
    )
    parser.add_argument("names", nargs="*", help="fixtures to run (default: all)")
    args = parser.parse_args(argv)

    all_names = sorted(path.stem for path in fixtures.glob("*.lean"))
    names = [name for name in all_names if not args.names or name in args.names]

    if not args.bless and not backend_available():
        print("FAIL the backend `leanscript` package is not importable from the repository root")
        return 1

    build.mkdir(parents=True, exist_ok=True)
    if args.bless:
        native_dir.mkdir(parents=True, exist_ok=True)

    failures = 0
    for name in names:
        input_path = fixtures / f"{name}.lean"
        source_path = build / f"{name}.py"
        exe_path = bin_dir / name
        expected_path = fixtures / f"{name}.expected"
        exitcode_path = fixtures / f"{name}.exitcode"
        args_path = fixtures / f"{name}.args"
        stdin_path = fixtures / f"{name}.stdin"
        program_args = (
            args_path.read_text(encoding="utf-8").splitlines() if args_path.exists() else []
        )
        stdin = stdin_path.read_text(encoding="utf-8") if stdin_path.exists() else ""
        cwd = work_dir / name
        shutil.rmtree(cwd, ignore_errors=True)
        cwd.mkdir(parents=True)

        if args.bless:
            native_exe = native_dir / name
            subprocess.run(["lean", "-c", f"{native_exe}.c", str(input_path)], check=True)
            subprocess.run(["leanc", "-o", str(native_exe), f"{native_exe}.c"], check=True)
            native = subprocess.run(
                [str(native_exe), *program_args],
                cwd=cwd,
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            expected_path.write_text(native.stdout, encoding="utf-8")
            if native.returncode == 0:
                remove(exitcode_path)
            else:
                exitcode_path.write_text(f"{native.returncode}\n", encoding="utf-8")
            print(f"blessed {name} (exit {native.returncode})")
            continue

        remove(source_path)
        try:
            compiled = compile_to_source(input_path, source_path, args.timeout)
        except subprocess.TimeoutExpired:
            failures += 1
            print(f"FAIL {name} (compile timed out after {args.timeout:g}s)")
            continue
        if compiled.returncode != 0:
            failures += 1
            print(f"FAIL {name} (compile)\n{compiled.stderr}")
            continue
        if not source_path.exists():
            failures += 1
            print(f"FAIL {name} (compile)\nthe compiler did not write {source_path}")
            continue
        source_error = check_runtime_header(source_path.read_text(encoding="utf-8"))
        if source_error is not None:
            failures += 1
            print(f"FAIL {name} (source)\n{source_error}")
            continue

        bin_dir.mkdir(parents=True, exist_ok=True)
        command, env, prepare_error = prepare_execution(source_path, exe_path, args.timeout)
        if command is None:
            failures += 1
            print(f"FAIL {name} ({runner})\n{prepare_error}")
            continue

        expected = expected_path.read_text(encoding="utf-8") if expected_path.exists() else ""
        expected_status = (
            int(exitcode_path.read_text(encoding="utf-8").strip()) if exitcode_path.exists() else 0
        )
        try:
            ran = run_program(command, env, program_args, stdin, cwd, args.timeout)
        except subprocess.TimeoutExpired:
            failures += 1
            print(f"FAIL {name} (timed out after {args.timeout:g}s)")
            continue
        if not check_run(name, ran, expected, expected_status):
            failures += 1

    if not args.bless:
        print(f"\n{len(names) - failures}/{len(names)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
