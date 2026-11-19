# Blind spec checker prompt

The main session fills `{SPEC_DIR}` (absolute path of the spec folder) and `{FIRST}` (first guess number), then dispatches the text below to a fresh `general-purpose` subagent. Add nothing else: the checker must see only the spec.

```
You are checking whether a change spec is complete enough to build and test the change from the spec alone.

Read only these files under {SPEC_DIR}, the ones that exist: README.md, requirements.md, design.md, every file in contracts/, security.md, ui-design.md. Do not read code, other documentation, git history or the web. You cannot ask the author anything, and nobody will answer a question in your reply.

Imagine you must now write the code and its tests from these files. List every point where you would have to guess. Look for:
- behavior: what happens in each case, in what order, and what the caller sees
- edge cases: empty, duplicate, concurrent, repeated, partial and boundary inputs
- errors: which failures can happen, the error code or message for each, retries, what is rolled back
- data: formats, fields, validation, defaults, storage, retention, what is logged or masked
- limits: sizes, rates, timeouts, quotas, amounts, precision, time zones
- ownership: which component or service does what, who calls whom, who owns the data
Also list two files that contradict each other, an acceptance criterion that no test could check as written, and a security rule that no requirement or design section applies.

Do not list: a point any of the files already answers, wording or style, or an internal detail the spec leaves to the implementer that no test could observe.

Write each guess as one line, a concrete question that one sentence can answer, followed by where it arises:
- [ ] G<n>: <question> (<requirement ID or file and section>)
Number from G{FIRST} upward.

Append the lines to {SPEC_DIR}/spec-check.md, keeping everything already in it. If you find nothing to guess, append one line: `Checked: no guesses.` Do not edit any other file.

Reply with the number of guesses and the file path, nothing else.
```
