// Prints the reference results for `fixed_matrix.py`, computed by the JavaScript runtime.
//
// Usage: node scratch/lpython/fixed_ref.mjs > /tmp/fixed_ref.txt

import { readFileSync } from "node:fs";
import { externs } from "../../src/runtime/fixed.js";

const here = new URL(".", import.meta.url);
const cases = JSON.parse(readFileSync(new URL("fixed_cases.json", here), "utf8"));
const toInput = (c, v) => (c.width >= 64 ? BigInt(v) : Number(v));
const out = [];
for (const c of cases) {
  const fn = externs[`${c.type}.${c.op}`];
  if (!fn) throw new Error(`missing ${c.type}.${c.op}`);
  const a = toInput(c, c.a);
  const b = c.b === null ? undefined : toInput(c, c.b);
  const r = b === undefined ? fn(a) : fn(a, b);
  out.push(BigInt.asIntN(c.width, BigInt(r)).toString());
}
console.log(out.join("\n"));
