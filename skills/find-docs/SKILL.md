---
name: find-docs
description: Look up a library, framework, SDK, CLI or cloud-service detail not verified for the project's version (syntax, flags, config keys, feature support, migration) via Context7 or official or installed docs, and cite it; Read by every stage before relying on such a detail.
disable-model-invocation: true
user-invocable: false
---

# Documentation lookup

Ordinary code reading needs no lookup when local source settles the behaviour.

1. **Version.** Read manifests, lockfiles or installed help for the version in use; never substitute the latest.
2. **Query.** One concept per query (combine only when the interaction is the question). Never send credentials, PII, proprietary code or payloads.
3. **Source.** Configured Context7 tools first: `resolve-library-id` (skip if an ID is already known), pick the official, version-matching library, then `query-docs` with the ID. Never invent an ID or version suffix. Alternatives: official docs, installed CLI help, local package source. An installed Context7 CLI is usable only after reading its `--help`; never `npx`/`@latest`, global installs or login flows for a lookup. Quota or missing package → switch source, do not create accounts.
4. **Limit.** After ~3 unproductive queries change source or question.
5. **Answer.** Cite the link or local path and version; separate documented fact, local behaviour and inference. No adequate source → say what is unknown and what would settle it. Recall may shape a query, never stand in for a citation. Never print keys or config values.
