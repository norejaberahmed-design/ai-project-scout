import tempfile
import unittest
from pathlib import Path

from skill_proposal_sync import sync_proposed_skill_records
from skill_registry import list_skills


REVISION = "a" * 40
DOCUMENT = """---
name: portable-review
description: A portable procedure for evidence-based review.
version: 1.0.0
---

# Portable review

1. State the goal and acceptance criteria.
2. Inspect the relevant evidence before changing anything.
3. Make a small, reversible change.
4. Run the relevant tests and inspect the exit code.
5. Report limitations and unresolved risks without claiming unverified success.
"""
ATTRIBUTION = f"""# Upstream skill attribution

- Repository: https://github.com/example/agent-skills
- Skill file: https://github.com/example/agent-skills/blob/{REVISION}/skills/portable-review/SKILL.md
- Immutable revision: {REVISION}
- Declared SPDX license: MIT
- Original license file: LICENSE
- This is an untrusted proposal.
"""
LICENSE = "MIT License\n" + ("Permission is hereby granted, free of charge, to any person obtaining a copy. " * 4)


class SkillProposalSyncTests(unittest.TestCase):
    def write_proposal(self, root: Path, license_spdx: str = "MIT") -> Path:
        folder = root / "skills" / "proposed" / "portable-review"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(DOCUMENT, encoding="utf-8")
        attribution = ATTRIBUTION.replace("Declared SPDX license: MIT", f"Declared SPDX license: {license_spdx}")
        (folder / "ATTRIBUTION.md").write_text(attribution, encoding="utf-8")
        (folder / "UPSTREAM_LICENSE.txt").write_text(LICENSE, encoding="utf-8")
        return folder

    def test_committed_proposal_is_registered_but_never_activated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_proposal(root)
            db = root / "data" / "skills.sqlite"
            result = sync_proposed_skill_records(root=root, db_path=db)
            self.assertEqual(result["registered"], 1)
            self.assertEqual(result["items"][0]["status"], "PROPOSED")
            records = list_skills(db_path=db)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["status"], "PROPOSED")
            self.assertFalse(records[0]["license_verified"])
            self.assertIn("external_content_requires_human_review", records[0]["risk_flags"])
            self.assertFalse((root / "skills" / "active" / "portable-review").exists())

    def test_sync_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_proposal(root)
            db = root / "data" / "skills.sqlite"
            first = sync_proposed_skill_records(root=root, db_path=db)
            second = sync_proposed_skill_records(root=root, db_path=db)
            self.assertEqual(first["registered"], 1)
            self.assertEqual(second["registered"], 0)
            self.assertEqual(len(list_skills(db_path=db)), 1)

    def test_unknown_license_is_not_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_proposal(root, license_spdx="GPL-3.0")
            result = sync_proposed_skill_records(root=root, db_path=root / "data" / "skills.sqlite")
            self.assertEqual(result["registered"], 0)
            self.assertEqual(result["items"][0]["status"], "SKIPPED_INVALID_PROVENANCE_OR_CONTENT")
            self.assertEqual(list_skills(db_path=root / "data" / "skills.sqlite"), [])


if __name__ == "__main__":
    unittest.main()
