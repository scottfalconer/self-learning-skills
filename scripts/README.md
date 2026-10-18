# CLI reference

The CLI requires Python 3.10 or newer. It uses only the standard library.

Run commands from the intended project root. Replace `<SKILL_DIR>` with the installed skill directory. Use `SELF_LEARNING_REPO_ROOT` to select a different root explicitly.

For the full option list, run:

```bash
python3 <SKILL_DIR>/scripts/self_learning.py --help
python3 <SKILL_DIR>/scripts/self_learning.py <command> --help
```

## Commands and write effects

| Command | Effect |
| --- | --- |
| `init` | Creates the project store. Updates `.gitignore` unless you use `--no-gitignore`. |
| `list` | Reads project Aha Cards. |
| `review` | Reads project records and shows a summary. |
| `record` | Writes records from a JSON payload. |
| `use` | Writes usage signals. |
| `signal` | Writes one selected signal. |
| `aha-status` | Adds an Aha Card status update. |
| `rec-status` | Adds a recommendation status or scope update. |
| `repair` | Shows proposed corrections. Writes corrections only with `--apply`. |
| `promote` | Copies selected cards to the global store. Writes project signals. |
| `export-backport` | Writes a local bundle and history entry. Changes target skill files only with `--apply`. |
| `backport-inspect` | Reads backport markers in a target skill. |

`list`, `review`, and `repair` without `--apply` do not create a missing store. Store writes can also update the generated `INDEX.md`.

## Read records

```bash
python3 <SKILL_DIR>/scripts/self_learning.py list --query "pagination" --limit 10
python3 <SKILL_DIR>/scripts/self_learning.py list --skill csv-import
python3 <SKILL_DIR>/scripts/self_learning.py review --days 7
python3 <SKILL_DIR>/scripts/self_learning.py review --scope portable --format json
```

`review --include-global` adds global store counts. It does not search global card contents.

## Write records and status updates

```bash
python3 <SKILL_DIR>/scripts/self_learning.py record --json payload.json
python3 <SKILL_DIR>/scripts/self_learning.py use --aha aha_123 --rec rec_123
python3 <SKILL_DIR>/scripts/self_learning.py aha-status --id aha_123 --status accepted --note "Test passed."
python3 <SKILL_DIR>/scripts/self_learning.py rec-status --id rec_123 --status in_progress --note "Work started."
python3 <SKILL_DIR>/scripts/self_learning.py signal --kind aha_recalled --aha-id aha_123 --source manual
```

Replace example IDs and notes with actual values. Record a successful test only after you run it and examine the result.

Refer to the [record format](../references/FORMAT.md) for JSON input and permitted status values.

## Repair records

```bash
python3 <SKILL_DIR>/scripts/self_learning.py repair
python3 <SKILL_DIR>/scripts/self_learning.py repair --apply
```

Repair can supply missing `primary_skill` values and normalize status aliases. Examine the proposed corrections before an authorized apply. Repair does not remove malformed JSONL lines. The reader skips malformed lines and writes a warning to standard error.

## Copy or export cards

```bash
python3 <SKILL_DIR>/scripts/self_learning.py promote --ids aha_123
python3 <SKILL_DIR>/scripts/self_learning.py export-backport --skill-path <target-skill-dir> --ids aha_123 --make-diff
python3 <SKILL_DIR>/scripts/self_learning.py backport-inspect --skill-path <target-skill-dir>
```

Each selected card must have `scope: "portable"` and `shareable: true`. Refer to the [backport procedure](../references/PORTABILITY.md#backport-to-a-skill) before you change another skill.
