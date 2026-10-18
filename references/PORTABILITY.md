# Storage and portability

Storage location, content scope, and sharing are separate properties. A portable card can remain in a project store. A global store does not make its contents safe for publication.

## Store locations

The default project store is:

```text
<repo-root>/.agents/memory/self-learning/v1/users/<user>/
```

The optional global store is:

```text
~/.agents/memory/self-learning/v1/users/<user>/
```

The CLI derives `<user>` from `USER`, then `USERNAME`, with `default` as the fallback. It removes the email domain and replaces characters that are not safe for a filename.

Run the CLI from the intended project. By default, it searches parent directories for `.git`. Use `SELF_LEARNING_REPO_ROOT` when automatic detection does not identify the intended root.

| Variable | Effect |
| --- | --- |
| `SELF_LEARNING_REPO_ROOT` | Sets the repository root. |
| `SELF_LEARNING_PROJECT_DIR` | Sets the project memory base directory. The CLI adds `self-learning/v1/users/<user>/`. |
| `SELF_LEARNING_GLOBAL_DIR` | Sets the complete global store path. The CLI adds no suffix. |

For example, this command reads `<repo-root>/.local-memory/self-learning/v1/users/<user>/`:

```bash
SELF_LEARNING_PROJECT_DIR=.local-memory \
  python3 <SKILL_DIR>/scripts/self_learning.py review
```

The example assumes that the current directory is the project root. Relative overrides resolve from the current directory.

`init` adds an ignore rule for a project memory base inside the repository. An external memory directory needs separate ignore or access controls. Use `--no-gitignore` to manage ignore rules yourself.

The `list` and `review` commands read the project store. `review --include-global` adds global store counts. It does not search global card contents. To recall global cards, read the global store's `INDEX.md` or JSONL file.

## Content scope

Use `scope: "project"` when a card depends on one project. Use `scope: "portable"` when its content is applicable to other projects.

Before you classify a card as portable:

1. Remove customer names and private data.
2. Replace environment values with placeholders.
3. Keep the conditions that affect the result.
4. Use source references that another reader can access.
5. Set `shareable: true` only when the content is safe to share.

To share revised private content, create a separate card. Refer to [Aha Card updates](FORMAT.md#aha-cards) for restrictions.

These fields classify the content. They do not authorize writes to a global store, edits to another skill, or publication.

## Copy cards to the global store

Use this command when the user authorizes personal memory across projects:

```bash
python3 <SKILL_DIR>/scripts/self_learning.py promote --ids aha_123,aha_456
```

The command copies selected Aha Cards to the global store. It also writes signals to the project store. It does not change skill files. It skips IDs that already exist in the global store. It does not update those global copies.

Every selected card must have `scope: "portable"` and `shareable: true`. The command uses each card's latest record. If an ID is missing, the command fails before it copies cards.

Examine a card before you copy it. Do not copy rejected or deprecated results without a new examination of their source data.

## Backport to a skill

A backport puts selected cards in `references/self-learning-aha.md` inside a target skill. It adds a marked reference block to the target's `SKILL.md`.

The CLI requires `scope: "portable"` and `shareable: true` for every selected card. These fields do not prove that a card is correct.

To prepare a backport:

1. Make sure that the card still agrees with the current code or documentation.
2. Make sure that the target skill needs this information.
3. Create a bundle with a patch:

   ```bash
   python3 <SKILL_DIR>/scripts/self_learning.py export-backport \
     --skill-path <target-skill-dir> \
     --ids aha_123,aha_456 \
     --make-diff
   ```

4. Examine the manifest and patch in the reported bundle directory.
5. If target edits are authorized, apply the changes:

   ```bash
   python3 <SKILL_DIR>/scripts/self_learning.py export-backport \
     --skill-path <target-skill-dir> \
     --ids aha_123,aha_456 \
     --apply
   ```

6. Examine the changed target files.

An export without `--apply` still writes files. It creates a bundle under `<project-store>/exports/backports/` and adds an entry to `backports.jsonl`. The target skill stays unchanged.

The bundle contains a manifest, a reference file, and a `SKILL_APPEND.md` snippet. `--make-diff` also writes `backport.patch`. `--apply` writes the target files and records the apply operation.

## Examine or remove a backport

To find backport markers, run this command:

```bash
python3 <SKILL_DIR>/scripts/self_learning.py backport-inspect --skill-path <target-skill-dir>
```

The target uses these markers:

- `self-learning:backport:start` and `self-learning:backport:end` in `SKILL.md`
- `self-learning:aha:start` and `self-learning:aha:end` around each card in the reference file

To remove a backport, first examine the current target changes. If the backport has a separate commit, a revert can remove it. Otherwise, remove only the applicable marked blocks after authorization. Do not overwrite later edits.
