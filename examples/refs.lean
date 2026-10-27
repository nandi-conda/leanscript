/-!
Mutable state: a module-level `initialize` reference, local `IO.Ref`s, a scoped `ST.Ref`, and
exceptions caught with `try`/`catch`.
-/

initialize counter : IO.Ref Nat ← IO.mkRef 0

def bump : IO Nat := counter.modifyGet fun n => (n, n + 1)

/-- Sums `1..n` in a reference scoped by `runST`. -/
def sumWithRef (n : Nat) : Nat := runST fun σ => do
  let r : ST.Ref σ Nat ← ST.mkRef 0
  for i in [1:n+1] do
    r.modify (· + i)
  r.get

def main : IO Unit := do
  IO.println s!"{← bump} {← bump} {← bump} {← counter.get}"
  let ref ← IO.mkRef (#[] : Array String)
  for w in ["a", "b", "c"] do
    ref.modify (·.push w)
  let old ← ref.swap #["z"]
  IO.println s!"{old} {← ref.get}"
  IO.println (sumWithRef 10)
  try
    let r ← IO.mkRef 0
    r.set 5
    throw (IO.userError s!"failed with {← r.get}")
  catch e =>
    IO.println s!"caught: {e}"
