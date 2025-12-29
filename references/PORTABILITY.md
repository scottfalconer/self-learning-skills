# Portability: project vs global vs backport

This skill supports **two storage scopes** and a **backport mechanism**.

## Scope options

### 1) `project` (default)
Keep the learning only in this repo’s local store.

Use this when:
- it depends on repo-specific conventions
- it references internal paths, services, or proprietary data
- it’s only relevant to this codebase

Storage:
`<repo-root>/.agent-skills/self-learning/...`

### 2) `portable` (promote to global)
Use when the learning is broadly reusable and safe:
- generic debugging patterns
- common command templates
- public API behavior
- generic schemas (not proprietary)

Promotion copies cards to a global store:
`~/.agent-skills/self-learning/...`

## Backporting into skills (shareable improvements)

Some learnings should become part of a skill itself so that:

- everyone on the project benefits (not just one user)
- the skill becomes faster and more reliable
- the knowledge travels with the skill when shared

Good backport targets:
- `references/…` files (schemas, examples, contracts)
- clearer steps in the skill’s `SKILL.md`
- small scripts in `scripts/…` (deterministic parsing/validation)

The helper script can generate a **backport bundle** you can commit or PR.

## Auditable and reversible backports

Backport bundles are designed to be easy to review and undo:

- Bundles include `BACKPORT_MANIFEST.json` describing the backport id, selected card ids, and intended changes.
- `SKILL.md` snippets are wrapped in `<!-- self-learning:backport:start ... -->` / `<!-- self-learning:backport:end -->`.
- Backported Aha Cards in `references/self-learning-aha.md` are wrapped per card with `<!-- self-learning:aha:start ... -->` / `<!-- self-learning:aha:end -->`.
- The local store records each export/apply in `backports.jsonl`.

Removal options:

- Prefer reverting the commit/PR that applied the backport.
- Otherwise delete the marker-wrapped blocks (and/or remove individual Aha Card blocks).

Optional helper:

- `python scripts/self_learning.py backport-inspect --skill-path <skill-dir>` prints marker IDs and card IDs to guide removal.

## Safety / privacy rules

Before promoting or backporting:
- remove secrets (keys, tokens, passwords, cookies)
- avoid raw customer data and PII
- keep examples synthetic or redacted
- prefer recording **shape** over values

If you can’t make it safe, keep it `project` and `shareable: false`.
