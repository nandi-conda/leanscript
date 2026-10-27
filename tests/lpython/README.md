# LPython 0.22.0 probes

This directory is evidence for the target decision, not a test suite. LPython 0.22.0 was evaluated
as the transpile target and rejected; the runtime and generated programs run on CPython 3. See
[`docs/refactor-plan.md`](../../docs/refactor-plan.md) for the decision and
[`docs/lpython-subset.md`](../../docs/lpython-subset.md) for the full matrix.

- `probes/` contains one small program per construct. Each probe has a `main()` call and does not
  import `leanscript_runtime`; the matrix measures the compiler, not the runtime.
- `run_probes.py` compiles each probe with the pinned LPython, runs the executable if compilation
  succeeds, and prints a Markdown table with the compiler's diagnostic.

```sh
pixi run python tests/lpython/run_probes.py
```

The current result is 21 failures out of 32 probes, including every probe for dynamic values,
exceptions, closures, bytes, and file or standard IO. Keep the probes and the pin so the rejection
stays reproducible. This directory is not part of `pixi run test`.
