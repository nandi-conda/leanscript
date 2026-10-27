"""The `leanscript` command line interface."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .emit import EmitError, emit_program
from .ir import Program, ProgramError, load_program

usage = """usage:
  leanscript compile <file.lean> [-o <out.py>] [--allow-unavailable]
  leanscript dump-ir <file.lean>
  leanscript list-externs <file.lean>"""


class CliError(Exception):
    """The command line cannot be run as given."""


class Exit(Exception):
    """The command has finished with the given status."""

    def __init__(self, status: int):
        self.status = status


@dataclass
class CompileArgs:
    input: Path
    output: Path | None = None
    allow_unavailable: bool = False


def project_root() -> Path:
    """Returns the root of the leanscript project."""
    return Path(__file__).resolve().parent.parent


def leanscript_ir() -> str:
    """Returns the command that runs the Lean frontend."""
    override = os.environ.get("LEANSCRIPT_IR")
    if override:
        return override
    candidate = project_root() / ".lake" / "build" / "bin" / "leanscript-ir"
    if candidate.is_file():
        return str(candidate)
    found = shutil.which("leanscript-ir")
    if found is not None:
        return found
    raise CliError("cannot find `leanscript-ir`; build it with `lake build`")


def parse_compile_args(input: Path, rest: list[str]) -> CompileArgs:
    args = CompileArgs(input)
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg == "-o" and i + 1 < len(rest):
            args.output = Path(rest[i + 1])
            i += 2
        elif arg == "--allow-unavailable":
            args.allow_unavailable = True
            i += 1
        else:
            raise CliError(f"unexpected argument '{arg}'")
    return args


def dump_program(input: Path) -> Program:
    """Runs the Lean frontend and loads the program it dumps."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as file:
        temporary = Path(file.name)
    try:
        process = subprocess.run(
            [leanscript_ir(), "dump-json", str(input.resolve()), "-o", str(temporary)],
            cwd=project_root(),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if process.returncode != 0:
            sys.stderr.write(process.stderr)
            raise Exit(1)
        try:
            data = json.loads(temporary.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            raise CliError(f"malformed IR JSON: {err}") from err
        return load_program(data)
    finally:
        temporary.unlink(missing_ok=True)


def describe_unavailable(program: Program, paths: tuple[tuple[int, ...], ...]) -> str:
    lines = "\n".join(
        "  " + " → ".join(program.names[n].display for n in path) for path in paths
    )
    return "the program uses externs that the runtime does not implement:\n" + lines


def compile_module(args: CompileArgs) -> int:
    program = dump_program(args.input)
    try:
        output = emit_program(program)
    except EmitError as err:
        raise CliError(str(err)) from err
    if output.unavailable:
        message = describe_unavailable(program, output.unavailable)
        if args.allow_unavailable:
            print(f"warning: {message}\nThese externs raise when called.", file=sys.stderr)
        else:
            print(
                f"error: {message}\n"
                "Compile with `--allow-unavailable` to make them raise when called instead.",
                file=sys.stderr,
            )
            return 1
    path = args.output
    if path is None:
        path = args.input.with_suffix(".py")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output.source, encoding="utf-8")
    return 0


def run_frontend(command: str, path: Path) -> int:
    return subprocess.run(
        [leanscript_ir(), command, str(path.resolve())], cwd=project_root()
    ).returncode


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) == 2 and args[0] in ("dump-ir", "list-externs"):
            return run_frontend(args[0], Path(args[1]))
        if args and args[0] == "compile" and len(args) >= 2:
            return compile_module(parse_compile_args(Path(args[1]), args[2:]))
        print(usage, file=sys.stderr)
        return 1
    except CliError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    except Exit as done:
        return done.status
    except ProgramError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
