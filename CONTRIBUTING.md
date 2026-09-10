# Contributing to SpaceAI

Thanks for helping out. SpaceAI deletes things for people, so the bar for
changes is a little higher than usual — mostly around the safety layer.

## Getting set up

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

## Before you open a pull request

```bash
ruff check src tests
ruff format src tests
mypy
pytest
```

All four must pass. `mypy` runs in strict mode and the codebase is currently at
zero errors; please keep it there.

## House rules

**Never add a generic command execution tool.** No `run_command(cmd)`, no
`shell=True`, no passing an LLM-authored string to a subprocess. Every operation
the agent can reach must be a named, typed, scoped tool. This is the single
rule that makes the rest of the design meaningful.

**The safety layer is the authority.** `cleanup/safety.py` decides what may be
touched. Nothing else — not the agent, not an analyzer, not a plan — may
conclude a path is safe. If you add a code path that touches the filesystem
destructively, it must call `SafetyPolicy.check_path` first, on the resolved
path, and honour the verdict.

**Resolve before you judge.** Any new path handling must expand `~`, expand
environment variables, collapse `..` and resolve symlinks *before* comparing
against any rule. Comparing the string a user typed is a bug.

**Failures are data.** Filesystem code must not raise for conditions that are
normal on a live system: permission denied, a file that vanished mid-scan, a
locked file, a directory that cannot be opened. Count it, record a sample
message, carry on.

**Keep memory bounded.** The scanner must never accumulate a per-file list.
Bounded heaps and running totals only.

## Adding a platform location

`analyzers/locations.py` is the single place platform knowledge lives. Add an
entry with an honest `is_cache` / `project_data` flag — `is_cache` means the
contents are regenerable, `project_data` means losing them costs real work. The
categoriser and, later, the cleanup planner both key off those flags.

## Adding an analyzer

Analyzers report; they never delete. An analyzer returns findings and, at most,
*proposed* `CleanupAction` objects, which are inert until the safety layer
approves them and a human confirms them.

## Tests

New safety rules need adversarial tests, not just happy-path ones. Look at
`tests/test_safety.py::test_malformed_input_cannot_reach_a_protected_path` for
the shape: a parametrised list of hostile inputs asserting they are all
refused. When you add a rule, add the inputs it was written to defeat.

## Commit messages

Explain the why. A commit that changes a safety rule should say what it now
prevents.
