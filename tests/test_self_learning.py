"""CLI regressions; every memory store and target skill lives in a temporary directory."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import re
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "self_learning.py"


class SelfLearningCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.base = self.repo / "custom-memory"
        self.store = self.base / "self-learning" / "v1" / "users" / "test-user"
        self.global_store = self.root / "global-memory"
        self.env = dict(os.environ)
        self.env.update(
            SELF_LEARNING_REPO_ROOT=str(self.repo),
            SELF_LEARNING_PROJECT_DIR=str(self.base),
            SELF_LEARNING_GLOBAL_DIR=str(self.global_store),
            USER="test-user",
            USERNAME="test-user",
            PYTHONDONTWRITEBYTECODE="1",
        )

    def run_cli(self, *args, payload=None, success=True):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            input=json.dumps(payload) if payload is not None else None,
            text=True, capture_output=True, cwd=self.repo, env=self.env,
            check=False,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertNotIn("Traceback", result.stderr)
        return result

    def record(self, **payload):
        return self.run_cli("record", payload=payload)

    def read_records(self, name, store=None):
        path = (store or self.store) / name
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def write_records(self, name, records):
        self.store.mkdir(parents=True, exist_ok=True)
        (self.store / name).write_text("".join(json.dumps(item) + "\n" for item in records))

    def card(self, **overrides):
        card = {
            "id": "aha_example", "title": "A reusable lesson", "primary_skill": "example",
            "when_to_use": "Before testing", "solution_steps": ["First step"],
            "scope": "portable", "shareable": True,
        }
        card.update(overrides)
        return card

    def make_skill(self):
        skill = self.root / "example-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: example\n---\n\n# Example\n")
        return skill

    def test_read_only_commands_do_not_create_stores(self):
        for args in (("list",), ("review", "--format", "json", "--include-global"), ("repair",)):
            with self.subTest(args=args):
                self.run_cli(*args)
                self.assertFalse(self.base.exists())
                self.assertFalse(self.global_store.exists())

    def test_invalid_record_is_rejected_before_any_write(self):
        invalid_payloads = [
            {"event": {"task_summary": "Valid event"}, "aha_cards": ["not an object"]},
            {"aha_cards": [{"title": "Valid"}], "recommendations": [None]},
            {"aha_cards": [{"title": "Valid", "shareable": "false"}]},
            {"aha_cards": [{"title": "Valid", "tags": "not an array"}]},
            {"aha_cards": [{"title": "Valid", "solution_steps": [7]}]},
            {"aha_cards": [{"id": None}]},
            {"event": {"ts": "not a timestamp"}},
            {"used_aha_ids": [17]},
            {"used": []},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                self.run_cli("record", payload=payload, success=False)
                self.assertFalse(self.base.exists())

    def test_malformed_json_reports_error_without_traceback_or_store(self):
        bad = self.root / "bad.json"
        bad.write_text('{"event": ')
        self.run_cli("record", "--json", str(bad), success=False)
        self.assertFalse(self.base.exists())

    def test_nonfinite_values_are_rejected_before_any_write(self):
        bad = self.root / "bad.json"
        for value in ("NaN", "Infinity", "-Infinity", "1e999"):
            with self.subTest(value=value):
                bad.write_text('{"event": {"task_summary": "Valid event"}, "extra": ' + value + '}')
                self.run_cli("record", "--json", str(bad), success=False)
                self.assertFalse(self.base.exists())

    def test_nonobject_and_corrupt_jsonl_rows_are_skipped_with_warning(self):
        self.write_records("aha_cards.jsonl", [None, [1], self.card()])
        with (self.store / "aha_cards.jsonl").open("a") as stream:
            stream.write('{"broken":\n')
        result = self.run_cli("list", "--skill", "example")
        self.assertEqual(json.loads(result.stdout)["count"], 1)
        self.assertIn("non-object record", result.stderr)
        self.assertIn("invalid JSON", result.stderr)
        self.assertNotIn('"broken"', result.stderr)

    def test_list_uses_latest_revision_and_latest_update_order(self):
        self.write_records("aha_cards.jsonl", [
            self.card(title="Old title"),
            self.card(id="aha_second", title="Second card"),
            self.card(title="New title", status="deprecated"),
        ])
        result = json.loads(self.run_cli("list", "--limit", "1").stdout)
        self.assertEqual(result["items"][0]["title"], "New title")
        self.assertEqual(result["items"][0]["status"], "deprecated")
        result = json.loads(self.run_cli("list", "--query", "Old title").stdout)
        self.assertEqual(result["count"], 0)

    def test_same_batch_reinforcement_preserves_every_step_and_one_identity(self):
        self.record(aha_cards=[
            self.card(solution_steps=["First step"]),
            self.card(id="aha_duplicate", solution_steps=["Second step"]),
            self.card(id="aha_another", solution_steps=["Third step"]),
        ])
        result = json.loads(self.run_cli("list").stdout)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["solution_steps"], ["First step", "Second step", "Third step"])
        self.assertEqual(len(self.read_records("signals.jsonl")), 2)

    def test_reinforcement_preserves_updates_to_existing_card_in_same_batch(self):
        self.record(aha_cards=[self.card()])
        self.record(aha_cards=[
            self.card(solution_steps=["Second step"]),
            self.card(solution_steps=["Third step"]),
        ])
        latest = self.read_records("aha_cards.jsonl")[-1]
        self.assertEqual(latest["solution_steps"], ["First step", "Second step", "Third step"])

    def test_matching_titles_from_different_skills_remain_separate(self):
        self.record(aha_cards=[self.card(), self.card(id="aha_other", primary_skill="other")])
        self.assertEqual(json.loads(self.run_cli("list").stdout)["count"], 2)

    def test_private_reinforcement_downgrades_sharing(self):
        self.record(aha_cards=[self.card()])
        self.record(aha_cards=[self.card(scope="project", shareable=False, solution_steps=["Local detail"])])
        latest = self.read_records("aha_cards.jsonl")[-1]
        self.assertEqual(latest["scope"], "project")
        self.assertIs(latest["shareable"], False)
        self.run_cli("promote", "--ids", "aha_example", success=False)
        self.assertFalse(self.global_store.exists())

    def test_append_preserves_a_record_without_final_newline(self):
        self.store.mkdir(parents=True)
        path = self.store / "aha_cards.jsonl"
        original = json.dumps(self.card(title="First lesson"))
        path.write_text(original)
        self.record(aha_cards=[self.card(id="aha_second", title="Second lesson")])
        self.assertTrue(path.read_text().startswith(original + "\n"))
        self.assertEqual(len(self.read_records("aha_cards.jsonl")), 2)

    def test_signal_and_status_outputs_match_redacted_records(self):
        secret = "a" * 48
        self.record(aha_cards=[self.card()], recommendations=[{"id": "rec_example", "title": "Improve"}])
        commands = [
            ("signal", "--kind", "aha_used", "--aha-id", "aha_example", "--context", secret),
            ("use", "--aha", "aha_example", "--context", secret),
            ("aha-status", "--id", "aha_example", "--status", "accepted", "--note", secret),
            ("rec-status", "--id", "rec_example", "--status", "done", "--note", secret),
        ]
        for args in commands:
            with self.subTest(command=args[0]):
                result = self.run_cli(*args)
                self.assertNotIn(secret, result.stdout)
                self.assertIn("***REDACTED***", result.stdout)
        result = self.record(used_aha_ids=["aha_example"], usage_context=secret)
        self.assertNotIn(secret, result.stdout)
        for path in self.store.glob("*.jsonl"):
            self.assertNotIn(secret, path.read_text())

    def test_signal_kind_must_match_target_type(self):
        self.run_cli("signal", "--kind", "aha_used", "--rec-id", "rec_example", success=False)
        self.assertFalse((self.store / "signals.jsonl").exists())

    def test_status_update_preserves_append_only_history(self):
        self.record(aha_cards=[self.card()])
        path = self.store / "aha_cards.jsonl"
        original = path.read_bytes()
        self.run_cli("aha-status", "--id", "aha_example", "--status", "accepted")
        self.assertTrue(path.read_bytes().startswith(original))
        self.assertEqual(len(self.read_records("aha_cards.jsonl")), 2)

    def test_promotion_uses_one_latest_revision_and_is_idempotent(self):
        self.write_records("aha_cards.jsonl", [self.card(title="Old"), self.card(title="Latest")])
        result = json.loads(self.run_cli("promote", "--ids", "aha_example,aha_example").stdout)
        self.assertEqual(result["promoted_count"], 1)
        self.assertEqual(self.read_records("aha_cards.jsonl", self.global_store)[0]["title"], "Latest")
        result = json.loads(self.run_cli("promote", "--ids", "aha_example").stdout)
        self.assertEqual(result["promoted_count"], 0)
        self.assertEqual(len(self.read_records("aha_cards.jsonl", self.global_store)), 1)

    def test_promotion_rejects_missing_id_without_partial_copy(self):
        self.record(aha_cards=[self.card()])
        self.run_cli("promote", "--ids", "aha_example,aha_missing", success=False)
        self.assertFalse(self.global_store.exists())

    def test_promotion_and_export_require_explicit_portable_shareable_cards(self):
        skill = self.make_skill()
        for fields in ({"scope": "project"}, {"shareable": False}, {"shareable": "false"}):
            with self.subTest(fields=fields):
                self.write_records("aha_cards.jsonl", [self.card(**fields)])
                self.run_cli("promote", "--ids", "aha_example", success=False)
                self.run_cli("export-backport", "--skill-path", str(skill), "--ids", "aha_example", success=False)
                self.assertFalse(self.global_store.exists())
                self.assertFalse((self.store / "exports").exists())

    def test_user_dot_segments_cannot_escape_user_directory(self):
        for user in (".", ".."):
            with self.subTest(user=user):
                self.env["USER"] = user
                result = json.loads(self.run_cli("list").stdout)
                self.assertEqual(result["user"], "default")

    def test_init_ignores_custom_store_not_comment_mentions(self):
        (self.repo / ".gitignore").write_text("# Add custom-memory/ here\n")
        self.run_cli("init")
        self.assertIn("/custom-memory/", (self.repo / ".gitignore").read_text().splitlines())
        before = (self.repo / ".gitignore").read_text()
        self.run_cli("init")
        self.assertEqual((self.repo / ".gitignore").read_text(), before)
        if shutil.which("git"):
            subprocess.run(["git", "init", "-q", str(self.repo)], check=True, capture_output=True)
            ignored = subprocess.run(
                ["git", "check-ignore", str(self.store / "aha_cards.jsonl")],
                cwd=self.repo, capture_output=True, text=True, check=False,
            )
            self.assertEqual(ignored.returncode, 0, ignored.stderr)

    @unittest.skipUnless(shutil.which("git"), "git is required to validate ignore patterns")
    def test_init_escapes_custom_store_glob_characters(self):
        base = self.repo / "memory[local]"
        self.env["SELF_LEARNING_PROJECT_DIR"] = str(base)
        self.run_cli("init")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True, capture_output=True)
        ignored = subprocess.run(
            ["git", "check-ignore", str(base / "self-learning" / "sample.jsonl")],
            cwd=self.repo, capture_output=True, text=True, check=False,
        )
        self.assertEqual(ignored.returncode, 0, ignored.stderr)

    def test_export_rejects_symlink_escape_before_writing_bundle(self):
        self.write_records("aha_cards.jsonl", [self.card()])
        skill = self.make_skill()
        references = skill / "references"
        references.mkdir()
        outside = self.root / "outside.md"
        outside.write_text("Unrelated content\n")
        (references / "self-learning-aha.md").symlink_to(outside)
        self.run_cli("export-backport", "--skill-path", str(skill), "--ids", "aha_example", "--apply", success=False)
        self.assertEqual(outside.read_text(), "Unrelated content\n")
        self.assertFalse((self.store / "exports").exists())

    @unittest.skipUnless(shutil.which("git"), "git is required to validate generated patches")
    def test_export_patch_applies_with_and_without_trailing_newline(self):
        self.record(aha_cards=[self.card()])
        skill = self.make_skill()
        for trailing_newline in (True, False):
            with self.subTest(trailing_newline=trailing_newline):
                original = "# Example" + ("\n" if trailing_newline else "")
                (skill / "SKILL.md").write_text(original)
                result = json.loads(self.run_cli(
                    "export-backport", "--skill-path", str(skill), "--ids", "aha_example,aha_example", "--make-diff",
                ).stdout)
                patch = Path(result["bundle_dir"]) / "backport.patch"
                check = subprocess.run(
                    ["git", "apply", "--check", str(patch)], cwd=self.root,
                    text=True, capture_output=True, check=False,
                )
                self.assertEqual(check.returncode, 0, check.stderr + patch.read_text())
                self.assertEqual((skill / "SKILL.md").read_text(), original)
                self.assertFalse((skill / "references").exists())
                self.assertEqual(result["card_ids"], ["aha_example"])

    def test_export_apply_is_inspectable_and_does_not_duplicate_cards(self):
        self.record(aha_cards=[self.card()])
        skill = self.make_skill()
        args = ("export-backport", "--skill-path", str(skill), "--ids", "aha_example", "--apply")
        self.run_cli(*args)
        self.run_cli(*args)
        content = (skill / "references" / "self-learning-aha.md").read_text()
        self.assertEqual(content.count("<!-- self-learning:aha:start id=aha_example "), 1)
        inspection = json.loads(self.run_cli("backport-inspect", "--skill-path", str(skill)).stdout)
        self.assertIn("aha_example", json.dumps(inspection))

    def test_repeated_exports_keep_separate_reviewable_bundles(self):
        spec = importlib.util.spec_from_file_location("self_learning_test_cli", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        first_id = module._make_backport_id("20260101T000000Z", "example", ["aha_example"])
        second_id = module._make_backport_id("20260101T000000Z", "example", ["aha_example"])
        self.assertNotEqual(first_id, second_id)
        self.record(aha_cards=[self.card()])
        skill = self.make_skill()
        args = ("export-backport", "--skill-path", str(skill), "--ids", "aha_example", "--make-diff")
        first = json.loads(self.run_cli(*args).stdout)
        bundle = Path(first["bundle_dir"])
        original_files = {path.relative_to(bundle): path.read_bytes() for path in bundle.rglob("*") if path.is_file()}
        second = json.loads(self.run_cli(*args).stdout)
        self.assertNotEqual(first["bundle_dir"], second["bundle_dir"])
        self.assertEqual(original_files, {path.relative_to(bundle): path.read_bytes() for path in bundle.rglob("*") if path.is_file()})
        self.assertFalse((skill / "references").exists())

    def test_review_and_index_only_suggest_exportable_cards(self):
        self.write_records("aha_cards.jsonl", [
            self.card(),
            self.card(id="aha_project", title="Local lesson", scope="project"),
            self.card(id="aha_string_false", title="Legacy unsafe flag", shareable="false"),
        ])
        self.write_records("signals.jsonl", [
            {"kind": "aha_used", "aha_id": card_id}
            for card_id in ("aha_example", "aha_project", "aha_string_false")
        ])
        self.record(event={"task_summary": "Refresh the index"})
        result = json.loads(self.run_cli("review", "--format", "json").stdout)
        self.assertEqual([card["id"] for card in result["aha"]["backport_candidates"]], ["aha_example"])
        index = (self.store / "INDEX.md").read_text()
        section = re.search(r"## Backport Candidates[^\n]*\n(.*?)(?:\n##|\Z)", index, re.I | re.S).group(1)
        self.assertIn("aha_example", section)
        self.assertNotIn("aha_project", section)
        self.assertNotIn("aha_string_false", section)


if __name__ == "__main__":
    unittest.main()
