#!/usr/bin/env python3
"""
self_learning.py

Helper CLI for the `self-learning-skills` Agent Skill.

Goals:
- Keep dependencies to Python stdlib only.
- Work in most agent environments (Claude Code, Codex, Copilot Agent, etc.).
- Store learnings per-user, defaulting to a project-local, gitignored directory.
- Provide lightweight mechanisms to promote learnings globally or backport them into skills.

This script is OPTIONAL. The skill can be used without it by writing JSONL files directly.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import hashlib
import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# -----------------------------
# Utilities
# -----------------------------

SECRET_KEY_RE = re.compile(r"(api[_-]?key|token|secret|password|passwd|authorization|cookie)", re.I)
JWT_RE = re.compile(r"^[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+$")
HEXLIKE_RE = re.compile(r"^[a-f0-9]{32,}$", re.I)
BASE64LIKE_RE = re.compile(r"^[A-Za-z0-9+/=_-]{32,}$")

# Backport markers (used in skills / bundles for auditability and easy removal).
SKILL_BACKPORT_START_RE = re.compile(r"<!--\s*self-learning:backport:start(?:\s+id=[^\s]+)?\s*-->")
SKILL_BACKPORT_START_ID_RE = re.compile(r"<!--\s*self-learning:backport:start\s+id=([A-Za-z0-9_.-]+)\s*-->")
SKILL_BACKPORT_END_RE = re.compile(r"<!--\s*self-learning:backport:end\s*-->")
AHA_FILE_HEADER_BLOCK_RE = re.compile(r"\A\s*<!--\s*self-learning:aha-file\n.*?\n-->\s*\n*", re.DOTALL)
AHA_FILE_HEADER_META_RE = re.compile(r"<!--\s*self-learning:aha-file\n(.*?)\n-->", re.DOTALL)
AHA_CARD_START_ID_RE = re.compile(r"<!--\s*self-learning:aha:start\s+id=([A-Za-z0-9_.-]+)\b")
LEGACY_AHA_ID_RE = re.compile(r"-\s+\*\*ID:\*\*\s+`([^`]+)`")

RECOMMENDATION_STATUSES = {"proposed", "accepted", "in_progress", "done", "rejected", "deprecated"}
AHA_STATUSES = {"proposed", "accepted", "rejected", "deprecated", "backported"}

SIGNAL_KINDS = {
    "aha_used",
    "aha_recalled",
    "aha_reinforced",
    "aha_promoted",
    "aha_backported",
    "rec_used",
    "rec_touched",
    "rec_done",
}

SIGNAL_WEIGHTS = {
    # Aha-card scoring weights (simple + explainable).
    "aha_used": 2,
    "aha_recalled": 1,
    "aha_reinforced": 1,
    "aha_promoted": 1,
    "aha_backported": 2,
}


def _normalize_primary_skill(val: Any) -> str:
    """
    Ensure primary_skill is always a usable string (for filtering and portability).
    """
    if isinstance(val, str) and val.strip():
        s = val.strip()
        # If multiple skills are mentioned, keep only the first so filtering works
        # (e.g., "skill-a + skill-b" -> "skill-a").
        for sep in ["+", ",", ";", "|"]:
            if sep in s:
                s = s.split(sep, 1)[0].strip()
        if " " in s:
            s = s.split()[0].strip()
        return s or "unknown"
    return "unknown"


def _parse_id_list(val: Any, *, allow_empty: bool = True) -> List[str]:
    """
    Parse a list of ids from either:
      - a JSON array of strings
      - a comma-separated string ("aha_...,aha_...")
    Returns de-duped ids preserving order.
    """
    if val is None:
        return []
    parts: List[str] = []
    if isinstance(val, str):
        parts = [x.strip() for x in val.split(",") if x.strip()]
    elif isinstance(val, list):
        for x in val:
            if x is None:
                continue
            if isinstance(x, str) and x.strip():
                parts.append(x.strip())
    else:
        raise TypeError("Expected a list of strings or a comma-separated string")

    out: List[str] = []
    seen: set[str] = set()
    for x in parts:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)

    if not out and not allow_empty:
        raise ValueError("Expected at least one id")
    return out


VALID_SCOPES = {"project", "portable"}


def _normalize_scope(val: Any, *, default: str = "project") -> str:
    """
    Normalize scope for Recommendations/Aha Cards.

    Conventions:
      - project  : specific to the current repo/run; not intended for backport.
      - portable : generally reusable; a backport candidate.
    """
    if isinstance(val, str) and val.strip():
        scope = val.strip().lower()
        if scope in VALID_SCOPES:
            return scope
    return default


def _parse_iso_ts(ts: str) -> Optional[_dt.datetime]:
    """
    Parse ISO 8601 timestamps (supports 'Z' suffix).
    Returns an aware datetime in UTC when possible.
    """
    if not ts or not isinstance(ts, str):
        return None
    # LLMs sometimes output "YYYY-MM-DD HH:MM:SS" instead of using "T".
    # datetime.fromisoformat supports a space separator, but normalizing makes parsing more consistent.
    s = ts.strip().replace(" ", "T")
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dtv = _dt.datetime.fromisoformat(s)
        if dtv.tzinfo is None:
            dtv = dtv.replace(tzinfo=_dt.timezone.utc)
        return dtv.astimezone(_dt.timezone.utc)
    except Exception:
        return None


def _first_and_latest_by_id(items: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """
    Treat JSONL as an event stream; later lines override earlier for the same id.
    Returns (first, latest) maps.
    """
    first: Dict[str, Dict[str, Any]] = {}
    latest: Dict[str, Dict[str, Any]] = {}
    for obj in items:
        if not isinstance(obj, dict):
            continue
        rid = obj.get("id")
        if not rid:
            continue
        rid_s = str(rid)
        if rid_s not in first:
            first[rid_s] = obj
        latest[rid_s] = obj
    return first, latest


def _rec_status(obj: Dict[str, Any]) -> str:
    s = str(obj.get("status") or "").strip()
    # Back-compat aliases.
    aliases = {
        "implemented": "done",
        "complete": "done",
        "completed": "done",
        "in-progress": "in_progress",
        "inprogress": "in_progress",
    }
    s = aliases.get(s, s)
    return s if s in RECOMMENDATION_STATUSES else "proposed"


def _rec_last_touched_ts(obj: Dict[str, Any]) -> str:
    # Prefer explicit last_touched_ts; fallback to ts; fallback now.
    ts = obj.get("last_touched_ts") or obj.get("ts")
    if isinstance(ts, str) and ts.strip():
        return ts.strip()
    return iso_now()


def _aha_status(obj: Dict[str, Any]) -> str:
    s = str(obj.get("status") or "").strip()
    return s if s in AHA_STATUSES else "proposed"


def _aha_equivalence_key(obj: Dict[str, Any]) -> str:
    """
    Stable-ish key for detecting equivalent learnings (used for "reinforced").
    Prefer an explicit `key` field if provided; otherwise derive from (primary_skill, title, when_to_use).
    """
    explicit = obj.get("key")
    if isinstance(explicit, str) and explicit.strip():
        return f"key:{explicit.strip().lower()}"
    primary_skill = str(obj.get("primary_skill") or "").strip().lower()
    if primary_skill in {"unknown", "none", "null"}:
        primary_skill = ""
    title = str(obj.get("title") or "").strip().lower()
    when = str(obj.get("when_to_use") or "").strip().lower()
    # Keep keys reasonably stable even if some fields are missing.
    return f"{primary_skill}|{title}|{when}".strip("|")


def _merge_list_preserve(existing: Any, incoming: Any) -> List[Any]:
    ex = existing if isinstance(existing, list) else []
    inc = incoming if isinstance(incoming, list) else []
    out: List[Any] = []
    seen: set[str] = set()

    def _add(x: Any) -> None:
        if x is None:
            return
        if isinstance(x, (dict, list)):
            # Avoid complex merges; store as-is with best-effort de-dupe via JSON blob.
            key = json.dumps(x, ensure_ascii=False, sort_keys=True)
        else:
            key = str(x)
        if key in seen:
            return
        seen.add(key)
        out.append(x)

    for x in ex:
        _add(x)
    for x in inc:
        _add(x)
    return out


def _load_signals(store: Path) -> List[Dict[str, Any]]:
    return read_jsonl(store / "signals.jsonl")


def _aha_score_breakdown(aha_id: str, signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Dict[str, int] = {k: 0 for k in SIGNAL_WEIGHTS.keys()}
    for s in signals:
        if not isinstance(s, dict):
            continue
        if str(s.get("aha_id") or "") != aha_id:
            continue
        kind = str(s.get("kind") or "")
        if kind in counts:
            counts[kind] += 1

    base = 1
    weighted = {k: counts[k] * int(SIGNAL_WEIGHTS.get(k, 0)) for k in counts.keys()}
    score = base + sum(weighted.values())

    parts = []
    for k, w in weighted.items():
        if w:
            parts.append(f"{k}×{counts[k]} ({w})")
    explain = f"Score {score} = base {base}" + ((" + " + " + ".join(parts)) if parts else "")

    return {
        "aha_id": aha_id,
        "score": score,
        "base": base,
        "counts": counts,
        "weighted": weighted,
        "explain": explain,
    }


def _top_aha_by_score(
    aha_latest: Dict[str, Dict[str, Any]],
    signals: List[Dict[str, Any]],
    *,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for aha_id, card in aha_latest.items():
        bd = _aha_score_breakdown(aha_id, signals)
        ranked.append({
            "id": aha_id,
            "title": card.get("title"),
            "primary_skill": card.get("primary_skill"),
            "score": bd["score"],
            "explain": bd["explain"],
            "counts": bd["counts"],
        })
    ranked.sort(key=lambda x: (int(x.get("score") or 0), str(x.get("title") or "")), reverse=True)
    return ranked[: max(0, int(limit))]


def _impact_score(val: Any) -> int:
    s = str(val or "").strip().lower()
    return {"high": 3, "medium": 2, "low": 1}.get(s, 0)


def _recommendation_priority(rec: Dict[str, Any]) -> int:
    impact = rec.get("expected_impact") if isinstance(rec.get("expected_impact"), dict) else {}
    speed = _impact_score(impact.get("speed") if isinstance(impact, dict) else None)
    quality = _impact_score(impact.get("quality") if isinstance(impact, dict) else None)
    return speed * 10 + quality


def _days_ago(ts: str, now_utc: _dt.datetime) -> Optional[int]:
    dtv = _parse_iso_ts(ts)
    if not dtv:
        return None
    delta = now_utc - dtv
    if delta.total_seconds() < 0:
        return 0
    return int(delta.total_seconds() // 86400)


def iso_now() -> str:
    """UTC now as ISO-8601 with Z suffix (seconds precision)."""
    return (
        _dt.datetime.now(tz=_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def safe_user_slug() -> str:
    raw = os.environ.get("USER") or os.environ.get("USERNAME") or "default"
    raw = raw.strip() or "default"
    # Avoid leaking emails; keep it filesystem-safe.
    if "@" in raw:
        raw = (raw.split("@", 1)[0] or "").strip() or "default"
    user = re.sub(r"[^a-zA-Z0-9_.-]+", "_", raw)
    return user[:64] if len(user) > 64 else user


def find_repo_root() -> Path:
    """
    Best-effort repo root detection.
    Preference order:
      1) SELF_LEARNING_REPO_ROOT env var
      2) nearest parent of CWD containing .git
      3) if running inside a typical skills dir (.github/.claude/.codex), return its parent
      4) fallback: CWD
    """
    env = os.environ.get("SELF_LEARNING_REPO_ROOT")
    if env:
        return Path(env).expanduser().resolve()

    cwd = Path.cwd().resolve()
    for p in [cwd, *cwd.parents]:
        if (p / ".git").exists():
            return p

    # Common layout: <repo>/.github/skills/<skill>/scripts/...
    for p in [cwd, *cwd.parents]:
        if p.name in {".github", ".claude", ".codex"}:
            return p.parent

    return cwd


def project_store_dir(repo_root: Path, user: str) -> Path:
    return repo_root / ".agent-skills" / "self-learning" / "v1" / "users" / user


def global_store_dir(user: str) -> Path:
    env = os.environ.get("SELF_LEARNING_GLOBAL_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / ".agent-skills" / "self-learning" / "v1" / "users" / user


def ensure_store_dirs(store: Path) -> None:
    store.mkdir(parents=True, exist_ok=True)
    (store / "exports").mkdir(parents=True, exist_ok=True)
    (store / "exports" / "backports").mkdir(parents=True, exist_ok=True)


def _looks_sensitive_string(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    if JWT_RE.match(s):
        return True
    if HEXLIKE_RE.match(s):
        return True
    if BASE64LIKE_RE.match(s):
        # Avoid false positives for normal prose; require no whitespace.
        return (" " not in s) and ("\n" not in s)
    return False


def redact(obj: Any) -> Any:
    """
    Best-effort redaction:
    - If dict key looks secret-ish, replace value with "***REDACTED***"
    - If string looks like token/JWT/hex/base64, redact it
    """
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(k, str) and SECRET_KEY_RE.search(k):
                out[k] = "***REDACTED***"
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    if isinstance(obj, str):
        return "***REDACTED***" if _looks_sensitive_string(obj) else obj
    return obj


def stable_id(prefix: str, payload: str) -> str:
    h = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{h}"


def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # Skip corrupt lines rather than failing hard.
                continue
    return out


def append_signal(
    store: Path,
    *,
    kind: str,
    aha_id: Optional[str] = None,
    rec_id: Optional[str] = None,
    source: str = "agent",
    context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Append a scoring/usage signal to `signals.jsonl` (best-effort redaction).
    Returns the written record.
    """
    kind = str(kind or "").strip()
    if kind not in SIGNAL_KINDS:
        raise ValueError(f"Invalid signal kind: {kind}")
    if bool(aha_id) == bool(rec_id):
        raise ValueError("Provide exactly one of aha_id or rec_id")

    ts = iso_now()
    record: Dict[str, Any] = {
        "ts": ts,
        "kind": kind,
        "source": str(source or "agent"),
    }
    if aha_id:
        record["aha_id"] = str(aha_id)
    if rec_id:
        record["rec_id"] = str(rec_id)
    if context:
        record["context"] = str(context)

    payload = f"{ts}|{kind}|{record.get('aha_id','')}|{record.get('rec_id','')}|{record.get('source','')}|{record.get('context','')}"
    record["id"] = stable_id("sig", payload)

    signals_path = store / "signals.jsonl"
    append_jsonl(signals_path, redact(record))
    return record


def tail_lines(path: Path, n: int = 20) -> List[str]:
    if not path.exists():
        return []
    # Simple approach: read all if small; otherwise do a backwards seek.
    try:
        data = path.read_text(encoding="utf-8")
        lines = [ln for ln in data.splitlines() if ln.strip()]
        return lines[-n:]
    except Exception:
        return []


def update_index_md(store: Path) -> None:
    """
    Generate a small, human-friendly INDEX.md for quick skimming.
    Best-effort; never fail the command if this errors.
    """
    try:
        aha_path = store / "aha_cards.jsonl"
        rec_path = store / "recommendations.jsonl"
        bp_path = store / "backports.jsonl"
        sig_path = store / "signals.jsonl"
        aha_lines = tail_lines(aha_path, 10)
        rec_lines = tail_lines(rec_path, 10)
        bp_lines = tail_lines(bp_path, 10)

        def _bullets(lines: List[str]) -> str:
            bullets: List[str] = []
            for ln in lines[::-1]:  # newest first
                try:
                    obj = json.loads(ln)
                    title = obj.get("title", "(untitled)")
                    cid = obj.get("id", "")
                    ts = obj.get("ts", "")
                    bullets.append(f"- **{title}** (`{cid}`, {ts})")
                except Exception:
                    continue
            return "\n".join(bullets) if bullets else "_(none yet)_"

        def _backport_bullets(lines: List[str]) -> str:
            bullets: List[str] = []
            for ln in lines[::-1]:  # newest first
                try:
                    obj = json.loads(ln)
                    target = obj.get("target_skill") or obj.get("target_skill_name") or "(unknown skill)"
                    bp_id = obj.get("backport_id") or obj.get("id", "")
                    ts = obj.get("ts", "")
                    bullets.append(f"- **{target}** (`{bp_id}`, {ts})")
                except Exception:
                    continue
            return "\n".join(bullets) if bullets else "_(none yet)_"

        # Best-effort "dashboard" sections (may read full JSONL).
        top_aha_md = ""
        open_recs_md = ""
        stale_recs_md = ""
        backport_candidates_md = ""
        try:
            now_utc = _dt.datetime.now(tz=_dt.timezone.utc).replace(microsecond=0)

            aha_all = read_jsonl(aha_path)
            rec_all = read_jsonl(rec_path)
            sig_all = read_jsonl(sig_path)
            bp_all = read_jsonl(bp_path)

            _, aha_latest = _first_and_latest_by_id(aha_all)
            rec_first, rec_latest = _first_and_latest_by_id(rec_all)

            backported_ids: set[str] = set()
            for b in bp_all:
                if not isinstance(b, dict):
                    continue
                if not b.get("applied"):
                    continue
                for cid in (b.get("result_card_ids") or b.get("requested_card_ids") or []):
                    if cid:
                        backported_ids.add(str(cid))
            for cid, c in aha_latest.items():
                if _aha_status(c) == "backported":
                    backported_ids.add(cid)

            # Top Aha Cards by score
            top_aha = _top_aha_by_score(aha_latest, sig_all, limit=5)
            if top_aha:
                lines = []
                for c in top_aha:
                    title = c.get("title") or "(untitled)"
                    lines.append(f"- **{title}** (`{c.get('id')}`, score {c.get('score')})")
                top_aha_md = "\n".join(lines)
            else:
                top_aha_md = "_(none yet)_"

            # Open + stale recommendations
            open_statuses = {"proposed", "accepted", "in_progress"}
            open_recs: List[Dict[str, Any]] = []
            stale_recs: List[Dict[str, Any]] = []

            for rid, rec in rec_latest.items():
                if not isinstance(rec, dict):
                    continue
                st = _rec_status(rec)
                if st not in open_statuses:
                    continue
                lt = _rec_last_touched_ts(rec)
                days_since = _days_ago(lt, now_utc)
                open_recs.append({
                    "id": rid,
                    "title": rec.get("title"),
                    "status": st,
                    "scope": _normalize_scope(rec.get("scope"), default="project"),
                    "last_touched_ts": lt,
                    "days_since": days_since,
                    "priority": _recommendation_priority(rec),
                    "created_ts": str(rec_first.get(rid, {}).get("ts") or ""),
                })
                if days_since is not None and days_since >= 7:
                    stale_recs.append(open_recs[-1])

            open_recs.sort(key=lambda r: (int(r.get("priority") or 0), int(r.get("days_since") or 0)), reverse=True)
            stale_recs.sort(key=lambda r: (int(r.get("days_since") or 0), int(r.get("priority") or 0)), reverse=True)

            def _rec_lines(items: List[Dict[str, Any]], limit: int) -> str:
                if not items:
                    return "_(none)_"
                out = []
                for r in items[:limit]:
                    title = r.get("title") or "(untitled)"
                    days = r.get("days_since")
                    days_s = f"{days}d ago" if isinstance(days, int) else "unknown age"
                    scope = _normalize_scope(r.get("scope"), default="project")
                    out.append(f"- **{title}** (`{r.get('id')}`, {r.get('status')}, {scope}, {days_s})")
                return "\n".join(out)

            open_recs_md = _rec_lines(open_recs, 10)
            stale_recs_md = _rec_lines(stale_recs, 10)

            # Backport candidates preview (shareable, not backported, score>=4 or reinforced/used)
            candidates: List[Dict[str, Any]] = []
            for cid, card in aha_latest.items():
                if cid in backported_ids:
                    continue
                if card.get("shareable") is False:
                    continue
                if _aha_status(card) in {"rejected", "deprecated", "backported"}:
                    continue
                if not bool(card.get("shareable")):
                    continue
                bd = _aha_score_breakdown(cid, sig_all)
                if bd["score"] < 4 and int(bd["counts"].get("aha_reinforced") or 0) < 1 and int(bd["counts"].get("aha_used") or 0) < 1:
                    continue
                candidates.append({
                    "id": cid,
                    "title": card.get("title"),
                    "primary_skill": card.get("primary_skill"),
                    "score": bd["score"],
                })
            candidates.sort(key=lambda x: (int(x.get("score") or 0), str(x.get("title") or "")), reverse=True)
            if candidates:
                lines = []
                for c in candidates[:5]:
                    title = c.get("title") or "(untitled)"
                    ps = c.get("primary_skill") or ""
                    ps_s = f" [{ps}]" if ps else ""
                    lines.append(f"- **{title}** (`{c.get('id')}`, score {c.get('score')}){ps_s}")
                backport_candidates_md = "\n".join(lines)
            else:
                backport_candidates_md = "_(none yet)_"
        except Exception:
            top_aha_md = "_(unavailable)_"
            open_recs_md = "_(unavailable)_"
            stale_recs_md = "_(unavailable)_"
            backport_candidates_md = "_(unavailable)_"

        md = f"""# Self-learning index

This file is generated by `scripts/self_learning.py` (best-effort).

## Top Aha Cards (score)

{top_aha_md}

## Open Recommendations

{open_recs_md}

## Stale Recommendations (≥7d)

{stale_recs_md}

## Backport Candidates (preview)

{backport_candidates_md}

## Latest Aha Cards

{_bullets(aha_lines)}

## Latest Backports

{_backport_bullets(bp_lines)}

## Latest Recommendations

{_bullets(rec_lines)}
"""
        (store / "INDEX.md").write_text(md, encoding="utf-8")
    except Exception:
        return


# -----------------------------
# Commands
# -----------------------------

def cmd_init(args: argparse.Namespace) -> int:
    user = safe_user_slug()
    repo = find_repo_root()
    store = project_store_dir(repo, user)
    ensure_store_dirs(store)

    # Ensure gitignore contains .agent-skills/
    if args.gitignore:
        gi = repo / ".gitignore"
        try:
            existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
            if ".agent-skills/" not in existing:
                with gi.open("a", encoding="utf-8") as f:
                    if existing and not existing.endswith("\n"):
                        f.write("\n")
                    f.write("\n# Local per-user agent skill memory\n.agent-skills/\n")
        except Exception:
            # Don't fail init if gitignore isn't writable.
            pass

    print(json.dumps({
        "repo_root": str(repo),
        "user": user,
        "project_store": str(store),
        "global_store": str(global_store_dir(user)),
        "note": "Project store created. Add .agent-skills/ to .gitignore if you haven't."
    }, indent=2))
    return 0


def _load_payload_from_stdin_or_file(path: Optional[str]) -> Dict[str, Any]:
    if path:
        p = Path(path).expanduser()
        return json.loads(p.read_text(encoding="utf-8"))
    raw = sys.stdin.read()
    if not raw.strip():
        raise SystemExit("No input provided. Provide --json <file> or pipe JSON into stdin.")
    return json.loads(raw)


def _normalize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    event = dict(event)
    event.setdefault("ts", iso_now())
    payload = f"{event.get('ts','')}|{event.get('task_summary','')}|{event.get('primary_skill','')}"
    event.setdefault("id", stable_id("evt", payload))
    return event


def _normalize_items(items: Iterable[Dict[str, Any]], prefix: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in items:
        obj = dict(item)
        obj.setdefault("ts", iso_now())
        # Try to build a stable-ish id from title + when_to_use.
        payload = f"{obj.get('ts','')}|{obj.get('title','')}|{obj.get('when_to_use','')}|{obj.get('primary_skill','')}"
        obj.setdefault("id", stable_id(prefix, payload))
        out.append(obj)
    return out


def cmd_record(args: argparse.Namespace) -> int:
    user = safe_user_slug()
    repo = find_repo_root()
    store = project_store_dir(repo, user)
    ensure_store_dirs(store)

    payload = _load_payload_from_stdin_or_file(args.json)
    if not isinstance(payload, dict):
        raise SystemExit("Input must be a JSON object with keys: event, aha_cards, recommendations (any subset).")

    event = payload.get("event")
    aha_cards = payload.get("aha_cards", [])
    recs = payload.get("recommendations", [])
    used_aha_ids_raw = payload.get("used_aha_ids")
    used_rec_ids_raw = payload.get("used_rec_ids")
    used_obj = payload.get("used") if isinstance(payload.get("used"), dict) else {}
    usage_source = payload.get("usage_source")
    usage_context = payload.get("usage_context")

    if event is not None and not isinstance(event, dict):
        raise SystemExit("'event' must be a JSON object if provided.")
    if not isinstance(aha_cards, list):
        raise SystemExit("'aha_cards' must be an array.")
    if not isinstance(recs, list):
        raise SystemExit("'recommendations' must be an array.")

    try:
        used_aha_ids = _parse_id_list(used_aha_ids_raw)
        used_rec_ids = _parse_id_list(used_rec_ids_raw)
        used_aha_ids += _parse_id_list(used_obj.get("aha_ids"))
        used_rec_ids += _parse_id_list(used_obj.get("rec_ids"))
    except Exception as e:
        raise SystemExit(f"Invalid used ids in payload: {e}")

    # Redact first.
    event_r = redact(event) if event else None
    aha_r = [redact(x) for x in aha_cards]
    recs_r = [redact(x) for x in recs]

    # Ensure primary_skill is always present and usable for filtering.
    default_primary_skill: Optional[str] = None
    if event_r:
        ps = event_r.get("primary_skill")
        if isinstance(ps, str) and ps.strip():
            default_primary_skill = _normalize_primary_skill(ps)
    if not default_primary_skill:
        candidates: List[str] = []
        for item in [*aha_r, *recs_r]:
            if not isinstance(item, dict):
                continue
            ps = item.get("primary_skill")
            if isinstance(ps, str) and ps.strip():
                candidates.append(_normalize_primary_skill(ps))
        uniq = sorted(set(candidates))
        if len(uniq) == 1:
            default_primary_skill = uniq[0]

    if event_r:
        event_r = dict(event_r)
        event_r["primary_skill"] = _normalize_primary_skill(event_r.get("primary_skill") or default_primary_skill)

    aha_norm: List[Dict[str, Any]] = []
    for x in aha_r:
        if not isinstance(x, dict):
            continue
        obj = dict(x)
        obj["primary_skill"] = _normalize_primary_skill(obj.get("primary_skill") or default_primary_skill)
        obj["scope"] = _normalize_scope(obj.get("scope"), default="project")
        aha_norm.append(obj)

    rec_norm: List[Dict[str, Any]] = []
    for x in recs_r:
        if not isinstance(x, dict):
            continue
        obj = dict(x)
        obj["primary_skill"] = _normalize_primary_skill(obj.get("primary_skill") or default_primary_skill)
        # Recommendations default to project scope unless explicitly marked portable.
        obj["scope"] = _normalize_scope(obj.get("scope"), default="project")
        rec_norm.append(obj)

    written: Dict[str, str] = {}

    if event_r:
        e = _normalize_event(event_r)
        append_jsonl(store / "events.jsonl", e)
        written["events"] = str(store / "events.jsonl")
        # Prefer a stable event id for usage signal context.
        if not usage_context:
            usage_context = f"event_id={e.get('id')}"

    if aha_norm:
        existing_lines = read_jsonl(store / "aha_cards.jsonl")
        _, existing_latest = _first_and_latest_by_id(existing_lines)
        key_to_id: Dict[str, str] = {}
        # Build key->id map using file order (earliest wins).
        for ln in existing_lines:
            if not isinstance(ln, dict):
                continue
            cid = ln.get("id")
            if not cid:
                continue
            key = _aha_equivalence_key(ln)
            if not key or key in key_to_id:
                continue
            key_to_id[key] = str(cid)

        cards_n = _normalize_items(aha_norm, "aha")
        for c in cards_n:
            c["status"] = _aha_status(c)
            key = _aha_equivalence_key(c)
            existing_id = key_to_id.get(key)
            if not existing_id:
                # Back-compat: match legacy cards that did not include primary_skill in their equivalence key.
                title = str(c.get("title") or "").strip().lower()
                when = str(c.get("when_to_use") or "").strip().lower()
                legacy_key = f"{title}|{when}".strip("|")
                existing_id = key_to_id.get(legacy_key)
            if existing_id and existing_id in existing_latest:
                # Treat "we learned this again" as a reinforcement signal. Only append a full card update
                # if the merged content actually changes (e.g., new evidence/steps/tags).
                current = dict(existing_latest[existing_id])
                merged = dict(current)
                merged["primary_skill"] = _normalize_primary_skill(merged.get("primary_skill") or c.get("primary_skill"))
                merged["status"] = _aha_status(merged)
                merged["title"] = merged.get("title") or c.get("title")
                merged["when_to_use"] = merged.get("when_to_use") or c.get("when_to_use")
                merged["problem"] = merged.get("problem") or c.get("problem")
                merged["scope"] = merged.get("scope") or c.get("scope")
                if merged.get("shareable") is None:
                    merged["shareable"] = c.get("shareable")
                merged["solution_steps"] = _merge_list_preserve(merged.get("solution_steps"), c.get("solution_steps"))
                merged["evidence"] = _merge_list_preserve(merged.get("evidence"), c.get("evidence"))
                merged["tags"] = _merge_list_preserve(merged.get("tags"), c.get("tags"))

                cur_cmp = dict(current)
                cur_cmp.pop("ts", None)
                mer_cmp = dict(merged)
                mer_cmp.pop("ts", None)
                if json.dumps(cur_cmp, ensure_ascii=False, sort_keys=True) != json.dumps(mer_cmp, ensure_ascii=False, sort_keys=True):
                    merged["ts"] = iso_now()
                    append_jsonl(store / "aha_cards.jsonl", redact(merged))
                try:
                    append_signal(
                        store,
                        kind="aha_reinforced",
                        aha_id=existing_id,
                        source="agent",
                        context=f"equivalent capture observed (key={key})",
                    )
                except Exception:
                    pass
            else:
                append_jsonl(store / "aha_cards.jsonl", redact(c))
                if key:
                    key_to_id[key] = str(c.get("id"))
                    title = str(c.get("title") or "").strip().lower()
                    when = str(c.get("when_to_use") or "").strip().lower()
                    legacy_key = f"{title}|{when}".strip("|")
                    if legacy_key and legacy_key not in key_to_id:
                        key_to_id[legacy_key] = str(c.get("id"))
        written["aha_cards"] = str(store / "aha_cards.jsonl")

    if rec_norm:
        recs_n = _normalize_items(rec_norm, "rec")
        for r in recs_n:
            r["status"] = _rec_status(r)
            r.setdefault("last_touched_ts", r.get("ts") or iso_now())
            r["primary_skill"] = _normalize_primary_skill(r.get("primary_skill") or default_primary_skill)
            append_jsonl(store / "recommendations.jsonl", redact(r))
        written["recommendations"] = str(store / "recommendations.jsonl")

    usage_signals: Dict[str, Any] = {"written": [], "invalid_ids": [], "errors": []}
    try:
        # De-dupe while preserving order (and ignore blanks).
        used_aha_ids = _parse_id_list(used_aha_ids)
        used_rec_ids = _parse_id_list(used_rec_ids)
        source = str(usage_source or "agent").strip() or "agent"
        context = str(usage_context).strip() if isinstance(usage_context, str) and usage_context.strip() else None

        for cid in used_aha_ids:
            if not str(cid).startswith("aha_"):
                usage_signals["invalid_ids"].append({"id": cid, "expected_prefix": "aha_"})
                continue
            try:
                usage_signals["written"].append(
                    append_signal(store, kind="aha_used", aha_id=str(cid), source=source, context=context)
                )
            except Exception as exc:
                usage_signals["errors"].append({"id": cid, "error": str(exc)})

        for rid in used_rec_ids:
            if not str(rid).startswith("rec_"):
                usage_signals["invalid_ids"].append({"id": rid, "expected_prefix": "rec_"})
                continue
            try:
                usage_signals["written"].append(
                    append_signal(store, kind="rec_used", rec_id=str(rid), source=source, context=context)
                )
            except Exception as exc:
                usage_signals["errors"].append({"id": rid, "error": str(exc)})
    except Exception as exc:
        usage_signals["errors"].append({"error": str(exc)})

    try:
        update_index_md(store)
    except Exception:
        pass

    print(json.dumps({
        "ok": True,
        "repo_root": str(repo),
        "user": user,
        "project_store": str(store),
        "written": written,
        "usage_signals": usage_signals,
    }, indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    user = safe_user_slug()
    repo = find_repo_root()
    store = project_store_dir(repo, user)
    aha_path = store / "aha_cards.jsonl"

    cards = read_jsonl(aha_path)
    if not cards:
        # Cold start handler: avoid encouraging hallucinated "memories" when the store is empty.
        print(json.dumps({
            "repo_root": str(repo),
            "user": user,
            "count": 0,
            "items": [],
            "message": "No memories recorded yet. Proceed with the task using standard tools.",
        }, indent=2, ensure_ascii=False))
        return 0

    def _match(card: Dict[str, Any]) -> bool:
        if args.skill and card.get("primary_skill") != args.skill:
            return False
        if args.tag:
            tags = card.get("tags") or []
            if isinstance(tags, list) and args.tag not in tags:
                return False
        if args.query:
            q = args.query.lower()
            blob = json.dumps(card, ensure_ascii=False).lower()
            return q in blob
        return True

    filtered = [c for c in cards if _match(c)]
    if args.limit:
        filtered = filtered[-args.limit:]

    print(json.dumps({
        "repo_root": str(repo),
        "user": user,
        "count": len(filtered),
        "items": filtered,
    }, indent=2, ensure_ascii=False))
    return 0


def cmd_rec_status(args: argparse.Namespace) -> int:
    user = safe_user_slug()
    repo = find_repo_root()
    store = project_store_dir(repo, user)
    ensure_store_dirs(store)

    rec_path = store / "recommendations.jsonl"
    recs = read_jsonl(rec_path)
    first, latest = _first_and_latest_by_id(recs)

    rec_id = str(args.id or "").strip()
    if not rec_id:
        raise SystemExit("Provide --id rec_...")
    if rec_id not in latest:
        raise SystemExit(f"Recommendation id not found in project store: {rec_id}")

    new_status = str(args.status or "").strip()
    if new_status not in RECOMMENDATION_STATUSES:
        raise SystemExit(f"Invalid --status {new_status!r}. Expected one of: {', '.join(sorted(RECOMMENDATION_STATUSES))}")

    now = iso_now()
    current = latest[rec_id]
    updated = dict(current)
    updated["ts"] = now
    updated["status"] = new_status
    updated["last_touched_ts"] = now
    updated["scope"] = _normalize_scope(args.scope if args.scope else updated.get("scope"), default="project")
    if args.note:
        updated["note"] = str(args.note)

    append_jsonl(rec_path, redact(updated))
    try:
        append_signal(store, kind="rec_touched", rec_id=rec_id, source="agent", context=f"status={new_status}")
        if new_status == "done":
            append_signal(store, kind="rec_done", rec_id=rec_id, source="agent")
    except Exception:
        # Best-effort; do not fail status updates if signals cannot be written.
        pass
    try:
        update_index_md(store)
    except Exception:
        pass

    created = first[rec_id]
    print(json.dumps({
        "ok": True,
        "repo_root": str(repo),
        "user": user,
        "project_store": str(store),
        "id": rec_id,
        "previous": {
            "status": _rec_status(current),
            "last_touched_ts": _rec_last_touched_ts(current),
            "ts": current.get("ts"),
            "created_ts": created.get("ts"),
            "title": current.get("title"),
            "scope": _normalize_scope(current.get("scope"), default="project"),
        },
        "updated": {
            "status": new_status,
            "last_touched_ts": now,
            "ts": now,
            "note": updated.get("note"),
            "scope": updated.get("scope"),
        },
        "written_to": str(rec_path),
    }, indent=2, ensure_ascii=False))
    return 0


def cmd_signal(args: argparse.Namespace) -> int:
    user = safe_user_slug()
    repo = find_repo_root()
    store = project_store_dir(repo, user)
    ensure_store_dirs(store)

    aha_id = str(args.aha_id).strip() if args.aha_id else None
    rec_id = str(args.rec_id).strip() if args.rec_id else None
    kind = str(args.kind or "").strip()
    source = str(args.source or "manual").strip() or "manual"
    context = str(args.context) if args.context else None

    try:
        rec = append_signal(store, kind=kind, aha_id=aha_id, rec_id=rec_id, source=source, context=context)
    except Exception as e:
        raise SystemExit(str(e))

    try:
        update_index_md(store)
    except Exception:
        pass

    print(json.dumps({
        "ok": True,
        "repo_root": str(repo),
        "user": user,
        "project_store": str(store),
        "written_to": str(store / "signals.jsonl"),
        "signal": rec,
    }, indent=2, ensure_ascii=False))
    return 0


def cmd_use(args: argparse.Namespace) -> int:
    """
    Convenience helper to mark existing learnings as "used" (writes to signals.jsonl).
    This avoids having to call `signal` repeatedly.
    """
    user = safe_user_slug()
    repo = find_repo_root()
    store = project_store_dir(repo, user)
    ensure_store_dirs(store)

    aha_ids = _parse_id_list(args.aha_ids) if args.aha_ids else []
    rec_ids = _parse_id_list(args.rec_ids) if args.rec_ids else []
    if not aha_ids and not rec_ids:
        raise SystemExit("Provide --aha <aha_...[,aha_...]> and/or --rec <rec_...[,rec_...]>" )

    source = str(args.source or "agent").strip() or "agent"
    context = str(args.context).strip() if args.context else None

    written: List[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for cid in aha_ids:
        if not str(cid).startswith("aha_"):
            invalid.append({"id": cid, "expected_prefix": "aha_"})
            continue
        try:
            written.append(append_signal(store, kind="aha_used", aha_id=str(cid), source=source, context=context))
        except Exception as exc:
            errors.append({"id": cid, "error": str(exc)})

    for rid in rec_ids:
        if not str(rid).startswith("rec_"):
            invalid.append({"id": rid, "expected_prefix": "rec_"})
            continue
        try:
            written.append(append_signal(store, kind="rec_used", rec_id=str(rid), source=source, context=context))
        except Exception as exc:
            errors.append({"id": rid, "error": str(exc)})

    try:
        update_index_md(store)
    except Exception:
        pass

    print(json.dumps({
        "ok": True,
        "repo_root": str(repo),
        "user": user,
        "project_store": str(store),
        "written_to": str(store / "signals.jsonl"),
        "signals_written": written,
        "invalid_ids": invalid,
        "errors": errors,
    }, indent=2, ensure_ascii=False))
    return 0


def cmd_aha_status(args: argparse.Namespace) -> int:
    user = safe_user_slug()
    repo = find_repo_root()
    store = project_store_dir(repo, user)
    ensure_store_dirs(store)

    aha_path = store / "aha_cards.jsonl"
    cards = read_jsonl(aha_path)
    first, latest = _first_and_latest_by_id(cards)

    aha_id = str(args.id or "").strip()
    if not aha_id:
        raise SystemExit("Provide --id aha_...")
    if aha_id not in latest:
        raise SystemExit(f"Aha Card id not found in project store: {aha_id}")

    new_status = str(args.status or "").strip()
    if new_status not in AHA_STATUSES:
        raise SystemExit(f"Invalid --status {new_status!r}. Expected one of: {', '.join(sorted(AHA_STATUSES))}")

    now = iso_now()
    current = latest[aha_id]
    updated = dict(current)
    updated["ts"] = now
    updated["status"] = new_status
    updated["last_touched_ts"] = now
    if args.note:
        updated["note"] = str(args.note)

    append_jsonl(aha_path, redact(updated))
    try:
        update_index_md(store)
    except Exception:
        pass

    created = first[aha_id]
    print(json.dumps({
        "ok": True,
        "repo_root": str(repo),
        "user": user,
        "project_store": str(store),
        "id": aha_id,
        "previous": {
            "status": _aha_status(current),
            "ts": current.get("ts"),
            "created_ts": created.get("ts"),
            "title": current.get("title"),
        },
        "updated": {
            "status": new_status,
            "ts": now,
            "note": updated.get("note"),
        },
        "written_to": str(aha_path),
    }, indent=2, ensure_ascii=False))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    user = safe_user_slug()
    repo = find_repo_root()
    store = project_store_dir(repo, user)
    ensure_store_dirs(store)

    now_utc = _dt.datetime.now(tz=_dt.timezone.utc).replace(microsecond=0)

    # Time window (optional)
    since_dt: Optional[_dt.datetime] = None
    if args.since:
        since_dt = _parse_iso_ts(str(args.since))
        if since_dt is None:
            raise SystemExit("Invalid --since (expected ISO-8601 like 2025-12-26T00:00:00Z)")
    elif args.days is not None:
        since_dt = now_utc - _dt.timedelta(days=max(0, int(args.days)))

    stale_days = max(0, int(args.stale_days))
    skill_filter = str(args.skill).strip() if args.skill else None
    scope_filter = str(args.scope).strip() if args.scope else None
    query_filter = str(args.query).strip().lower() if args.query else None
    status_filter = [s.strip() for s in (args.status or "").split(",") if s.strip()] if args.status else []
    status_filter_set = set(status_filter)

    # Load stores
    aha_lines = read_jsonl(store / "aha_cards.jsonl")
    rec_lines = read_jsonl(store / "recommendations.jsonl")
    signals = _load_signals(store)
    bp_lines = read_jsonl(store / "backports.jsonl")

    global_store = global_store_dir(user)
    global_aha_lines = read_jsonl(global_store / "aha_cards.jsonl") if bool(args.include_global) else []

    # Build first/latest and counts
    rec_first, rec_latest = _first_and_latest_by_id(rec_lines)
    aha_first, aha_latest = _first_and_latest_by_id(aha_lines)

    rec_counts: Dict[str, int] = {}
    for r in rec_lines:
        rid = r.get("id") if isinstance(r, dict) else None
        if rid:
            rec_counts[str(rid)] = rec_counts.get(str(rid), 0) + 1

    # Backported ids (applied backports + explicit status)
    backported_ids: set[str] = set()
    for b in bp_lines:
        if not isinstance(b, dict):
            continue
        if not b.get("applied"):
            continue
        for cid in (b.get("result_card_ids") or b.get("requested_card_ids") or []):
            if cid:
                backported_ids.add(str(cid))
    for cid, c in aha_latest.items():
        if _aha_status(c) == "backported":
            backported_ids.add(cid)

    def _matches_common(obj: Dict[str, Any]) -> bool:
        if skill_filter and str(obj.get("primary_skill") or "") != skill_filter:
            return False
        if scope_filter and _normalize_scope(obj.get("scope"), default="project") != scope_filter:
            return False
        if query_filter:
            blob = json.dumps(obj, ensure_ascii=False).lower()
            if query_filter not in blob:
                return False
        if since_dt:
            ts = obj.get("last_touched_ts") or obj.get("ts")
            dtv = _parse_iso_ts(str(ts)) if ts else None
            if not dtv or dtv < since_dt:
                return False
        return True

    # Recommendations: normalize + classify
    open_statuses = {"proposed", "accepted", "in_progress"}
    open_recs: List[Dict[str, Any]] = []
    stale_recs: List[Dict[str, Any]] = []
    untouched_recs: List[Dict[str, Any]] = []
    recs_by_status: Dict[str, List[Dict[str, Any]]] = {s: [] for s in sorted(RECOMMENDATION_STATUSES)}

    # Precompute rec_touched signals.
    rec_signal_ids: set[str] = set()
    for s in signals:
        if isinstance(s, dict) and s.get("rec_id"):
            rec_signal_ids.add(str(s.get("rec_id")))

    for rid, rec in rec_latest.items():
        if not isinstance(rec, dict):
            continue
        if not _matches_common(rec):
            continue

        st = _rec_status(rec)
        lt = _rec_last_touched_ts(rec)
        created_ts = str(rec_first.get(rid, {}).get("ts") or "")
        scope = _normalize_scope(rec.get("scope"), default="project")
        rec_view = {
            "id": rid,
            "title": rec.get("title"),
            "status": st,
            "created_ts": created_ts,
            "last_touched_ts": lt,
            "scope": scope,
            "priority": _recommendation_priority(rec),
            "expected_impact": rec.get("expected_impact"),
            "primary_skill": rec.get("primary_skill"),
            "tags": rec.get("tags"),
            "why": rec.get("why"),
            "implementation_hint": rec.get("implementation_hint"),
        }
        recs_by_status.setdefault(st, []).append(rec_view)

        if st in open_statuses:
            open_recs.append(rec_view)
            days_since_touch = _days_ago(lt, now_utc)
            if days_since_touch is not None and days_since_touch >= stale_days:
                stale_recs.append(rec_view)

            touched = (rec_counts.get(rid, 0) > 1) or (rid in rec_signal_ids)
            if not touched:
                untouched_recs.append(rec_view)

    open_recs.sort(
        key=lambda r: (
            int(r.get("priority") or 0),
            int(_days_ago(r.get("last_touched_ts") or "", now_utc) or 0),
        ),
        reverse=True,
    )
    stale_recs.sort(key=lambda r: (int(_days_ago(r.get("last_touched_ts") or "", now_utc) or 0), int(r.get("priority") or 0)), reverse=True)
    untouched_recs.sort(
        key=lambda r: (
            int(r.get("priority") or 0),
            int(_days_ago(r.get("created_ts") or "", now_utc) or 0),
        ),
        reverse=True,
    )

    # Apply status filter if requested.
    if status_filter_set:
        for st in list(recs_by_status.keys()):
            if st not in status_filter_set:
                recs_by_status.pop(st, None)

    # Aha cards: scoring + backport candidates
    aha_candidates: List[Dict[str, Any]] = []
    for cid, card in aha_latest.items():
        if not isinstance(card, dict):
            continue
        if not _matches_common(card):
            continue
        if cid in backported_ids:
            continue
        if card.get("shareable") is False:
            continue
        if _aha_status(card) in {"rejected", "deprecated"}:
            continue

        bd = _aha_score_breakdown(cid, signals)
        reinforced = int(bd["counts"].get("aha_reinforced") or 0)
        used = int(bd["counts"].get("aha_used") or 0)
        shareable = bool(card.get("shareable"))
        if not shareable:
            continue
        if bd["score"] < int(args.min_aha_score) and reinforced < 1 and used < 1 and _aha_status(card) != "accepted":
            continue

        tags = card.get("tags") if isinstance(card.get("tags"), list) else []
        artifact = "reference-file"
        tag_blob = " ".join(str(t).lower() for t in (tags or []))
        if "template" in tag_blob or "query" in tag_blob:
            artifact = "template"
        elif "schema" in tag_blob:
            artifact = "reference-file"
        elif "script" in tag_blob or "tooling" in tag_blob:
            artifact = "script"
        elif "skill" in tag_blob or "docs" in tag_blob:
            artifact = "skill-md-snippet"

        aha_candidates.append({
            "id": cid,
            "title": card.get("title"),
            "primary_skill": card.get("primary_skill"),
            "score": bd["score"],
            "explain": bd["explain"],
            "tags": tags,
            "artifact_suggestion": artifact,
            "how_to_backport": f"python3 <SKILL_DIR>/scripts/self_learning.py export-backport --skill-path <target-skill-dir> --ids {cid} --make-diff",
        })

    aha_candidates.sort(key=lambda x: (int(x.get("score") or 0), str(x.get("title") or "")), reverse=True)
    aha_candidates = aha_candidates[: max(0, int(args.backport_limit))]

    top_aha = _top_aha_by_score(
        {k: v for k, v in aha_latest.items() if _matches_common(v)},
        signals,
        limit=max(0, int(args.top_aha_limit)),
    )

    # Next actions: mix open recs and backport candidates
    next_actions: List[Dict[str, Any]] = []
    for r in open_recs[: max(0, int(args.next_actions_limit))]:
        next_actions.append({
            "type": "recommendation",
            "id": r["id"],
            "title": r.get("title"),
            "status": r.get("status"),
            "scope": r.get("scope"),
            "why": r.get("why"),
            "suggested_next": "mark in_progress and implement, or reject/deprecate if no longer relevant",
        })
    for c in aha_candidates[: max(0, int(args.next_actions_limit))]:
        next_actions.append({
            "type": "backport_candidate",
            "id": c["id"],
            "title": c.get("title"),
            "target_skill": c.get("primary_skill"),
            "score": c.get("score"),
            "suggested_next": c.get("how_to_backport"),
        })

    out = {
        "ok": True,
        "repo_root": str(repo),
        "user": user,
        "project_store": str(store),
        "global_store": (str(global_store) if bool(args.include_global) else None),
        "filters": {
            "skill": skill_filter,
            "scope": scope_filter,
            "since": (since_dt.isoformat().replace("+00:00", "Z") if since_dt else None),
            "stale_days": stale_days,
            "query": query_filter,
            "status": status_filter if status_filter else None,
        },
        "summary": {
            "aha_cards": len(aha_latest),
            "recommendations": len(rec_latest),
            "open_recommendations": len(open_recs),
            "open_recommendations_project": sum(1 for r in open_recs if r.get("scope") == "project"),
            "open_recommendations_portable": sum(1 for r in open_recs if r.get("scope") == "portable"),
            "stale_recommendations": len(stale_recs),
            "untouched_recommendations": len(untouched_recs),
            "backport_candidates": len(aha_candidates),
            "signals": len(signals),
            "backports": len(bp_lines),
            "global_aha_cards": (len(_first_and_latest_by_id(global_aha_lines)[1]) if global_aha_lines else 0),
        },
        "next_actions": next_actions[: max(0, int(args.next_actions_limit))],
        "recommendations": {
            "open": open_recs[: max(0, int(args.recs_limit))],
            "stale": stale_recs[: max(0, int(args.recs_limit))],
            "untouched": untouched_recs[: max(0, int(args.recs_limit))],
            "by_status": recs_by_status,
        },
        "aha": {
            "top_by_score": top_aha,
            "backport_candidates": aha_candidates,
        },
    }

    out_format = str(getattr(args, "format", "") or "summary").strip().lower()
    if out_format == "json":
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    if out_format != "summary":
        raise SystemExit("Invalid --format (expected: summary or json)")

    summary = out.get("summary") if isinstance(out.get("summary"), dict) else {}
    filters = out.get("filters") if isinstance(out.get("filters"), dict) else {}
    next_actions_out = out.get("next_actions") if isinstance(out.get("next_actions"), list) else []

    def _fmt_cmd(fmt: str) -> str:
        parts: List[str] = ["python", sys.argv[0], "review", "--format", fmt]
        if args.skill:
            parts.extend(["--skill", str(args.skill)])
        if args.scope:
            parts.extend(["--scope", str(args.scope)])
        if args.query:
            parts.extend(["--query", str(args.query)])
        if args.status:
            parts.extend(["--status", str(args.status)])
        if args.since:
            parts.extend(["--since", str(args.since)])
        elif args.days is not None:
            parts.extend(["--days", str(int(args.days))])
        if int(args.stale_days) != 7:
            parts.extend(["--stale-days", str(int(args.stale_days))])
        if bool(args.include_global):
            parts.append("--include-global")
        if int(args.min_aha_score) != 4:
            parts.extend(["--min-aha-score", str(int(args.min_aha_score))])
        if int(args.backport_limit) != 10:
            parts.extend(["--backport-limit", str(int(args.backport_limit))])
        if int(args.top_aha_limit) != 10:
            parts.extend(["--top-aha-limit", str(int(args.top_aha_limit))])
        if int(args.next_actions_limit) != 10:
            parts.extend(["--next-actions-limit", str(int(args.next_actions_limit))])
        if int(args.recs_limit) != 10:
            parts.extend(["--recs-limit", str(int(args.recs_limit))])
        return " ".join(shlex.quote(p) for p in parts)

    print("Self-learning review (summary)")
    print(f"Project store: {out.get('project_store')}")
    if any(v for v in filters.values()):
        filters_compact = {k: v for k, v in filters.items() if v is not None and v != ""}
        print(f"Filters: {json.dumps(filters_compact, ensure_ascii=False)}")
    print(
        "Counts: "
        f"aha={summary.get('aha_cards', 0)}; "
        f"recs={summary.get('recommendations', 0)} "
        f"(open={summary.get('open_recommendations', 0)} "
        f"[project={summary.get('open_recommendations_project', 0)}, portable={summary.get('open_recommendations_portable', 0)}], "
        f"stale={summary.get('stale_recommendations', 0)}, untouched={summary.get('untouched_recommendations', 0)}); "
        f"backport_candidates={summary.get('backport_candidates', 0)}"
    )

    max_next = min(5, max(0, int(args.next_actions_limit)))
    if next_actions_out and max_next > 0:
        print("Next actions:")
        for a in next_actions_out[:max_next]:
            if not isinstance(a, dict):
                continue
            if a.get("type") == "recommendation":
                rid = a.get("id")
                title = a.get("title") or ""
                st = a.get("status") or ""
                scope = a.get("scope") or "project"
                print(f"- {rid} [{st}, {scope}] {title}".rstrip())
            elif a.get("type") == "backport_candidate":
                cid = a.get("id")
                title = a.get("title") or ""
                score = a.get("score")
                target_skill = a.get("target_skill") or "unknown-skill"
                print(f"- {cid} (backport; score={score}; target={target_skill}) {title}".rstrip())

    print("View more:")
    print(f"- Open {out.get('project_store')}/INDEX.md")
    print(f"- Full JSON: {_fmt_cmd('json')}")
    return 0


def cmd_backport_inspect(args: argparse.Namespace) -> int:
    skill_path = Path(args.skill_path).expanduser().resolve()
    skill_md_path = skill_path / "SKILL.md"
    if not skill_md_path.exists():
        raise SystemExit(f"skill-path must point to a skill directory containing SKILL.md: {skill_path}")

    skill_md = skill_md_path.read_text(encoding="utf-8")
    start_ids = SKILL_BACKPORT_START_ID_RE.findall(skill_md)
    has_any_start = bool(SKILL_BACKPORT_START_RE.search(skill_md))
    has_any_end = bool(SKILL_BACKPORT_END_RE.search(skill_md))

    ref_path = skill_path / "references" / "self-learning-aha.md"
    ref_exists = ref_path.exists()
    ref_md = ref_path.read_text(encoding="utf-8") if ref_exists else ""
    ref_meta = _parse_aha_file_header_meta(ref_md) if ref_exists else {}
    ref_card_ids = _extract_aha_card_ids_from_ref_md(ref_md) if ref_exists else []

    requested_bp = str(args.backport_id).strip() if args.backport_id else None
    requested_aha = str(args.aha_id).strip() if args.aha_id else None

    instructions: List[str] = [
        "Preferred removal path: revert the commit/PR that applied the backport.",
        "No-git removal: delete the marker block in SKILL.md and remove the relevant Aha blocks from references/self-learning-aha.md.",
    ]
    if requested_bp:
        instructions.append(f"For backport id '{requested_bp}': remove the SKILL.md block whose start marker has id={requested_bp} (if present).")
    if requested_aha:
        instructions.append(f"For Aha id '{requested_aha}': delete the block between `<!-- self-learning:aha:start id={requested_aha} ... -->` and `<!-- self-learning:aha:end -->`.")

    out: Dict[str, Any] = {
        "ok": True,
        "target_skill_path": str(skill_path),
        "files": {
            "skill_md": str(skill_md_path),
            "aha_reference": str(ref_path),
        },
        "skill_md_markers": {
            "has_backport_start": has_any_start,
            "has_backport_end": has_any_end,
            "backport_ids": start_ids,
        },
        "aha_reference": {
            "exists": ref_exists,
            "header_meta": ref_meta,
            "card_count": len(ref_card_ids),
            "card_ids": ref_card_ids,
        },
        "requested": {
            "backport_id": requested_bp,
            "aha_id": requested_aha,
        },
        "remove_instructions": instructions,
        "markers": {
            "skill_start": "<!-- self-learning:backport:start id=... -->",
            "skill_end": "<!-- self-learning:backport:end -->",
            "aha_start": "<!-- self-learning:aha:start id=... -->",
            "aha_end": "<!-- self-learning:aha:end -->",
        },
    }

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def _infer_primary_skill_from_text(obj: Dict[str, Any]) -> Optional[str]:
    # Generic, non-opinionated inference:
    # If you want a record to be attributable to a specific skill without relying on event context,
    # add an explicit tag like: "skill:my-skill-name".
    tags = obj.get("tags") if isinstance(obj.get("tags"), list) else []
    for t in tags:
        if not isinstance(t, str):
            continue
        if not t.startswith("skill:"):
            continue
        inferred = t.split(":", 1)[1].strip()
        if inferred:
            return inferred
    return None


def _infer_primary_skill_from_events(events: List[Dict[str, Any]], ts: Optional[str]) -> Optional[str]:
    if not ts:
        return None
    dt = _parse_iso_ts(str(ts))
    if not dt:
        return None

    best_before: Optional[Tuple[_dt.datetime, str]] = None
    best_after: Optional[Tuple[_dt.datetime, str]] = None
    for e in events:
        if not isinstance(e, dict):
            continue
        edt = _parse_iso_ts(str(e.get("ts") or ""))
        if not edt:
            continue
        ps_raw = e.get("primary_skill")
        ps = _normalize_primary_skill(ps_raw)
        if not ps or ps == "unknown":
            continue
        if edt <= dt:
            if best_before is None or edt > best_before[0]:
                best_before = (edt, ps)
        else:
            if best_after is None or edt < best_after[0]:
                best_after = (edt, ps)
    if best_before:
        return best_before[1]
    if best_after:
        return best_after[1]
    return None


def cmd_repair(args: argparse.Namespace) -> int:
    """
    Best-effort store repair:
    - Fill missing/empty primary_skill on Aha Cards and Recommendations
    - Normalize common recommendation status aliases (e.g., implemented -> done)
    """
    user = safe_user_slug()
    repo = find_repo_root()
    store = project_store_dir(repo, user)
    ensure_store_dirs(store)

    aha_path = store / "aha_cards.jsonl"
    rec_path = store / "recommendations.jsonl"
    evt_path = store / "events.jsonl"

    aha_lines = read_jsonl(aha_path)
    rec_lines = read_jsonl(rec_path)
    events = read_jsonl(evt_path)

    _, aha_latest = _first_and_latest_by_id(aha_lines)
    _, rec_latest = _first_and_latest_by_id(rec_lines)

    planned: Dict[str, List[Dict[str, Any]]] = {"aha_updates": [], "rec_updates": []}

    for cid, card in aha_latest.items():
        if not isinstance(card, dict):
            continue
        ps_raw = card.get("primary_skill")
        if isinstance(ps_raw, str) and ps_raw.strip():
            continue
        inferred = _infer_primary_skill_from_events(events, card.get("ts")) or _infer_primary_skill_from_text(card) or "unknown"
        upd = dict(card)
        upd["ts"] = iso_now()
        upd["primary_skill"] = _normalize_primary_skill(inferred)
        planned["aha_updates"].append({"id": cid, "primary_skill": upd["primary_skill"]})
        if bool(args.apply):
            append_jsonl(aha_path, redact(upd))

    for rid, rec in rec_latest.items():
        if not isinstance(rec, dict):
            continue
        updated: Dict[str, Any] = {}

        ps_raw = rec.get("primary_skill")
        if not (isinstance(ps_raw, str) and ps_raw.strip()):
            inferred = _infer_primary_skill_from_events(events, rec.get("ts")) or _infer_primary_skill_from_text(rec) or "unknown"
            updated["primary_skill"] = _normalize_primary_skill(inferred)

        # Normalize known status aliases without clobbering unknown custom statuses.
        orig_status = str(rec.get("status") or "").strip()
        canonical = _rec_status(rec)
        if orig_status and orig_status not in RECOMMENDATION_STATUSES and canonical != "proposed":
            updated["status"] = canonical

        if not updated:
            continue

        upd = dict(rec)
        upd["ts"] = iso_now()
        # Preserve last_touched_ts so repairs don't make items look recently "touched".
        if "last_touched_ts" in upd:
            upd["last_touched_ts"] = upd.get("last_touched_ts")
        for k, v in updated.items():
            upd[k] = v

        planned_item = {"id": rid, **updated}
        planned["rec_updates"].append(planned_item)
        if bool(args.apply):
            append_jsonl(rec_path, redact(upd))

    if bool(args.apply):
        try:
            update_index_md(store)
        except Exception:
            pass

    print(json.dumps({
        "ok": True,
        "repo_root": str(repo),
        "user": user,
        "project_store": str(store),
        "applied": bool(args.apply),
        "planned": planned,
        "counts": {
            "aha_updates": len(planned["aha_updates"]),
            "rec_updates": len(planned["rec_updates"]),
        },
        "note": ("Run again with --apply to write changes." if not bool(args.apply) else "Repairs appended; INDEX.md refreshed."),
    }, indent=2, ensure_ascii=False))
    return 0


def _collect_cards_by_ids(store: Path, ids: List[str]) -> List[Dict[str, Any]]:
    cards = read_jsonl(store / "aha_cards.jsonl")
    want = set(ids)
    out = [c for c in cards if str(c.get("id")) in want]
    return out


def cmd_promote(args: argparse.Namespace) -> int:
    user = safe_user_slug()
    repo = find_repo_root()
    src = project_store_dir(repo, user)
    dst = global_store_dir(user)

    ensure_store_dirs(src)
    ensure_store_dirs(dst)

    ids = [x.strip() for x in (args.ids or "").split(",") if x.strip()]
    if not ids:
        raise SystemExit("Provide --ids <id1,id2,...>")

    cards = _collect_cards_by_ids(src, ids)
    if not cards:
        raise SystemExit("No matching cards found in project store.")

    existing_ids = {str(c.get("id")) for c in read_jsonl(dst / "aha_cards.jsonl")}
    promoted = 0
    promoted_ids: List[str] = []
    for c in cards:
        cid = str(c.get("id"))
        if cid in existing_ids:
            continue
        # Mark as portable if not already.
        c = dict(c)
        c.setdefault("scope", "portable")
        append_jsonl(dst / "aha_cards.jsonl", c)
        promoted += 1
        promoted_ids.append(cid)

    try:
        update_index_md(dst)
    except Exception:
        pass
    try:
        for cid in promoted_ids:
            append_signal(src, kind="aha_promoted", aha_id=cid, source="agent")
    except Exception:
        pass
    try:
        update_index_md(src)
    except Exception:
        pass

    print(json.dumps({
        "ok": True,
        "user": user,
        "from_project_store": str(src),
        "to_global_store": str(dst),
        "requested": ids,
        "promoted_count": promoted,
        "promoted_ids": promoted_ids,
    }, indent=2))
    return 0


def _diff_text(old: str, new: str, path: str) -> str:
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm=""
    )
    return "\n".join(diff) + "\n"


def _dedupe_preserve_order(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _make_backport_id(ts_compact: str, target_skill_name: str, card_ids: List[str]) -> str:
    payload = f"{ts_compact}|{target_skill_name}|{','.join(card_ids)}"
    suffix = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:6]
    return f"slbp_{ts_compact}_{suffix}"


def _extract_aha_card_ids_from_ref_md(md: str) -> List[str]:
    md = md or ""
    ids = AHA_CARD_START_ID_RE.findall(md)
    if ids:
        return _dedupe_preserve_order(ids)
    ids = LEGACY_AHA_ID_RE.findall(md)
    return _dedupe_preserve_order(ids)


def _parse_aha_file_header_meta(md: str) -> Dict[str, str]:
    md = md or ""
    m = AHA_FILE_HEADER_META_RE.search(md)
    if not m:
        return {}
    body = m.group(1) or ""
    meta: Dict[str, str] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            meta[k] = v
    return meta


def _aha_file_header_block(*, backport_id: str, generated_at: str, card_ids: List[str]) -> str:
    return (
        "<!-- self-learning:aha-file\n"
        f"backport_id={backport_id}\n"
        f"generated_at={generated_at}\n"
        f"card_ids={','.join(card_ids)}\n"
        "-->\n\n"
    )


def _upsert_aha_file_header(md: str, header_block: str) -> str:
    md = md or ""
    header_block = header_block.strip() + "\n\n"
    if AHA_FILE_HEADER_BLOCK_RE.search(md):
        return AHA_FILE_HEADER_BLOCK_RE.sub(header_block, md, count=1).lstrip("\n")
    return header_block + md.lstrip("\n")


def _aha_card_block(card: Dict[str, Any], *, backport_id: str) -> str:
    title = card.get("title", "(untitled)")
    cid = str(card.get("id") or "")
    when = card.get("when_to_use", "")
    problem = card.get("problem", "")
    steps = card.get("solution_steps") or []
    evidence = card.get("evidence") or []
    tags = card.get("tags") or []

    parts: List[str] = [f"<!-- self-learning:aha:start id={cid} backport_id={backport_id} -->\n"]
    parts.append(f"## {title}\n")
    parts.append(f"- **ID:** `{cid}`\n")
    if when:
        parts.append(f"- **When to use:** {when}\n")
    if tags:
        parts.append(f"- **Tags:** {', '.join(tags)}\n")
    if problem:
        parts.append(f"\n**Problem**\n\n{problem}\n")
    if steps:
        parts.append("\n**Solution**\n")
        for s in steps:
            parts.append(f"- {s}\n")
    if evidence:
        parts.append("\n**Evidence**\n")
        for e in evidence:
            parts.append(f"- {e}\n")
    parts.append("\n<!-- self-learning:aha:end -->\n\n")
    return "".join(parts)


def _build_aha_ref_text(
    existing_md: str,
    *,
    added_cards: List[Dict[str, Any]],
    backport_id: str,
    generated_at: str,
    card_ids: List[str],
) -> str:
    header = _aha_file_header_block(backport_id=backport_id, generated_at=generated_at, card_ids=card_ids)
    if not (existing_md or "").strip():
        blocks = "".join(_aha_card_block(c, backport_id=backport_id) for c in added_cards)
        out = header + "# Self-learning Aha Cards\n\n" + blocks
        return out.rstrip() + "\n"

    base = _upsert_aha_file_header(existing_md, header)
    if not added_cards:
        return base.rstrip() + "\n"

    blocks = "".join(_aha_card_block(c, backport_id=backport_id) for c in added_cards).rstrip()
    return base.rstrip() + "\n\n" + blocks + "\n"


def _skill_backport_block(backport_id: str) -> str:
    return (
        "\n\n"
        f"<!-- self-learning:backport:start id={backport_id} -->\n"
        "## Learnings (self-learning)\n\n"
        "If `references/self-learning-aha.md` exists, skim it before starting work. "
        "It contains compact, proven “aha” moments captured from real runs.\n"
        "<!-- self-learning:backport:end -->\n"
    )


def _upsert_skill_backport_block(skill_md: str, *, backport_id: str) -> Tuple[str, str]:
    start_marker = f"<!-- self-learning:backport:start id={backport_id} -->"
    skill_md = skill_md or ""
    if SKILL_BACKPORT_START_RE.search(skill_md):
        updated = SKILL_BACKPORT_START_RE.sub(start_marker, skill_md, count=1)
        return updated, ("updated_marker_id" if updated != skill_md else "unchanged")
    updated = skill_md.rstrip() + _skill_backport_block(backport_id)
    return (updated if updated.endswith("\n") else updated + "\n"), "appended_block"


def cmd_export_backport(args: argparse.Namespace) -> int:
    user = safe_user_slug()
    repo = find_repo_root()
    store = project_store_dir(repo, user)
    ensure_store_dirs(store)

    skill_path = Path(args.skill_path).expanduser().resolve()
    if not (skill_path / "SKILL.md").exists():
        raise SystemExit(f"skill-path must point to a skill directory containing SKILL.md: {skill_path}")

    ids = [x.strip() for x in (args.ids or "").split(",") if x.strip()]
    if not ids:
        raise SystemExit("Provide --ids <card-id-1,card-id-2,...>")

    cards = _collect_cards_by_ids(store, ids)
    if not cards:
        raise SystemExit("No matching cards found in project store.")

    cards_by_id = {str(c.get("id")): c for c in cards}
    missing_req = [cid for cid in ids if cid not in cards_by_id]
    if missing_req:
        raise SystemExit(f"Some requested ids were not found in project store: {', '.join(missing_req)}")

    # Build bundle folder
    now = _dt.datetime.now(tz=_dt.timezone.utc).replace(microsecond=0)
    generated_at = now.isoformat().replace("+00:00", "Z")
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    backport_id = _make_backport_id(ts, skill_path.name, ids)
    bundle = store / "exports" / "backports" / f"{skill_path.name}_{backport_id}"
    (bundle / "references").mkdir(parents=True, exist_ok=True)

    # Compute updated reference file content (preserve existing file, append new blocks, and upsert header).
    ref_path = skill_path / "references" / "self-learning-aha.md"
    old_ref = ref_path.read_text(encoding="utf-8") if ref_path.exists() else ""
    existing_ref_ids = _extract_aha_card_ids_from_ref_md(old_ref) if old_ref else []
    added_ids = [cid for cid in ids if cid not in set(existing_ref_ids)]
    added_cards = [cards_by_id[cid] for cid in added_ids]
    result_ids = _dedupe_preserve_order([*existing_ref_ids, *added_ids])

    new_ref = _build_aha_ref_text(
        old_ref,
        added_cards=added_cards if old_ref else [cards_by_id[cid] for cid in ids],
        backport_id=backport_id,
        generated_at=generated_at,
        card_ids=result_ids if old_ref else ids,
    )
    (bundle / "references" / "self-learning-aha.md").write_text(new_ref, encoding="utf-8")

    skill_append = _skill_backport_block(backport_id).strip() + "\n"
    (bundle / "SKILL_APPEND.md").write_text(skill_append, encoding="utf-8")

    manifest: Dict[str, Any] = {
        "backport_id": backport_id,
        "generated_at": generated_at,
        "target_skill_name": skill_path.name,
        "target_skill_path": str(skill_path),
        "requested_card_ids": ids,
        "existing_card_ids": existing_ref_ids,
        "added_card_ids": added_ids,
        "result_card_ids": (result_ids if old_ref else ids),
        "changes": [
            {
                "path": "SKILL.md",
                "kind": "append_or_update_marker_id",
                "markers": {
                    "start": f"<!-- self-learning:backport:start id={backport_id} -->",
                    "end": "<!-- self-learning:backport:end -->",
                },
            },
            {"path": "references/self-learning-aha.md", "kind": "create_or_update"},
        ],
    }
    (bundle / "BACKPORT_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    readme = f"""# Backport bundle for: {skill_path.name}

This bundle was generated by `self-learning-skills`.

## What’s included

- `BACKPORT_MANIFEST.json` — provenance (backport id, card ids, and intended changes)
- `references/self-learning-aha.md` — selected Aha Cards as a reference file (marker-wrapped per card)
- `SKILL_APPEND.md` — marker-wrapped snippet for the target skill’s `SKILL.md`

## How to apply (manual)

1) Copy the reference file into the target skill:

   - Copy: `references/self-learning-aha.md`
   - To:   `{skill_path}/references/self-learning-aha.md`

2) Apply `SKILL_APPEND.md` into `{skill_path}/SKILL.md`:

   - If `{skill_path}/SKILL.md` does not already include a `self-learning:backport` marker block, append the snippet.
   - If it already includes a `self-learning:backport` block, update the start marker’s `id=...` to match `BACKPORT_MANIFEST.json`.

3) Commit the changes and open a PR if you want to share it.

## How to remove (manual)

- Best: revert the commit/PR that added this backport.
- No-git: delete the block between `<!-- self-learning:backport:start ... -->` and `<!-- self-learning:backport:end -->`, and delete (or edit) `references/self-learning-aha.md` blocks between `<!-- self-learning:aha:start ... -->` / `<!-- self-learning:aha:end -->`.

## Optional: auto-apply

Re-run with `--apply` to apply changes directly (overwrites/creates only the files listed above).
"""
    (bundle / "README.md").write_text(readme, encoding="utf-8")

    old_skill = (skill_path / "SKILL.md").read_text(encoding="utf-8")
    new_skill, skill_change = _upsert_skill_backport_block(old_skill, backport_id=backport_id)

    patch_text = ""
    if args.make_diff:
        # Create a unified diff (best-effort). We only diff SKILL.md and the new reference file.
        # SKILL.md diff: append block or update marker id.
        if new_skill != old_skill:
            patch_text += _diff_text(old_skill, new_skill, str((skill_path / "SKILL.md").relative_to(skill_path.parent)))

        # references file diff: add/replace.
        patch_text += _diff_text(old_ref, new_ref, str(ref_path.relative_to(skill_path.parent)))

        (bundle / "backport.patch").write_text(patch_text, encoding="utf-8")

    if args.apply:
        (skill_path / "references").mkdir(parents=True, exist_ok=True)
        ref_path.write_text(new_ref, encoding="utf-8")

        s_path = skill_path / "SKILL.md"
        if new_skill != old_skill:
            s_path.write_text(new_skill, encoding="utf-8")

    backport_evt = {
        "ts": generated_at,
        "backport_id": backport_id,
        "target_skill": skill_path.name,
        "target_skill_path": str(skill_path),
        "requested_card_ids": ids,
        "added_card_ids": added_ids,
        "result_card_ids": (result_ids if old_ref else ids),
        "applied": bool(args.apply),
        "diff_written": bool(args.make_diff),
        "bundle_dir": str(bundle),
        "manifest_path": str(bundle / "BACKPORT_MANIFEST.json"),
        "skill_change": skill_change,
    }
    append_jsonl(store / "backports.jsonl", backport_evt)
    if args.apply:
        try:
            for cid in added_ids:
                append_signal(
                    store,
                    kind="aha_backported",
                    aha_id=cid,
                    source="agent",
                    context=f"backport_id={backport_id}; target_skill={skill_path.name}",
                )
        except Exception:
            pass
    try:
        update_index_md(store)
    except Exception:
        pass

    print(json.dumps({
        "ok": True,
        "repo_root": str(repo),
        "user": user,
        "project_store": str(store),
        "target_skill": str(skill_path),
        "backport_id": backport_id,
        "bundle_dir": str(bundle),
        "applied": bool(args.apply),
        "diff_written": bool(args.make_diff),
        "card_ids": ids,
        "added_card_ids": added_ids,
        "result_card_ids": (result_ids if old_ref else ids),
        "logged_to": str(store / "backports.jsonl"),
    }, indent=2))
    return 0


# -----------------------------
# Entrypoint
# -----------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="self_learning.py",
        description="Helper CLI for the `self-learning-skills` Agent Skill (optional).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_init = sub.add_parser("init", help="Create the project-local store and (optionally) update .gitignore.")
    sp_init.add_argument("--no-gitignore", dest="gitignore", action="store_false", help="Do not modify .gitignore.")
    sp_init.set_defaults(func=cmd_init, gitignore=True)

    sp_record = sub.add_parser("record", help="Append event/cards/recommendations to the project-local store.")
    sp_record.add_argument("--json", help="Path to input JSON file. If omitted, reads JSON from stdin.")
    sp_record.set_defaults(func=cmd_record)

    sp_list = sub.add_parser("list", help="List aha cards from the project-local store (optionally filtered).")
    sp_list.add_argument("--skill", help="Filter by primary_skill exact match.")
    sp_list.add_argument("--tag", help="Filter by tag exact match.")
    sp_list.add_argument("--query", help="Substring match over the JSON blob.")
    sp_list.add_argument("--limit", type=int, default=20, help="Return only the most recent N matches.")
    sp_list.set_defaults(func=cmd_list)

    sp_rec_status = sub.add_parser("rec-status", help="Update a recommendation status (append-only, auditable).")
    sp_rec_status.add_argument("--id", required=True, help="Recommendation id (rec_...).")
    sp_rec_status.add_argument(
        "--status",
        required=True,
        choices=sorted(RECOMMENDATION_STATUSES),
        help="New status.",
    )
    sp_rec_status.add_argument(
        "--scope",
        choices=sorted(VALID_SCOPES),
        help="Optional scope update (project vs portable).",
    )
    sp_rec_status.add_argument("--note", help="Optional note explaining the change.")
    sp_rec_status.set_defaults(func=cmd_rec_status)

    sp_signal = sub.add_parser("signal", help="Append a usage/scoring signal (append-only).")
    sp_signal.add_argument("--kind", required=True, choices=sorted(SIGNAL_KINDS), help="Signal kind.")
    sp_signal.add_argument("--aha-id", dest="aha_id", help="Aha Card id (aha_...).")
    sp_signal.add_argument("--rec-id", dest="rec_id", help="Recommendation id (rec_...).")
    sp_signal.add_argument("--source", default="manual", help="Source of the signal (default: manual).")
    sp_signal.add_argument("--context", help="Optional short context (avoid secrets).")
    sp_signal.set_defaults(func=cmd_signal)

    sp_use = sub.add_parser("use", help="Mark an Aha Card / Recommendation as used (writes signals).")
    sp_use.add_argument("--aha", dest="aha_ids", help="Comma-separated Aha Card ids (aha_...[,aha_...]).")
    sp_use.add_argument("--rec", dest="rec_ids", help="Comma-separated Recommendation ids (rec_...[,rec_...]).")
    sp_use.add_argument("--source", default="agent", help="Source of the usage signal (default: agent).")
    sp_use.add_argument("--context", help="Optional short context (avoid secrets).")
    sp_use.set_defaults(func=cmd_use)

    sp_aha_status = sub.add_parser("aha-status", help="Update an Aha Card status (append-only, auditable).")
    sp_aha_status.add_argument("--id", required=True, help="Aha Card id (aha_...).")
    sp_aha_status.add_argument(
        "--status",
        required=True,
        choices=sorted(AHA_STATUSES),
        help="New status.",
    )
    sp_aha_status.add_argument("--note", help="Optional note explaining the change.")
    sp_aha_status.set_defaults(func=cmd_aha_status)

    sp_review = sub.add_parser("review", help="Summarize open work, scores, and backport candidates.")
    sp_review.add_argument(
        "--format",
        default="summary",
        choices=["summary", "json"],
        help="Output format (default: summary). Use 'json' for full machine-readable output.",
    )
    sp_review.add_argument("--skill", help="Filter by primary_skill exact match.")
    sp_review.add_argument(
        "--scope",
        choices=sorted(VALID_SCOPES),
        help="Filter by scope (project vs portable).",
    )
    sp_review.add_argument("--query", help="Substring match over JSON blobs.")
    sp_review.add_argument("--status", help="Comma-separated recommendation statuses to include (e.g. proposed,accepted).")
    sp_review.add_argument("--since", help="Only include items touched since this ISO timestamp (e.g. 2025-12-26T00:00:00Z).")
    sp_review.add_argument("--days", type=int, help="Alternative to --since: include items touched in last N days.")
    sp_review.add_argument("--stale-days", dest="stale_days", type=int, default=7, help="Stale threshold in days (default: 7).")
    sp_review.add_argument("--include-global", action="store_true", help="Include global store counts (and global aha card count).")
    sp_review.add_argument("--min-aha-score", type=int, default=4, help="Minimum score for backport candidate (default: 4).")
    sp_review.add_argument("--backport-limit", type=int, default=10, help="Max backport candidates to include (default: 10).")
    sp_review.add_argument("--top-aha-limit", type=int, default=10, help="Max top aha cards to include (default: 10).")
    sp_review.add_argument("--next-actions-limit", type=int, default=10, help="Max next actions to include (default: 10).")
    sp_review.add_argument("--recs-limit", type=int, default=10, help="Max recs in each list (default: 10).")
    sp_review.set_defaults(func=cmd_review)

    sp_repair = sub.add_parser("repair", help="Repair common store issues (missing primary_skill, status aliases).")
    sp_repair.add_argument(
        "--apply",
        action="store_true",
        help="Apply repairs (append-only) to the project store. If omitted, prints what would change.",
    )
    sp_repair.set_defaults(func=cmd_repair)

    sp_bp_inspect = sub.add_parser("backport-inspect", help="Inspect an existing skill for self-learning backport markers.")
    sp_bp_inspect.add_argument("--skill-path", required=True, help="Path to the target skill directory (must contain SKILL.md).")
    sp_bp_inspect.add_argument("--backport-id", dest="backport_id", help="Optional backport id to focus on.")
    sp_bp_inspect.add_argument("--aha-id", dest="aha_id", help="Optional Aha id to focus on.")
    sp_bp_inspect.set_defaults(func=cmd_backport_inspect)

    sp_promote = sub.add_parser("promote", help="Promote selected Aha Cards from project store to global store.")
    sp_promote.add_argument("--ids", required=True, help="Comma-separated card ids to promote.")
    sp_promote.set_defaults(func=cmd_promote)

    sp_backport = sub.add_parser("export-backport", help="Create a backport bundle (and optional diff) for a target skill.")
    sp_backport.add_argument("--skill-path", required=True, help="Path to the target skill directory (must contain SKILL.md).")
    sp_backport.add_argument("--ids", required=True, help="Comma-separated Aha Card ids to include.")
    sp_backport.add_argument("--apply", action="store_true", help="Apply changes directly to the target skill (creates/updates only the included files/snippets).")
    sp_backport.add_argument("--make-diff", action="store_true", help="Write a unified diff patch into the bundle as backport.patch (best-effort).")
    sp_backport.set_defaults(func=cmd_export_backport)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
