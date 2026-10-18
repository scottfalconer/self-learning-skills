# Record format

The CLI stores version 1 records in JSONL files. Each line contains one JSON object. Refer to [storage configuration](PORTABILITY.md) for directory paths.

## Record input

The `record` command accepts a JSON object from a file or standard input. Each top-level field is optional.

| Field | Type | Content |
| --- | --- | --- |
| `event` | Object | A task summary |
| `aha_cards` | Array of objects | Results that can help later tasks |
| `recommendations` | Array of objects | Proposed improvements |
| `used_aha_ids` | Array of strings | IDs of cards that informed the task |
| `used_rec_ids` | Array of strings | IDs of recommendations that informed the task |
| `usage_source` | String | The source of usage signals |
| `usage_context` | String | A short description of record use |

This example shows a payload. It does not report a test of this repository.

```json
{
  "event": {
    "task_summary": "Correct the CSV import",
    "primary_skill": "csv-import"
  },
  "aha_cards": [
    {
      "title": "Preserve empty CSV fields",
      "when_to_use": "Import rows with optional CSV fields",
      "problem": "A split on commas cannot read quoted commas correctly.",
      "solution_steps": [
        "Use the csv module to read rows.",
        "Keep empty field values until validation."
      ],
      "evidence": ["tests/test_csv_import.py"],
      "primary_skill": "csv-import",
      "scope": "project",
      "shareable": false,
      "tags": ["csv", "import"]
    }
  ],
  "recommendations": [
    {
      "title": "Add a quoted-field test",
      "why": "A test can detect changes to the import behavior.",
      "expected_impact": {"quality": "high"},
      "implementation_hint": "Add an empty field and a quoted comma to the import test data.",
      "primary_skill": "csv-import",
      "scope": "project",
      "shareable": false,
      "status": "proposed",
      "tags": ["tests"]
    }
  ]
}
```

Save the payload as `payload.json`. Then run this command:

```bash
python3 <SKILL_DIR>/scripts/self_learning.py record --json payload.json
```

Without `--json`, the command reads JSON from standard input. Input validation rejects malformed known fields before it writes records.

## Common fields

| Field | Meaning |
| --- | --- |
| `id` | A stable record ID. The CLI creates it if you omit it. |
| `ts` | An ISO 8601 timestamp. The CLI supplies UTC time if you omit it. |
| `primary_skill` | The related skill name. The CLI uses `unknown` when it cannot determine the name. |
| `scope` | `project` by default, or `portable` for content that applies to other projects. |
| `shareable` | A boolean content classification. Set it to `true` only after a privacy examination. |
| `tags` | An array of search terms. `skill:<name>` can identify the related skill. |

The CLI accepts additional fields. Their presence does not prove that their content is correct. Prefer fields that help another reader examine or use the result.

For portable records, use placeholders for project values. Keep credentials, personal data, and private payloads out of every record. `shareable: false` does not make secret storage safe.

## Aha Cards

An Aha Card explains a result and the conditions for its use. Include `title`, `when_to_use`, `problem`, `solution_steps`, and `evidence`.

The `evidence` field contains source references or observed results. Include an exact command and its result when you report a test. Identify conditions that limit the result, such as a software version or environment.

Optional fields include `input_shape`, `output_shape`, `gotchas`, `links`, and `note`. Keep these fields short.

The permitted status values are `proposed`, `accepted`, `rejected`, `deprecated`, and `backported`.

The CLI uses a card's title, use condition, and primary skill to find equivalent cards. A repeated record can add source data and a reinforcement signal.

A repeated record can restrict sharing. It cannot change a private card to a shareable card. To share revised content, create a new card with a different title and ID.

## Recommendations

A recommendation identifies a proposed change. Include `title`, `why`, and `implementation_hint`.

`expected_impact` can contain `speed` and `quality` values. These values are estimates, not measured results. `last_touched_ts` identifies the last status change. `note` can explain that change.

The permitted status values are `proposed`, `accepted`, `in_progress`, `done`, `rejected`, and `deprecated`.

## Files and history

| File | Content |
| --- | --- |
| `events.jsonl` | Task summaries |
| `aha_cards.jsonl` | Aha Card history |
| `recommendations.jsonl` | Recommendation history |
| `signals.jsonl` | Usage and status signals |
| `backports.jsonl` | Export and apply history |
| `INDEX.md` | A generated summary of the store |

JSONL updates add records. For a repeated ID, the last record supplies its current state. Earlier records remain in the file. `INDEX.md` can change when the CLI writes records or applies repairs.

Use the CLI status commands to change a record. Do not remove history to change its status.

Use only one writer per store. The CLI has no lock or transaction across files. An interrupted write can leave an incomplete operation.

## Usage signals

Signals contain `ts`, `kind`, a related record ID, `source`, and optional `context`.

The permitted signal kinds are:

- `aha_used`, `aha_recalled`, `aha_reinforced`, `aha_promoted`, `aha_backported`
- `rec_used`, `rec_touched`, `rec_done`

To record actual use, run this command:

```bash
python3 <SKILL_DIR>/scripts/self_learning.py use --aha aha_123 --rec rec_123
```

The `record` payload also accepts `used: {"aha_ids": [...], "rec_ids": [...]}`. This field is an alternative to `used_aha_ids` and `used_rec_ids`.

Usage scores help sort records. They do not establish correctness or permission to share content.

## Redaction limits

The CLI masks some secret fields and token patterns. It cannot identify all private data.

Remove private data before you prepare a payload. Examine the stored result after an authorized write. Append-only history keeps earlier values, even when you add a corrected record.
