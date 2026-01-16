# Self-Learning Storage Format (v1)

This skill writes **append-only JSONL** files.

## Default store locations

### Project-local (recommended)
`<repo-root>/.agent-skills/self-learning/v1/users/<user>/`

### Global (optional)
`~/.agent-skills/self-learning/v1/users/<user>/`

The helper script (`<SKILL_DIR>/scripts/self_learning.py`) supports both.

## Files

- `events.jsonl` — what happened in runs
- `aha_cards.jsonl` — the durable “aha moments” captured
- `recommendations.jsonl` — improvement opportunities (what would make next time easier)
- `backports.jsonl` — provenance log for backport bundles/actions
- `signals.jsonl` — lightweight “usage”/lifecycle signals for scoring
- `INDEX.md` — optional human-readable summary (best-effort)

All JSONL files are **append-only**.

### Append-only updates (auditable)

Some JSONL files behave like an **event stream**:

- `aha_cards.jsonl`: you may append a new line with an existing `id` to update status/fields (history is preserved).
- `recommendations.jsonl`: you may append a new line with an existing `id` to update status/notes (history is preserved).

## Common fields

- `id` (string): stable identifier. If omitted, the helper script will create one.
- `ts` (string): ISO 8601 timestamp (`YYYY-MM-DDTHH:MM:SSZ`). If omitted, helper script fills it.
- `primary_skill` (string): the skill name involved (use `unknown` if not known)
- `scope` (string): `project` (repo/run-specific; not a backport target) or `portable` (generally reusable; a backport candidate)
- `shareable` (boolean): whether it is safe to backport/share
- `tags` (array of strings): small keywords (`["schema", "jq"]`). Optional convention: include `skill:<name>` to explicitly tag the originating skill (used by `python3 <SKILL_DIR>/scripts/self_learning.py repair` to backfill missing `primary_skill`).

### Writing `portable` entries (generalize without project bleed)

If you set `scope: "portable"`, write the card/recommendation so it reads like a reusable developer note:

- Replace project-specific values with placeholders: `<repo-root>`, `<ENV>`, `<SERVICE>`, `<PROJECT_KEY>`, `<TOKEN>`.
- Prefer **templates and shapes** over raw payload dumps (field names/types, invariants, error signatures).
- Avoid absolute paths in `solution_steps`/`evidence` (they will be wrong after backporting).
- If it’s portable in spirit but still sensitive, keep `scope: "portable"` but set `shareable: false` until you can rewrite safely.

## Aha Card object (one per line in `aha_cards.jsonl`)

Required (minimum viable):

```json
{
  "id": "aha_...",
  "ts": "2025-12-26T18:22:10Z",
  "title": "Short, specific title",
  "when_to_use": "Keywords / trigger phrase",
  "problem": "What slowed us down or caused uncertainty",
  "solution_steps": ["Step 1", "Step 2"],
  "evidence": ["path/to/file.md", "command: jq ..."],
  "primary_skill": "skill-name-or-unknown",
  "scope": "project",
  "shareable": true,
  "tags": ["tag1", "tag2"]
}
```

Recommended extra fields:

- `input_shape` (object): schema-like summary of key fields
- `output_shape` (object): shape of produced artifacts
- `gotchas` (array of strings)
- `links` (array of strings): internal links / docs (avoid secrets)
- `status` (string): `proposed|accepted|rejected|deprecated|backported` (optional)
- `last_touched_ts` (string): ISO timestamp for last manual status/note change (optional)
- `note` (string): optional human note for the latest status change

## Recommendation object (one per line in `recommendations.jsonl`)

Required (minimum viable):

```json
{
  "id": "rec_...",
  "ts": "2025-12-26T18:22:10Z",
  "title": "Concrete improvement",
  "why": "Why this matters / impact",
  "expected_impact": { "speed": "high", "quality": "medium" },
  "implementation_hint": "What to add/change and where",
  "primary_skill": "skill-name-or-unknown",
  "scope": "project",
  "shareable": true,
  "status": "proposed",
  "last_touched_ts": "2025-12-26T18:22:10Z",
  "note": "Optional note about status change",
  "tags": ["docs", "schema"]
}
```

Optional backport hints:

```json
{
  "backport": {
    "type": "reference-file",
    "target_skill_path": "optional/path/to/skill",
    "files": [
      { "path": "references/upstream-schema.md", "content": "# Schema\n..." }
    ],
    "skill_md_append": "## Notes\nRead references/upstream-schema.md first."
  }
}
```

## Event object (one per line in `events.jsonl`)

Minimum viable:

```json
{
  "id": "evt_...",
  "ts": "2025-12-26T18:22:10Z",
  "task_summary": "What the user wanted",
  "primary_skill": "skill-name-if-known",
  "notes": ["Key steps taken", "Tools used", "Pain points"]
}
```

## Backport record object (one per line in `backports.jsonl`)

Minimum viable:

```json
{
  "ts": "2025-12-26T18:22:10Z",
  "backport_id": "slbp_20251226T182210Z_4f2c9c",
  "target_skill": "example-skill",
  "target_skill_path": "/path/to/skill",
  "requested_card_ids": ["aha_..."],
  "added_card_ids": ["aha_..."],
  "result_card_ids": ["aha_..."],
  "applied": true,
  "bundle_dir": "/path/to/.agent-skills/.../exports/backports/example-skill_slbp_..."
}
```

## Signal record object (one per line in `signals.jsonl`)

Signals are lightweight, append-only events used for scoring and lifecycle tracking.

Minimum viable:

```json
{
  "ts": "2025-12-26T18:22:10Z",
  "kind": "aha_used",
  "aha_id": "aha_...",
  "source": "manual",
  "context": "Short, non-sensitive context"
}
```

`kind` values (current):

- `aha_used`, `aha_recalled`, `aha_reinforced`, `aha_promoted`, `aha_backported`
- `rec_used`, `rec_touched`, `rec_done`

Helper CLI conveniences:

- `python3 <SKILL_DIR>/scripts/self_learning.py use --aha aha_...[,aha_...] [--rec rec_...[,rec_...]]` appends `aha_used` / `rec_used` signals.
- `python3 <SKILL_DIR>/scripts/self_learning.py record` also supports optional keys to auto-append usage signals:
  - `used_aha_ids`: array of `aha_...` ids (or comma-separated string)
  - `used_rec_ids`: array of `rec_...` ids (or comma-separated string)
  - `used`: `{ "aha_ids": [...], "rec_ids": [...] }` (alternative shape)
  - `usage_source`, `usage_context`: optional metadata for the generated signals

## Redaction and safety

Never store:
- credentials, API keys, tokens, cookies
- private user data (PII)
- proprietary payloads that shouldn’t persist

The helper script performs **best-effort redaction** based on key names and token-like patterns, but the agent should still avoid capturing sensitive data.
