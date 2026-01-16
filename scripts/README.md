# Scripts (optional)

This skill works without scripts (you can write the JSONL files manually), but these helpers make it easier.

## Quick commands

From your repo root (recommended):

```bash
python path/to/self-learning-skills/scripts/self_learning.py init
python path/to/self-learning-skills/scripts/self_learning.py record --json payload.json
python path/to/self-learning-skills/scripts/self_learning.py list --limit 10
python path/to/self-learning-skills/scripts/self_learning.py review --days 7
python path/to/self-learning-skills/scripts/self_learning.py review --days 7 --format json
python path/to/self-learning-skills/scripts/self_learning.py repair --apply
python path/to/self-learning-skills/scripts/self_learning.py rec-status --id rec_... --status in_progress --note "..."
python path/to/self-learning-skills/scripts/self_learning.py aha-status --id aha_... --status accepted --note "..."
python path/to/self-learning-skills/scripts/self_learning.py signal --kind aha_used --aha-id aha_... --source manual --context "..."
python path/to/self-learning-skills/scripts/self_learning.py use --aha aha_...[,aha_...] [--rec rec_...[,rec_...]] [--context "..."]
python path/to/self-learning-skills/scripts/self_learning.py promote --ids aha_...
python path/to/self-learning-skills/scripts/self_learning.py export-backport --skill-path <skill-folder> --ids aha_...
python path/to/self-learning-skills/scripts/self_learning.py backport-inspect --skill-path <skill-folder>
```

Notes:

- `export-backport` writes a bundle under `.agent-skills/self-learning/v1/users/<user>/exports/backports/` including `BACKPORT_MANIFEST.json`, and appends a provenance entry to `backports.jsonl`.
- `review` defaults to a compact summary. Use `--format json` for full machine-readable output.
- `repair --apply` backfills missing `primary_skill` values and normalizes common status aliases (append-only).

All commands use only Python stdlib.
