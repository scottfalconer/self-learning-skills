# Aha Moment Rubric

Use this rubric after completing a task (or a skill run) to decide what is worth saving.

An “aha” is worth recording if it meets **all** of these:

## 1) Durable
It is likely to stay true for a while:
- stable API behavior
- stable log/event fields
- consistent file formats
- repeatable command/query patterns

Avoid saving one-off coincidences.

## 2) Reusable
It saves time or prevents mistakes in the future:
- removes repeated exploration (sampling, guessing field names, trial-and-error)
- prevents a known failure mode (auth, pagination, parsing, escaping)
- provides a known-good template for queries/commands

### Reusable across repos?

If the learning applies beyond the current repo (for example, two systems use the same log format), mark it:

- `scope: "portable"` (generalizable)
- `shareable: true` only if it contains no secrets/PII/project-only context

If it’s only relevant to the current repo/run, keep:

- `scope: "project"`

## 3) Specific and actionable
It includes concrete steps:
- commands, query templates, jq filters, SQL snippets
- schema/contract summaries (field names + types + invariants)
- a small checklist that can be followed without extra context

Avoid vague advice.

## 4) Safe to store
No secrets, PII, or proprietary payloads.

If in doubt:
- store only the **shape** (field names/types), not raw values
- store a **redacted** example with placeholders

---

## Common “aha” categories (good candidates)

### Input/Output shape
- “Upstream JSON fields are X/Y/Z; `errorCode` is missing when success”
- “CSV columns are stable; dates are `YYYY-MM-DD`”

### Fast path / template
- “Best log-search query starter for service logs”
- “curl invocation with required headers and pagination”

### Invariants and constraints
- “This endpoint requires idempotency key”
- “Times are UTC; convert before charting”

### Error signatures → fixes
- “`403` means token missing scope; fix by …”
- “`jq` fails unless we use `-r`”

### Tooling shortcuts
- “Use `rg` with these patterns; ignore vendor dirs”
- “Use `git log -S` for this kind of regression”

### Negative knowledge (anti-patterns)
Record things that failed if the failure was non-obvious (so future runs don’t waste time retrying known bad paths).

- “Do not use `git grep` on this repo; it hangs. Use `rg`.”
- “The v2 API endpoint returns `200 OK` even on errors; check the body.”

---

## What *not* to record

- personal reminders (“be careful”, “remember to check”)
- long raw logs or payload dumps
- anything that depends on ephemeral state
- anything secret / sensitive
