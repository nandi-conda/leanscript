/-!
`Array` operations: building by repeated `push`, `foldl`, `map`, `set!`, `reverse`, `qsort`, and
`contains`. Array indexing is bounds checked; `xs[i]!` panics on an out-of-range index.
-/

def squares (n : Nat) : Array Nat := Id.run do
  let mut xs : Array Nat := #[]
  for i in [0:n] do
    xs := xs.push (i * i)
  return xs

def main : IO Unit := do
  let xs := squares 10
  IO.println xs
  IO.println xs.size
  IO.println (xs.foldl (· + ·) 0)
  IO.println (xs.map (· + 1) |>.toList)
  let ys := xs.set! 0 100
  IO.println (xs[0]!, ys[0]!)
  IO.println (xs.reverse)
  IO.println (#[3, 1, 2].qsort (· < ·))
  IO.println (xs.contains 49)
