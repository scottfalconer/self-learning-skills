"""Validate the skill metadata and its local document links."""

from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[1]


class SkillPackageTests(unittest.TestCase):
    def test_frontmatter_follows_agent_skills_format(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        sections = text.split("---", 2)
        self.assertEqual(sections[0], "", "SKILL.md must start with YAML frontmatter")
        self.assertEqual(len(sections), 3, "The YAML block must have an end marker")
        metadata = yaml.safe_load(sections[1])
        self.assertIsInstance(metadata, dict)
        allowed = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
        self.assertFalse(set(metadata) - allowed)
        name = metadata["name"]
        self.assertIsInstance(name, str)
        self.assertRegex(name, r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
        self.assertLessEqual(len(name), 64)
        description = metadata["description"]
        self.assertIsInstance(description, str)
        self.assertTrue(description.strip())
        self.assertLessEqual(len(description), 1024)
        if "compatibility" in metadata:
            self.assertIsInstance(metadata["compatibility"], str)
            self.assertTrue(metadata["compatibility"].strip())
            self.assertLessEqual(len(metadata["compatibility"]), 500)
        if "metadata" in metadata:
            self.assertIsInstance(metadata["metadata"], dict)
            for key, value in metadata["metadata"].items():
                self.assertIsInstance(key, str)
                self.assertIsInstance(value, str)
        self.assertTrue(sections[2].strip(), "The skill must have instructions")

    def test_local_document_links_resolve_inside_package(self):
        documents = [*ROOT.glob("*.md"), *ROOT.glob("references/*.md"),
                     *ROOT.glob("docs/*.md"), ROOT / "scripts/README.md"]
        for document in documents:
            text = document.read_text(encoding="utf-8")
            text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
            for target in re.findall(r"\[[^\]]+\]\(([^\s)]+)\)", text):
                parts = urlsplit(target)
                if parts.scheme or parts.netloc or not parts.path:
                    continue
                with self.subTest(document=document.relative_to(ROOT), target=target):
                    resolved = (document.parent / unquote(parts.path)).resolve()
                    self.assertTrue(resolved.is_relative_to(ROOT))
                    self.assertTrue(resolved.exists(), f"Missing link target: {target}")

    def test_codex_metadata_has_a_valid_interface(self):
        metadata = yaml.safe_load((ROOT / "agents/openai.yaml").read_text(encoding="utf-8"))
        interface = metadata["interface"]
        for key in ("display_name", "short_description", "default_prompt"):
            self.assertIsInstance(interface[key], str)
            self.assertTrue(interface[key].strip())
        self.assertGreaterEqual(len(interface["short_description"]), 25)
        self.assertLessEqual(len(interface["short_description"]), 64)
        self.assertIn("$self-learning-skills", interface["default_prompt"])


if __name__ == "__main__":
    unittest.main()
