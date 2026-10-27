import LeanScript

open Lean LeanScript

def usage : String :=
  "usage:
  leanscript-ir dump-json <file.lean> [-o <out.json>]
  leanscript-ir dump-ir <file.lean>
  leanscript-ir list-externs <file.lean>"

def moduleNameFor (path : System.FilePath) : Name :=
  (path.fileStem.getD "Main").toName

def dumpIr (path : System.FilePath) : IO UInt32 := do
  let env ← elabFile path (moduleNameFor path)
  IO.println (dumpIrDecls env).pretty
  return 0

def listExterns (path : System.FilePath) : IO UInt32 := do
  let env ← elabFile path (moduleNameFor path)
  match collectReachable env #[`main, `IO.Error.toString] with
  | .error err =>
    IO.eprintln s!"error: {err}"
    return 1
  | .ok program =>
    for decl in program.decls do
      if decl.isExtern then
        IO.println (format decl).pretty
    return 0

/-- Writes the JSON program that the Python emitter consumes. -/
def program (path : System.FilePath) (output? : Option System.FilePath) : IO UInt32 := do
  let env ← elabFile path (moduleNameFor path)
  match programJson env with
  | .error err =>
    IO.eprintln s!"error: {err}"
    return 1
  | .ok json =>
    match output? with
    | some output => IO.FS.writeFile output json.compress
    | none => IO.println json.compress
    return 0

def main (args : List String) : IO UInt32 := do
  match args with
  | ["dump-json", path] => program path none
  | ["dump-json", path, "-o", output] => program path (some output)
  | ["dump-ir", path] => dumpIr path
  | ["list-externs", path] => listExterns path
  | _ =>
    IO.eprintln usage
    return 1
