# Blind spec checker prompt

Fill `{SPEC_DIR}` (absolute spec folder) and `{FIRST}` (first guess number); send the text below to a fresh `general-purpose` subagent and add nothing else.

```
Check whether this change spec is complete enough to build and test the change from the spec alone.

Read only these files under {SPEC_DIR}, those that exist: README.md, requirements.md, design.md, contracts/*, security.md, ui-design.md. No code, other docs, git history or web. You cannot ask the author; nobody answers questions in your reply.

Imagine writing the code and its tests from these files. List every point where you would have to guess:
- behavior: each case, ordering, what the caller sees
- edge cases: empty, duplicate, concurrent, repeated, partial, boundary inputs
- errors: possible failures, error code or message for each, retries, rollback
- data: formats, fields, validation, defaults, storage, retention, logging and masking
- limits: sizes, rates, timeouts, quotas, amounts, precision, time zones
- ownership: which component does what, who calls whom, who owns the data
Also: two files that contradict each other, an acceptance criterion no test could check as written, a security rule no requirement or design section applies.
Skip: points the files already answer, wording or style, internal details no test could observe.

One line per guess, a concrete question one sentence can answer, then where it arises, numbered from G{FIRST}:
- [ ] G<n>: <question> (<requirement ID or file and section>)

Append the lines to {SPEC_DIR}/spec-check.md, keeping its content. Nothing to guess → append `Checked: no guesses.` Edit no other file.

Reply with the number of guesses and the file path only.
```
