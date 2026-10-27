"""Checks the `leanscript-ir dump-json` boundary against `docs/ir-json.md`.

The JSON document is the contract between the Lean frontend and the backend. This test checks the
parts of that contract the backend relies on: one compact object on standard output, schema version
1, a name table, and indexes that stay inside it. With `-o`, standard output must stay empty and the
file must hold the same bytes without a trailing newline.

Usage: python tests/ir_json.py [file.lean]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
default_input = root / "tests" / "fixtures" / "Hello.lean"


def find_dumper() -> str:
    """Finds the Lean frontend the same way `leanscript.cli` does."""
    configured = os.environ.get("LEANSCRIPT_IR")
    if configured:
        return configured
    candidate = root / ".lake" / "build" / "bin" / "leanscript-ir"
    if candidate.is_file():
        return str(candidate)
    found = shutil.which("leanscript-ir")
    if found is not None:
        return found
    return str(candidate)


def is_int(value: object) -> bool:
    """Reports whether `value` is a JSON number with no fractional part, excluding booleans."""
    return isinstance(value, int) and not isinstance(value, bool)


def check_document(document: object) -> list[str]:
    """Returns every violation of the top-level contract in `document`."""
    if not isinstance(document, dict):
        return ["the document is not a JSON object"]
    errors = []
    fields = ("version", "names", "decls", "aliases", "inits", "main", "mainArity", "errorToString")
    for key in fields:
        if key not in document:
            errors.append(f"missing field `{key}`")
    if errors:
        return errors
    if not is_int(document["version"]) or document["version"] != 1:
        errors.append(f"schema version is {document['version']!r}, expected 1")
    names = document["names"]
    if not isinstance(names, list) or not names:
        errors.append("`names` is not a nonempty array")
        return errors
    for index, name in enumerate(names):
        if not isinstance(name, dict) or any(
            not isinstance(name.get(field), str) for field in ("str", "js", "display")
        ):
            errors.append(f"name {index} does not have string fields `str`, `js`, and `display`")

    def check_index(where: str, index: object) -> None:
        if not is_int(index) or not 0 <= index < len(names):
            errors.append(f"{where} is not a name index: {index!r}")

    check_index("`main`", document["main"])
    check_index("`errorToString`", document["errorToString"])
    if is_int(document["main"]) and 0 <= document["main"] < len(names):
        main_name = names[document["main"]]
        if not isinstance(main_name, dict) or main_name.get("str") != "main":
            errors.append("`main` does not point at the name `main`")
    if not is_int(document["mainArity"]):
        errors.append("`mainArity` is not a number")
    if not isinstance(document["decls"], list):
        errors.append("`decls` is not an array")
    else:
        for index, decl in enumerate(document["decls"]):
            if not isinstance(decl, dict):
                errors.append(f"decl {index} is not an object")
                continue
            if decl.get("k") not in ("fdecl", "extern"):
                errors.append(f"decl {index} has unknown kind {decl.get('k')!r}")
            check_index(f"decl {index} name", decl.get("name"))
            init = decl.get("initFn")
            if init is not None:
                check_index(f"decl {index} initFn", init)
            if not isinstance(decl.get("params"), list):
                errors.append(f"decl {index} has no parameter array")
        declared = {
            decl.get("name") for decl in document["decls"] if isinstance(decl, dict)
        }
        for field in ("main", "errorToString"):
            if is_int(document[field]) and document[field] not in declared:
                errors.append(f"`{field}` is not among the declarations")
    if not isinstance(document["aliases"], list):
        errors.append("`aliases` is not an array")
    else:
        for index, pair in enumerate(document["aliases"]):
            if not isinstance(pair, list) or len(pair) != 2:
                errors.append(f"alias {index} is not a pair")
                continue
            check_index(f"alias {index} extern", pair[0])
            check_index(f"alias {index} implementation", pair[1])
    if not isinstance(document["inits"], list):
        errors.append("`inits` is not an array")
    else:
        for index, name_index in enumerate(document["inits"]):
            check_index(f"init {index}", name_index)
    return errors


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check the `dump-json` contract.")
    parser.add_argument("file", nargs="?", default=str(default_input), help="a Lean source file")
    input_path = Path(parser.parse_args(argv).file)
    dumper = find_dumper()
    if not Path(dumper).exists():
        print(f"FAIL the Lean dumper `{dumper}` was not found; build it or set LEANSCRIPT_IR")
        return 1

    try:
        dumped = subprocess.run(
            [dumper, "dump-json", str(input_path)],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as error:
        print(f"FAIL could not run `{dumper}`: {error}")
        return 1
    if dumped.returncode != 0:
        print(f"FAIL dump-json exited with {dumped.returncode}\n{dumped.stderr}")
        return 1
    if not dumped.stdout.endswith("\n") or "\n" in dumped.stdout[:-1]:
        print("FAIL standard output is not one JSON document on one line")
        return 1
    try:
        document = json.loads(dumped.stdout)
    except json.JSONDecodeError as error:
        print(f"FAIL standard output is not JSON: {error}")
        return 1
    errors = check_document(document)
    if errors:
        print("FAIL the document violates docs/ir-json.md:")
        for error in errors:
            print(f"  {error}")
        return 1

    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "program.json"
        written = subprocess.run(
            [dumper, "dump-json", str(input_path), "-o", str(output)],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if written.returncode != 0:
            print(f"FAIL dump-json -o exited with {written.returncode}\n{written.stderr}")
            return 1
        if written.stdout != "":
            print("FAIL standard output is not empty when -o is given")
            return 1
        contents = output.read_text(encoding="utf-8")
        if contents != dumped.stdout[:-1]:
            print("FAIL the file written by -o differs from standard output")
            return 1

    print(f"ok   {input_path.name} (schema version 1)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
