# Security Policy

## Reporting a vulnerability

Please report security issues privately, through GitHub's *Report a
vulnerability* flow on the repository's Security tab, rather than opening a
public issue. Include the version, your platform, and the smallest input that
demonstrates the problem.

Anything that lets SpaceAI touch a path the safety layer should have refused is
a security issue, not a bug report.

## Threat model

SpaceAI's premise is that a language model will eventually be wrong, confused,
or manipulated, and that this must not be enough to cost anyone their data. The
model is treated as an untrusted source of *suggestions*.

Threats the design takes seriously:

| Threat | Mitigation |
| --- | --- |
| The model proposes deleting a system path | The safety layer refuses protected roots and their contents; the model has no vote |
| The model proposes a path traversal (`../../etc`) | Paths are resolved before they are judged, so the traversal is evaluated at its destination |
| A symlink or junction points somewhere protected | Paths are fully resolved; the scanner does not follow links at all by default |
| Prompt injection from a filename or file content | Filenames reach the model as data; the only privileged surface is the tool schema, which cannot express an arbitrary command |
| The model claims an action is safe | A declared risk level can only be raised by the policy, never lowered, and anything above the configured ceiling is refused |
| A Windows path is passed on a POSIX host | Drive-letter and UNC paths are refused outright rather than silently resolved relative to the working directory |
| The user's API key leaking into logs or scan records | Keys come from the environment and are excluded from every serialisation of the settings object |
| A reparse loop hanging the scanner | Links are not followed, and a hard depth guard bounds traversal regardless |

Out of scope: an attacker who already has code execution as the user, or who
can modify SpaceAI's own source. SpaceAI is not a sandbox.

## The rule that holds it together

**There is no generic command execution tool, and there never will be.**

The agent is only ever given narrow, typed, individually reviewed tools. A
`run_command(cmd)` tool — or any code path that hands an LLM-authored string to
a shell — would make every other control in this document decorative. A pull
request adding one will be rejected on principle.

## Current state

This build contains no destructive code path at all: nothing in SpaceAI calls
`unlink`, `rmtree`, or any deletion API. Cleanup execution arrives in a later
milestone, gated behind the safety layer and an explicit confirmation prompt,
with a preview of exactly which paths are affected shown first.
