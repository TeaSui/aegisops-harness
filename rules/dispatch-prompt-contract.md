# Dispatch contract

When dispatching, load `references/workflows/dispatch-prompt-contract.md`.
Implementation prompts state role, context, inputs, task, exit criteria, ownership/out-of-scope, evidence, bailout, and return format. Review/advisory prompts may use the lighter documented contract.
Verify referenced inputs exist; mark intended new files explicitly. Before dispatching into a worktree or another checkout, check that each instruction file the prompt cites (CLAUDE.md, `.claude/rules/*.md`, docs) exists there and is non-empty: ignored or uncommitted files are absent from worktrees. If not, cite the main checkout's absolute paths and say why. Give each implementer non-overlapping ownership and tell it other agents may be working in the same checkout. Resolve dependencies before parallel work.
Model/effort selection: `references/model-guide.md`. Task-specific context must be self-contained; do not assume access to the parent conversation.
