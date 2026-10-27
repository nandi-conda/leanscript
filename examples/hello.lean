/-!
The smallest complete program: a `main : IO Unit` that prints through `IO.println`.

It also shows string interpolation with `s!"..."` and structural recursion on `Nat`.
-/

def greet (name : String) : String :=
  s!"Hello, {name}!"

def sumTo : Nat → Nat
  | 0 => 0
  | n + 1 => (n + 1) + sumTo n

def main : IO Unit := do
  IO.println (greet "world")
  IO.println (sumTo 10)
