import Lean
import LeanScript.Collect

/-!
Serializes the program that the emitter needs to JSON.

The IR mentions `Name`s, whose mangled JS names and display strings the emitter uses. They are
interned into a table so that the JSON can refer to them by index, which also keeps name equality
from depending on `Name.toString`.
-/

namespace LeanScript

open Lean IR

private structure NameTable where
  names : Array Name := #[]
  ids : Std.HashMap Name Nat := {}

private abbrev DumpM := StateT NameTable (Except String)

private def jnum (n : Nat) : Json := Json.num (JsonNumber.fromNat n)

/-- Returns the index of `n` in the name table, adding it if it is not there yet. -/
private def nameId (n : Name) : DumpM Nat := do
  let st ← get
  match st.ids[n]? with
  | some i => return i
  | none =>
    let i := st.names.size
    set ({ names := st.names.push n, ids := st.ids.insert n i } : NameTable)
    return i

private partial def dumpIRType : IRType → DumpM Json
  | .float => return Json.str "float"
  | .uint8 => return Json.str "uint8"
  | .uint16 => return Json.str "uint16"
  | .uint32 => return Json.str "uint32"
  | .uint64 => return Json.str "uint64"
  | .usize => return Json.str "usize"
  | .erased => return Json.str "erased"
  | .object => return Json.str "object"
  | .tobject => return Json.str "tobject"
  | .float32 => return Json.str "float32"
  | .tagged => return Json.str "tagged"
  | .void => return Json.str "void"
  | .struct name? types => do
    let nameIdx? ← match name? with
      | some n => some <$> nameId n
      | none => pure none
    let name := nameIdx?.elim Json.null jnum
    return Json.mkObj [
      ("k", Json.str "struct"),
      ("name", name),
      ("types", Json.arr (← types.mapM dumpIRType))]
  | .union name types => do
    return Json.mkObj [
      ("k", Json.str "union"),
      ("name", jnum (← nameId name)),
      ("types", Json.arr (← types.mapM dumpIRType))]

private def dumpArg : Arg → DumpM Json
  | .var x => return Json.mkObj [("k", Json.str "var"), ("x", jnum x.idx)]
  | .erased => return Json.mkObj [("k", Json.str "erased")]

private def dumpCtor (info : CtorInfo) : DumpM Json := do
  return Json.mkObj [
    ("name", jnum (← nameId info.name)),
    ("cidx", jnum info.cidx),
    ("size", jnum info.size),
    ("usize", jnum info.usize),
    ("ssize", jnum info.ssize)]

private def dumpParam (p : Param) : DumpM Json := do
  return Json.mkObj [
    ("x", jnum p.x.idx),
    ("borrow", Json.bool p.borrow),
    ("ty", ← dumpIRType p.ty)]

private partial def dumpExpr : IR.Expr → DumpM Json
  | .ctor info ys => do
    return Json.mkObj [("k", Json.str "ctor"), ("info", ← dumpCtor info),
      ("ys", Json.arr (← ys.mapM dumpArg))]
  | .reset n x =>
    return Json.mkObj [("k", Json.str "reset"), ("n", jnum n), ("x", jnum x.idx)]
  | .reuse x info updtHeader ys => do
    return Json.mkObj [("k", Json.str "reuse"), ("x", jnum x.idx), ("info", ← dumpCtor info),
      ("updtHeader", Json.bool updtHeader), ("ys", Json.arr (← ys.mapM dumpArg))]
  | .proj i x =>
    return Json.mkObj [("k", Json.str "proj"), ("i", jnum i), ("x", jnum x.idx)]
  | .uproj i x =>
    return Json.mkObj [("k", Json.str "uproj"), ("i", jnum i), ("x", jnum x.idx)]
  | .sproj n offset x =>
    return Json.mkObj [("k", Json.str "sproj"), ("n", jnum n), ("offset", jnum offset),
      ("x", jnum x.idx)]
  | .fap c ys => do
    return Json.mkObj [("k", Json.str "fap"), ("c", jnum (← nameId c)),
      ("ys", Json.arr (← ys.mapM dumpArg))]
  | .pap c ys => do
    return Json.mkObj [("k", Json.str "pap"), ("c", jnum (← nameId c)),
      ("ys", Json.arr (← ys.mapM dumpArg))]
  | .ap x ys => do
    return Json.mkObj [("k", Json.str "ap"), ("x", jnum x.idx),
      ("ys", Json.arr (← ys.mapM dumpArg))]
  | .box ty x => do
    return Json.mkObj [("k", Json.str "box"), ("ty", ← dumpIRType ty), ("x", jnum x.idx)]
  | .unbox x =>
    return Json.mkObj [("k", Json.str "unbox"), ("x", jnum x.idx)]
  | .lit (.num v) =>
    return Json.mkObj [("k", Json.str "lit"), ("v", Json.str "num"), ("n", jnum v)]
  | .lit (.str s) =>
    return Json.mkObj [("k", Json.str "lit"), ("v", Json.str "str"), ("s", Json.str s)]
  | .isShared x =>
    return Json.mkObj [("k", Json.str "isShared"), ("x", jnum x.idx)]

mutual

  private partial def dumpAlt : Alt → DumpM Json
    | .ctor info b => do
      return Json.mkObj [("k", Json.str "ctor"), ("info", ← dumpCtor info),
        ("b", ← dumpFnBody b)]
    | .default b => do
      return Json.mkObj [("k", Json.str "default"), ("b", ← dumpFnBody b)]

  private partial def dumpFnBody : FnBody → DumpM Json
    | .vdecl x ty e b => do
      return Json.mkObj [("k", Json.str "vdecl"), ("x", jnum x.idx),
        ("ty", ← dumpIRType ty), ("e", ← dumpExpr e), ("b", ← dumpFnBody b)]
    | .jdecl j xs v b => do
      return Json.mkObj [("k", Json.str "jdecl"), ("j", jnum j.idx),
        ("xs", Json.arr (← xs.mapM dumpParam)), ("v", ← dumpFnBody v), ("b", ← dumpFnBody b)]
    | .set x i y b => do
      return Json.mkObj [("k", Json.str "set"), ("x", jnum x.idx), ("i", jnum i),
        ("y", ← dumpArg y), ("b", ← dumpFnBody b)]
    | .setTag x cidx b => do
      return Json.mkObj [("k", Json.str "setTag"), ("x", jnum x.idx), ("cidx", jnum cidx),
        ("b", ← dumpFnBody b)]
    | .uset x i y b => do
      return Json.mkObj [("k", Json.str "uset"), ("x", jnum x.idx), ("i", jnum i),
        ("y", jnum y.idx), ("b", ← dumpFnBody b)]
    | .sset x i offset y _ b => do
      return Json.mkObj [("k", Json.str "sset"), ("x", jnum x.idx), ("i", jnum i),
        ("offset", jnum offset), ("y", jnum y.idx), ("b", ← dumpFnBody b)]
    | .inc x n c persistent b => do
      return Json.mkObj [("k", Json.str "inc"), ("x", jnum x.idx), ("n", jnum n),
        ("c", Json.bool c), ("persistent", Json.bool persistent), ("b", ← dumpFnBody b)]
    | .dec x n c persistent b => do
      return Json.mkObj [("k", Json.str "dec"), ("x", jnum x.idx), ("n", jnum n),
        ("c", Json.bool c), ("persistent", Json.bool persistent), ("b", ← dumpFnBody b)]
    | .del x b => do
      return Json.mkObj [("k", Json.str "del"), ("x", jnum x.idx), ("b", ← dumpFnBody b)]
    | .case tid x xType alts => do
      return Json.mkObj [("k", Json.str "case"), ("tid", jnum (← nameId tid)),
        ("x", jnum x.idx), ("xt", ← dumpIRType xType),
        ("alts", Json.arr (← alts.mapM dumpAlt))]
    | .ret y => do
      return Json.mkObj [("k", Json.str "ret"), ("y", ← dumpArg y)]
    | .jmp j ys => do
      return Json.mkObj [("k", Json.str "jmp"), ("j", jnum j.idx),
        ("ys", Json.arr (← ys.mapM dumpArg))]
    | .unreachable => return Json.mkObj [("k", Json.str "unreachable")]

end

private def dumpDecl (env : Environment) (decl : Decl) : DumpM Json := do
  let name ← nameId decl.name
  let initFnIdx? ← match getInitFnNameFor? env decl.name with
    | some n => some <$> nameId n
    | none => pure none
  let initFn := initFnIdx?.elim Json.null jnum
  let params := Json.arr (← decl.params.mapM dumpParam)
  match decl with
  | .fdecl _ _ ty body _ => do
    return Json.mkObj [
      ("k", Json.str "fdecl"),
      ("name", jnum name),
      ("params", params),
      ("ty", ← dumpIRType ty),
      ("body", ← dumpFnBody body),
      ("initFn", initFn)]
  | .extern .. =>
    return Json.mkObj [
      ("k", Json.str "extern"),
      ("name", jnum name),
      ("params", params),
      ("initFn", initFn)]

/--
Returns the JSON program that the emitter consumes: the declarations reachable from `main`, their
aliases, the initializers, and the name table.
-/
def programJson (env : Environment) : Except String Json := do
  let some mainDecl := findEnvDecl env `main | throw "no `main` function found"
  let inits := initDecls env
  -- `IO Unit` initializers always run for their side effects, but an `[init]` declaration is only
  -- initialized if it is used. The runtime uses `IO.Error.toString` to report uncaught errors.
  let ioUnitInits := inits.filter fun n => (getInitFnNameFor? env n).isNone
  let roots := #[`main, `IO.Error.toString] ++ ioUnitInits
  let program ← collectReachable env roots
  let dump : DumpM Json := do
    let decls := Json.arr (← program.decls.mapM (dumpDecl env))
    let aliases := Json.arr (← program.aliases.mapM fun (ext, impl) => do
      return Json.arr #[jnum (← nameId ext), jnum (← nameId impl)])
    let inits := Json.arr (← inits.mapM fun n => do return jnum (← nameId n))
    let mainIdx ← nameId `main
    let errorToString ← nameId `IO.Error.toString
    -- The table is complete now, so its entries can name themselves.
    let names ← (← get).names.mapM fun n => do
      return Json.mkObj [
        ("str", Json.str n.toString),
        ("js", Json.str (n.mangle "l_")),
        ("display", Json.str ((privateToUserName? n).getD n).toString)]
    return Json.mkObj [
      ("version", jnum 1),
      ("names", Json.arr names),
      ("decls", decls),
      ("aliases", aliases),
      ("inits", inits),
      ("main", jnum mainIdx),
      ("mainArity", jnum mainDecl.params.size),
      ("errorToString", jnum errorToString)]
  let (json, _) ← dump.run {}
  return json

end LeanScript
