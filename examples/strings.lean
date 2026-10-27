/-!
Strings are UTF-8: `length` counts characters, while `utf8ByteSize` counts bytes. The operations
below use the core library only.
-/

def main : IO Unit := do
  let s := "héllo, wörld 👋"
  IO.println s
  IO.println s.length
  IO.println s.utf8ByteSize
  IO.println s.toUpper
  IO.println (s.toList.reverse |> String.ofList)
  IO.println (", ".intercalate ["a", "b", "c"])
  IO.println ("a-b-c".splitOn "-")
  IO.println ("  padded  ".trimAscii)
  IO.println (decide ("abc" < "abd"))
  IO.println ("abc" == "ab" ++ "c")
  IO.println ('x'.toNat)
  let mut acc := ""
  for i in [0:5] do
    acc := acc ++ toString i
  IO.println acc
