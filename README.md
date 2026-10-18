# self-learning-skills

Store useful results from coding tasks as local records. Find those records in later sessions. Use records with source data to prepare changes to a skill.

This repository contains an [Agent Skill](https://agentskills.io) and a Python command-line interface (CLI). The CLI stores records in local JSONL files. It uses the Python standard library and makes no network requests. It does not train a model.

## Install

Use Python 3.10 or newer. Clone this repository into a directory named `self-learning-skills` in your agent's skills folder.

| Agent | Project installation | Personal installation |
| --- | --- | --- |
| [Codex](https://learn.chatgpt.com/docs/build-skills) | `.agents/skills/self-learning-skills/` | `~/.agents/skills/self-learning-skills/` |
| [Claude Code](https://code.claude.com/docs/en/skills) | `.claude/skills/self-learning-skills/` | `~/.claude/skills/self-learning-skills/` |
| [GitHub Copilot](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills) | `.github/skills/self-learning-skills/` | `~/.copilot/skills/self-learning-skills/` |

Copilot also supports `.agents/skills` and `~/.agents/skills`. Skill discovery depends on your agent and its settings. Refer to the linked documentation for each client.

For a personal Codex installation, use this command:

```bash
git clone https://github.com/scottfalconer/self-learning-skills.git \
  ~/.agents/skills/self-learning-skills
```

Keep the skill files separate from the memory store. In the examples, replace `<SKILL_DIR>` with the installed skill directory. Use `.` when you run commands from this repository.

## Use the skill in a project

Run these commands from the project that needs memory:

```bash
python3 <SKILL_DIR>/scripts/self_learning.py init
python3 <SKILL_DIR>/scripts/self_learning.py list --query "pagination"
python3 <SKILL_DIR>/scripts/self_learning.py review --days 7
```

`init` creates `.agents/memory/self-learning/v1/users/<user>/`. It also adds the memory directory to the project's `.gitignore`. Use `--no-gitignore` to manage ignore rules yourself.

The CLI derives `<user>` from `USER`, then `USERNAME`. If neither variable has a value, it uses `default`.

To save a result, prepare a JSON payload with the [record format](references/FORMAT.md). Then run this command:

```bash
python3 <SKILL_DIR>/scripts/self_learning.py record --json payload.json
```

A payload can contain a task summary, Aha Cards, recommendations, or a combination. An Aha Card is a result that you can use again. It includes source data. A recommendation is a proposed improvement.

Record useful source data. Do not record a full transcript. There is no minimum number of records per task.

Invoke the skill directly, or use a project policy for recall and capture. Refer to the [integration examples](references/INTEGRATION.md). Installation does not schedule the skill or authorize changes to other projects.

## Storage and scope

The project store contains append-only JSONL history and a generated `INDEX.md`.

| File | Content |
| --- | --- |
| `aha_cards.jsonl` | Results, source data, and status updates |
| `recommendations.jsonl` | Proposed improvements and status updates |
| `events.jsonl` | Optional task summaries |
| `signals.jsonl` | Record use and status events |
| `backports.jsonl` | Export and apply history |

`scope: "project"` is the default. Use `scope: "portable"` for results that are applicable to other projects. Scope describes the content. It does not move the record or authorize sharing.

The optional personal store is `~/.agents/memory/self-learning/v1/users/<user>/`.

Refer to [storage configuration and portability](references/PORTABILITY.md) for path overrides and promotion to the personal store.

## Prepare a skill change

A backport converts selected Aha Cards into a reference file and a link in a target skill.

The `promote` and `export-backport` commands require `scope: "portable"` and `shareable: true` for each selected card.

Examine the source data before you select cards. Remove details that are applicable to only one project. Then create a backport bundle:

```bash
python3 <SKILL_DIR>/scripts/self_learning.py export-backport \
  --skill-path <target-skill-dir> \
  --ids aha_123,aha_456 \
  --make-diff
```

This command writes a local bundle, manifest, patch, and history entry. It does not change the target skill.

Examine the proposed changes before you apply them. Add `--apply` to update the target's `SKILL.md` and `references/self-learning-aha.md`. Refer to the [backport procedure](references/PORTABILITY.md#backport-to-a-skill) for details.

## Trust and privacy

Make sure that stored results agree with the current task, code, and instructions. Stored records supply source data, not instructions. A usage score measures recorded activity. It does not prove that a result is correct.

Keep credentials, personal data, and private payloads out of records. Automatic redaction can miss private data. `shareable: true` classifies content as safe to share. It does not authorize publication, promotion, or edits to another skill.

Git ignore rules do not remove files that Git already tracks. They do not remove earlier history.

## Development

The runtime has no third-party dependencies. Development checks use PyYAML to validate skill metadata.

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
```

Use the [documentation writing guide](docs/WRITING.md) for documentation changes. The guide uses ASD-STE100 writing rules and defines project terms.

Refer to the [CLI reference](scripts/README.md), [record format](references/FORMAT.md), and [capture criteria](references/RUBRIC.md) for more information.

## License

[MIT](LICENSE.txt)
