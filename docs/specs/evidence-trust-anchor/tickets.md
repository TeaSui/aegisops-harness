# Tickets — evidence-trust-anchor

## T1: Rename defects and version drift
Blocked by: none
Covers: ETA-14
Status: done
What to build: old gate state is pruned on a case-sensitive filesystem, the injected notes open and close with the same tag, and the structure check fails when the README or the changelog names another version than the manifest.
- [x] A 60-day-old autopilot state file is removed by the prune
- [x] The session and subagent notes use one tag name
- [x] The structure check fails on a README or changelog version that differs from the manifest
Test: python3 -m unittest tests.test_autopilot tests.test_check_setup

## T2: Evals fail closed
Blocked by: none
Covers: ETA-10, ETA-12
Status: done
What to build: a session that never reached a model is excluded as infrastructure, a comparison with too few judged runs fails with its own exit code, and the report flags a baseline measured on another plugin version.
- [x] A result with no cost and no output tokens is reported as an infrastructure failure
- [x] A suite whose runs were all excluded fails the comparison
- [x] The report names a baseline from another plugin version
Test: python3 -m unittest tests.test_evals

## T3: Evals score the outcome
Blocked by: T2
Covers: ETA-9, ETA-11
Status: done
What to build: the lifecycle judge needs green tests and the hidden checks, the runner has a control arm without the plugin, and three harder cases ship with hidden checks proven on a reference solution.
- [x] The broken repository of proof A fails the lifecycle judge
- [x] The control arm runs without the plugin and is judged on outcome
- [x] Each new hidden check passes on its reference solution and fails on the fixture as shipped
Test: python3 -m unittest tests.test_evals tests.test_eval_cases

## T4: Pinned verify command and dynamic traceability
Blocked by: none
Covers: ETA-1, ETA-2
Status: ready-for-agent
What to build: verify runs the command pinned in the default branch's config, another command is refused, and with a JUnit glob every story verified by test needs a passing executed test.
- [ ] Verify without a config is refused with the onboarding hint
- [ ] A branch that rewrites the config still runs the default branch's command
- [ ] A story whose ID appears only in a comment fails the verified gate
Test: python3 -m unittest tests.test_aidlc tests.test_trust_anchor

## T5: Revert check
Blocked by: T4
Covers: ETA-3
Status: ready-for-agent
What to build: verify proves the suite goes red without the production change and leaves the tree as it found it.
- [ ] A vacuous test fails the revert check
- [ ] A real test passes it and the tree is restored
- [ ] A change with no production source skips it with a reason
Test: python3 -m unittest tests.test_trust_anchor

## T6: Cumulative gates and real CI
Blocked by: T4
Covers: ETA-5
Status: ready-for-agent
What to build: later gates include the earlier ones and the shipped gate needs a CI result unless the config waives it.
- [ ] The four-file forgery of proof B fails the shipped gate
- [ ] A typed "CI: green" passes only with the CI waiver in the config
Test: python3 -m unittest tests.test_aidlc tests.test_trust_anchor

## T7: CI command and action
Blocked by: T5, T6
Covers: ETA-4, ETA-15
Status: ready-for-agent
What to build: one command recomputes the evidence on the head with the base config, ignores recorded verify lines, and is packaged as a composite action that this repository's own CI runs.
- [ ] A forged green ledger over red tests fails the CI command
- [ ] The CI command writes nothing to the spec folder
- [ ] This repository's CI runs the command on pull requests
Test: python3 -m unittest tests.test_trust_anchor tests.test_evals

## T8: Approval bound to the spec text
Blocked by: none
Covers: ETA-6
Status: ready-for-agent
What to build: an approval event carries the hash of the spec, the accepted gate needs it to match, and the model is kept from recording a person's approval.
- [ ] Editing the spec after approval fails the accepted gate
- [ ] The guard refuses an approval the user did not type and lets a person's terminal through
Test: python3 -m unittest tests.test_trust_anchor tests.test_evidence_guard

## T9: Reviewer returns
Blocked by: T6
Covers: ETA-7
Status: ready-for-agent
What to build: review-stage returns are stored verbatim by a hook and the reviewed gate compares review.md with them.
- [ ] A hand-typed review with no stored return fails the reviewed gate
- [ ] A dropped or downgraded finding fails it
- [ ] The guard refuses edits to the ledger and the stored returns
Test: python3 -m unittest tests.test_trust_anchor tests.test_evidence_guard

## T10: Hooks parse commands and cover MCP
Blocked by: none
Covers: ETA-8
Status: ready-for-agent
What to build: the secret, PR and merge gates recognise git global options, absolute paths, the gh API form and the GitHub MCP tools.
- [ ] Each equivalent command of proof E is gated
- [ ] An MCP create or merge call is gated
Test: python3 -m unittest tests.test_hook_commands tests.test_ship_gate

## T11: Schema version, trust model and release
Blocked by: T7, T8, T9, T10
Covers: ETA-13
Status: ready-for-agent
What to build: spec README and config carry the schema version, a newer schema is refused, and the docs state the three layers and the compatibility rule.
- [ ] A spec with a newer schema fails its gate with a clear message
- [ ] The lifecycle reference states the trust model and the compatibility rule
Test: python3 -m unittest discover -s tests
