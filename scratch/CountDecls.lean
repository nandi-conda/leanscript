import LeanScript
open Lean LeanScript IR

def main : IO Unit := do
  let env ← elabFile "tests/fixtures/Hello.lean" `Hello
  let decls := getDecls env
  IO.println s!"decls: {decls.length}"
  let bodies := decls.filter fun d => match d with | .fdecl (body := b) .. => b != .unreachable | _ => false
  IO.println s!"with bodies: {bodies.length}"
  IO.println s!"modules: {env.header.moduleNames.size}"
