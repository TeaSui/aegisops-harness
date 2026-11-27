# Spec compliance reviewer template (per ticket)

Send to `aegisops-harness:code-reviewer` (or `general-purpose`). Fill every `[…]`.

```
description: "Spec compliance review T<n>"
prompt: |
  AXIS: spec
  Check whether the implementation matches what was requested: nothing missing, nothing extra.

  ## Requested
  [ticket + the covered stories from spec.md + the Implementation and Testing Decisions they depend on]

  ## Scope
  [committed range | pending Git work | non-Git manifest; owned paths; checked state; untracked, deleted, renamed files; evidence logs]
  Pending work: read staged and unstaged diffs plus the listed untracked files; never substitute HEAD~1..HEAD. Files drift during review → name the affected scope; do not certify an unreviewed state.

  ## Implementer's claim
  [from its report]

  The claim is unverified. Read the actual code and compare it with each criterion line by line. Look for:
  - missing: criteria not implemented, or claimed but absent
  - extra: unrequested features, over-engineering
  - misread: a story or decision interpreted differently or solved the wrong way
  - traceability: each criterion has a test named with its story ID that checks the stated behavior through the agreed seam; no test cites an ID it does not check; no test of internals

  Report every discrepancy, uncertain or minor ones included, each with file:line and confidence; do not filter.
  Status: DONE when everything matches after inspection; BLOCKED with the list otherwise. Include a 1-3 sentence summary, the reviewed scope/state, and met/not met per criterion. Code inspection does not prove tests pass; say which checks were skipped.
```
