# Portability & scope: store location vs content scope

This skill has a few related concepts that are easy to mix up:

1) **Store location**: where the JSONL files live (project-local vs global)
2) **Content scope**: how general a card/recommendation is (`scope: project|portable`)
3) **Sharing mechanism**: promote (personal) vs backport (shared)

Keeping these separate is what lets you capture broadly useful “developer tips/tricks” without dragging full project context along.

## 1) Store location (where memory lives)

Store location is about **filesystem paths**, not whether something is generalizable.

### Project store (default)

Best for: anything you discover while working in this repo (including items you may later generalize).

Path:

`<repo-root>/.agent-skills/self-learning/v1/users/<user>/`

### Global store (optional)

Best for: items you want to recall across many repos (usually **portable + shareable** items).

Path:

`~/.agent-skills/self-learning/v1/users/<user>/`

Notes:
- The global store is optional; most workflows start in the project store.
- You still need policy/instructions if you want agents to consult the global store.

## 2) Content scope (`scope` field)

Content scope is a field on **Aha Cards** and **Recommendations** (see `references/FORMAT.md`).

- `project`: depends on this repo/run; keep local; not a backport target
- `portable`: expressed generically; could apply in other repos; candidate for promote/backport

### Portable-writing checklist (avoid leaking full project context)

If you mark something `portable`, write it so it reads like a reusable developer note:

- Remove customer names, one-off ticket IDs, and one-time incident details unless they are part of a reusable lookup pattern.
- Prefer **templates and shapes** over raw payload dumps (field names/types, invariants, error signatures).
- Replace environment-specific values with placeholders: `<repo-root>`, `<PROJECT_KEY>`, `<SERVICE>`, `<ENV>`, `<TOKEN>`.
- Avoid absolute paths in steps/evidence; prefer relative paths or `<repo-root>/...`.

If it’s a generally useful idea but contains sensitive/project-specific details, keep the scope intent (`portable`) but set `shareable: false` until you can rewrite safely.

## 3) Promote (project store → global store)

Promotion copies selected Aha Cards from your **project store** to your **global store** for personal cross-repo recall:

```bash
python3 <SKILL_DIR>/scripts/self_learning.py promote --ids aha_123,aha_456
```

Notes:
- Promotion does **not** change any skills; it just copies cards.
- The CLI will set `scope` to `portable` if it’s missing, but you’re still responsible for making the content actually portable and safe (`shareable: true`).

## 4) Backport (memory → skill)

Backporting is how you “graduate” a proven Aha into a skill so the knowledge travels with the skill when shared.

Good backport targets:
- `references/…` files (schemas, templates, examples)
- clearer steps in the skill’s `SKILL.md`
- small deterministic helpers in `scripts/…`

Generate a backport bundle (recommended first):

```bash
python3 <SKILL_DIR>/scripts/self_learning.py export-backport --skill-path <skill-dir> --ids aha_123 --make-diff
```

Apply directly (writes changes):

```bash
python3 <SKILL_DIR>/scripts/self_learning.py export-backport --skill-path <skill-dir> --ids aha_123 --apply
```

Recommended criteria before backporting:
- `scope: portable`
- `shareable: true`
- durable/repeatable (see `references/RUBRIC.md`)

## 5) Auditable and reversible backports

Backport bundles are designed to be easy to review and undo:

- Bundles include `BACKPORT_MANIFEST.json` describing the backport id, selected card ids, and intended changes.
- `SKILL.md` snippets are wrapped in `<!-- self-learning:backport:start ... -->` / `<!-- self-learning:backport:end -->`.
- Backported Aha Cards in `references/self-learning-aha.md` are wrapped per card with `<!-- self-learning:aha:start ... -->` / `<!-- self-learning:aha:end -->`.
- The local store records each export/apply in `backports.jsonl`.

Removal options:
- Prefer reverting the commit/PR that applied the backport.
- Otherwise delete the marker-wrapped blocks (and/or remove individual Aha Card blocks).

Optional helper:

```bash
python3 <SKILL_DIR>/scripts/self_learning.py backport-inspect --skill-path <skill-dir>
```

## Safety / privacy rules

Before promoting or backporting:
- remove secrets (keys, tokens, passwords, cookies)
- avoid raw customer data and PII
- keep examples synthetic or redacted
- prefer recording **shape** over values

If you can’t make it safe, keep it in the project store and set `shareable: false`.
