# self-learning-skills

**A simple system to help AI agents learn from their experiences.**

---

I built self-learning-skills because I noticed my agents often spent time poking around and guessing at things I had already solved in previous runs. I used to manually copy-paste those fixes into future prompts or backport them into my skills.

This repo streamlines that workflow. It acts as a sidecar memory that:

* Stops the guessing: Records "Aha moments" locally so the agent doesn't start from zero next time.
* Graduates knowledge: Includes a CLI workflow to Backport proven memories into permanent improvements in your actual skills or docs.
* It works with Claude Code, GitHub Copilot, and Codex and any other system that implements the  https://agentskills.io specification.


---

## ⚡ Quick Start

### 1) Install (pick the right skills folder for your agent)

Copy this entire directory into your agent’s **skills directory** as `self-learning-skills/`.

**Common locations:**

* **GitHub Copilot Agent:** `.github/skills/self-learning-skills/`
* **Claude Code (project):** `.claude/skills/self-learning-skills/`
* **Codex (repo):** `.codex/skills/self-learning-skills/`

> **Note:** The **memory store** is separate from the code.
> **By default**, it lives under `.agent-skills/` in your repo root (see `references/PORTABILITY.md` for project vs global options).

---

### 2) Initialize (one time per repo)

Run this from your repository root to create the storage structure and ignore it from version control.

> Replace `<SKILL_DIR>` with the install path from step (1), e.g. `.github/skills/self-learning-skills`.
> If you're running *this repo directly*, `<SKILL_DIR>` is `.`

```bash
python3 <SKILL_DIR>/scripts/self_learning.py init
```

* **Creates:** `.agent-skills/self-learning/v1/users/<user>/`
* **Protects:** Adds `.agent-skills/` to `.gitignore` so you don't commit local memory (use `--no-gitignore` to skip).
* **User:** `<user>` is a stable identifier for your local learning stream (see `references/PORTABILITY.md`).

---

### 3) Integrate (The Policy)

Agents do not automatically "know" to use this skill. You must give them a policy.

Copy & paste the block below into your project's main instruction file (e.g., `AGENTS.md`, `CLAUDE.md`, or `.github/copilot-instructions.md`).

> **Self-Learning Policy:**
>
> * **Before starting work:** Review prior learnings in `.agent-skills/self-learning/v1/users/<user>/INDEX.md` (or run the `review` command) and apply them to avoid repeating mistakes.
> * **After finishing work:** If you discovered a reusable pattern, fixed a tricky bug, or have a recommendation for next time, record 1–5 "Aha Cards" (and any Recommendations) using the `record` command.

See [AGENTS.md](AGENTS.md) for advanced configuration.

---

## 🛠 Operational Commands (Cheat Sheet)

Run these from your repository root:

### Dashboard (Review)

```bash
python3 <SKILL_DIR>/scripts/self_learning.py review --days 7
python3 <SKILL_DIR>/scripts/self_learning.py review --days 30 --scope portable
```

### Find a Memory (Recall)

```bash
python3 <SKILL_DIR>/scripts/self_learning.py list --query "pagination"
```

### Record a Memory (Post-Run)

```bash
python3 <SKILL_DIR>/scripts/self_learning.py record --json payload.json
```

Payload shape examples: [`references/FORMAT.md`](references/FORMAT.md)

### Repair / Normalize Indexes

```bash
python3 <SKILL_DIR>/scripts/self_learning.py repair --apply
```

### Recommendation Lifecycle

```bash
python3 <SKILL_DIR>/scripts/self_learning.py rec-status --id rec_... --status in_progress --note "working on it"
python3 <SKILL_DIR>/scripts/self_learning.py rec-status --id rec_... --status proposed --scope portable --note "Generalized; candidate for reuse/backport"
```

---

## 🚀 The Backporting Workflow: "Graduating" Knowledge

Backporting is how you take a proven "Aha Card" and turn it into a permanent improvement in another skill or documentation file.

### The Concept

1. **Discovery:** The agent learns something reusable and records an Aha Card.
2. **Generalize:** Rewrite it so it doesn’t depend on this repo (set `scope: "portable"` and remove project-only context).
3. **Validate:** You decide it belongs in a real skill, not just local memory.
4. **Backport:** You export an auditable bundle (optionally applying it).
5. **Result:** The target skill is permanently improved.
---

### How to Backport

#### 1) Identify Aha Card IDs

```bash
python3 <SKILL_DIR>/scripts/self_learning.py review --days 7
python3 <SKILL_DIR>/scripts/self_learning.py review --days 30 --scope portable
```

#### 2a) Generate a backport bundle + diff (Dry Run — No Changes)

```bash
python3 <SKILL_DIR>/scripts/self_learning.py export-backport \
  --skill-path <path-to-target-skill> \
  --ids aha_123,aha_456 \
  --make-diff
```

#### 2b) Apply the backport (Writes Changes)

```bash
python3 <SKILL_DIR>/scripts/self_learning.py export-backport \
  --skill-path <path-to-target-skill> \
  --ids aha_123,aha_456 \
  --apply
```

#### Inspect a target skill for backport markers

```bash
python3 <SKILL_DIR>/scripts/self_learning.py backport-inspect --skill-path <path-to-target-skill>
```

---

## 📂 Directory Structure

```text
self-learning-skills/
├── SKILL.md
├── AGENTS.md
├── README.md
├── scripts/
│   └── self_learning.py
└── references/
    ├── FORMAT.md
    ├── RUBRIC.md
    ├── INTEGRATION.md
    └── PORTABILITY.md
```

---

## 🧠 Storage Model

All data is stored in append-only JSONL files within `.agent-skills/self-learning/v1/users/<user>/`.

* **Key Files:**

  * `aha_cards.jsonl`: Durable, reusable knowledge.
  * `recommendations.jsonl`: Improvements for the next run.
  * `backports.jsonl`: A log of knowledge "graduated" to code.
  * `INDEX.md`: Human-readable dashboard (safe to delete/rebuild).

---

## 🏷 Scoping: `project` vs `portable`

Each Aha Card and Recommendation can include a `scope` field. This answers:

> “Does this read like a reusable developer tip/trick, or does it require this repo’s context?”

- `project`: specific to the current repo/run (default if omitted)
- `portable`: generally reusable; a good candidate for backporting into a skill or docs

Important: `scope` is about **content**. Store location (project-local vs global) and the promote/backport lifecycle are covered in `references/PORTABILITY.md`.

Practical workflows:

- Record something reusable by setting `"scope": "portable"` in your `record` payload (see `references/FORMAT.md`).
- Review only portable items: `python3 <SKILL_DIR>/scripts/self_learning.py review --scope portable --days 30`
- Reclassify an existing recommendation: `python3 <SKILL_DIR>/scripts/self_learning.py rec-status --id rec_... --status proposed --scope portable --note "..."`.

Portable-writing checklist (avoid leaking full project context):

- Replace repo/environment-specific values with placeholders (`<repo-root>`, `<ENV>`, `<SERVICE>`, `<PROJECT_KEY>`).
- Prefer shapes/templates/invariants over raw payload dumps.
- Avoid absolute paths in steps/evidence (they will be wrong after backporting).

Tip: use `shareable: true` only for content that’s safe to persist and potentially backport; never store secrets or sensitive payloads.

---

## Privacy / Safety

Avoid storing secrets or sensitive payloads in the memory store.

---

## License

MIT
