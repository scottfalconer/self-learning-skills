# Integration (no hooks)

This skill intentionally **does not modify other skills** (no “hooks”, no patching `SKILL.md` elsewhere).

Agent Skills are model-invoked and there is no standard lifecycle mechanism like “after any skill runs, run X”. The clean, cross-agent approach is to use **repo instruction files** to tell the agent to:

1) **Before starting work**: skim relevant prior learnings (if present)  
2) **After finishing work**: invoke this skill to capture new learnings
3) **Periodically (review)**: skim the store `INDEX.md` (or run the optional `review` CLI) to decide what to implement/backport next

## Recommended setup

### 1) `AGENTS.md` (repo root)

Add a small “Self-learning policy” section:

```md
## Self-learning policy (sidecar skill)

### Before starting work
- If present, skim `.agent-skills/self-learning/v1/users/<user>/INDEX.md` (or `aha_cards.jsonl`) for relevant Aha Cards.

### After finishing work
- Run the `self-learning-skills` skill to capture:
  - Aha Cards (durable, reusable learnings)
  - Recommendations (what to change to make next time faster/cleaner)
```

### 2) `CLAUDE.md` (repo root, optional)

Keep it short so it’s always carried into context:

```md
# Repo guidance

Follow the Self-learning policy:
- Before starting: skim `.agent-skills/self-learning/v1/users/<user>/INDEX.md` if present.
- After finishing: run the `self-learning-skills` skill.

(If `AGENTS.md` exists, treat it as canonical for details.)
```

### 3) `.github/copilot-instructions.md` (optional)

If you use Copilot/VS Code instruction files:

```md
Follow `AGENTS.md` repository guidance.

- Before starting: skim `.agent-skills/self-learning/v1/users/<user>/INDEX.md` if present.
- After finishing any non-trivial task: run the `self-learning-skills` skill.
```

## Notes

- Keep `.agent-skills/` in `.gitignore` if you don’t want these learnings committed.
- This is **policy-based** (instructions), not a runtime guarantee; it’s still the most portable way to get consistent pre/post behavior across different agent tools.

## If you previously used hooks

Older versions of this skill included an `enable-hooks` helper that appended a marked block into other skills’ `SKILL.md` files.

To remove it, delete the section between these markers (inclusive) in any affected `SKILL.md`:

- `<!-- self-learning:hook:start -->`
- `<!-- self-learning:hook:end -->`
