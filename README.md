# self-learning-skills

This skill is a “sidecar memory” system for agent work:

- Capture 1–5 durable **Aha Cards** after a task.
- Generate concrete **recommendations** to improve future runs.
- Persist learnings locally as append-only JSONL (per-project and optional global).
- Optionally export **auditable backport bundles** (manifest + markers) you can apply via PR/commit.

`SKILL.md` is intentionally kept short to reduce agent token cost; this README holds the longer background/setup docs.

## Compatibility

- Works in most filesystem-based Agent Skills implementations (Claude Code, Codex, Copilot Agent, etc.).
- No network access required.
- Optional: `python3` to run `scripts/self_learning.py` (stdlib-only helper CLI).

## Storage model

All learnings are stored as **append-only JSONL** (one JSON object per line).

- Project-local store (recommended; gitignored): `<repo-root>/.agent-skills/self-learning/v1/users/<user>/`
- Global store (optional; cross-project): `~/.agent-skills/self-learning/v1/users/<user>/`

Files (project store):
- `events.jsonl`
- `aha_cards.jsonl`
- `recommendations.jsonl`
- `signals.jsonl` (usage/reinforcement signals for scoring)
- `backports.jsonl` (backport exports/applies)
- `INDEX.md` (best-effort human dashboard; safe to delete/rebuild)

## One-time setup (optional)

### A) Initialize storage folders

```bash
python scripts/self_learning.py init
```

If you can’t run scripts, create the project store folder manually:
- `.agent-skills/self-learning/v1/users/<user>/`

### B) Keep the store out of git

Add `.agent-skills/` to `.gitignore` (the `init` command can do this with `--gitignore`).

## Integration (no hooks)

Agent Skills don’t have a standard post-run hook mechanism. This skill **does not** modify other skills to “auto-run itself”.

To make “run self-learning after tasks” happen consistently, add a small policy block to your repo instruction files:
- `AGENTS.md` (Codex and others)
- `CLAUDE.md` (Claude Code)
- Optional: `.github/copilot-instructions.md`

Templates live in `references/INTEGRATION.md`.

## Operational usage (CLI)

### Record (post-run)

```bash
python scripts/self_learning.py record --json payload.json
```

Payload shape examples and field conventions: `references/FORMAT.md`.

### Recall (pre-run)

```bash
python scripts/self_learning.py list --query "keywords"
```

### Review (dashboard)

```bash
python scripts/self_learning.py review --days 7
python scripts/self_learning.py review --days 7 --format json
```

### Recommendation lifecycle

```bash
python scripts/self_learning.py rec-status --id rec_... --status in_progress --note "..."
```

### Store hygiene / repair (append-only)

Backfills missing `primary_skill` (to avoid `null`) and normalizes known status aliases.

```bash
python scripts/self_learning.py repair --apply
```

## Backports (auditable + reversible)

Backporting is **explicit** and reviewable:

```bash
python scripts/self_learning.py export-backport --skill-path <skill-dir> --ids aha_1,aha_2 --make-diff
```

The bundle includes:
- `BACKPORT_MANIFEST.json` (metadata + included Aha IDs)
- `backport.patch` (optional diff; best-effort)

If you apply the backport (`--apply`), inserted text is marker-wrapped so it’s easy to find/remove:
- `<!-- self-learning:backport:start id=... --> … <!-- self-learning:backport:end -->`
- Per-card markers in `references/self-learning-aha.md`

Inspect an existing skill for markers:

```bash
python scripts/self_learning.py backport-inspect --skill-path <skill-dir>
```

## Privacy / safety

This system is designed for **durable, reusable, non-sensitive** learnings. Avoid storing secrets or private payloads.

Rubric and examples: `references/RUBRIC.md`.
