import tempfile
import unittest
from pathlib import Path

from skill_registry import list_skills, register_discovery, transition_skill


class SkillRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "skills.sqlite"
        self.skill = register_discovery(
            "evidence-research",
            "https://github.com/example/evidence-research",
            version="1.0.0",
            license_spdx="MIT",
            license_evidence="LICENSE file inspected at source revision abc123",
            inspected_files=["README.md", "LICENSE", "tests/test_skill.py"],
            evidence={"capability": "source-backed research", "confidence": "medium"},
            content="A bounded procedural skill document.",
            db_path=self.db,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def advance_to_proposed(self):
        skill_id = self.skill["skill_id"]
        transition_skill(skill_id, "ANALYZED", db_path=self.db,
                        inspected_files=["README.md", "LICENSE"],
                        evidence={"observed": "test files exist"})
        proposed = transition_skill(skill_id, "PROPOSED", db_path=self.db,
                                    content="candidate skill body")
        self.assertEqual(len(proposed["content_sha256"]), 64)
        return skill_id

    def test_analysis_requires_inspected_files_and_evidence(self):
        candidate = register_discovery(
            "no-evidence", "https://github.com/example/no-evidence", db_path=self.db
        )
        with self.assertRaisesRegex(ValueError, "inspected files"):
            transition_skill(candidate["skill_id"], "ANALYZED", db_path=self.db)

    def test_proposal_requires_its_own_content_hash(self):
        candidate = register_discovery(
            "empty-proposal", "https://github.com/example/empty-proposal", db_path=self.db
        )
        transition_skill(candidate["skill_id"], "ANALYZED", db_path=self.db,
                         inspected_files=["README.md"], evidence={"observed": "procedure described"})
        with self.assertRaisesRegex(ValueError, "content hash"):
            transition_skill(candidate["skill_id"], "PROPOSED", db_path=self.db)

    def test_passing_test_result_cannot_hide_reported_failures(self):
        skill_id = self.advance_to_proposed()
        with self.assertRaisesRegex(ValueError, "cannot include failures"):
            transition_skill(skill_id, "TESTED", db_path=self.db,
                             test_result="PASSED", test_command="python -m unittest",
                             test_report={"tests": 4, "failures": 1})

    def test_new_discovery_is_not_active(self):
        self.assertEqual(self.skill["status"], "DISCOVERED")
        self.assertEqual(self.skill["test_result"], "NOT_RUN")
        self.assertEqual(len(list_skills("DISCOVERED", self.db)), 1)
        self.assertEqual(list_skills("ACTIVE", self.db), [])

    def test_invalid_transition_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Invalid lifecycle transition"):
            transition_skill(self.skill["skill_id"], "ACTIVE", db_path=self.db, reviewer="maintainer")

    def test_failed_test_cannot_be_approved(self):
        skill_id = self.advance_to_proposed()
        transition_skill(skill_id, "TESTED", db_path=self.db,
                         test_result="FAILED", test_command="python -m unittest",
                         test_report={"failures": 1})
        with self.assertRaisesRegex(ValueError, "passing test evidence"):
            transition_skill(skill_id, "APPROVED", db_path=self.db, reviewer="maintainer")

    def test_passed_tests_without_license_evidence_cannot_be_approved(self):
        skill_id = self.advance_to_proposed()
        transition_skill(skill_id, "TESTED", db_path=self.db,
                         test_result="PASSED", test_command="python -m unittest",
                         test_report={"tests": 4, "failures": 0})
        with self.assertRaisesRegex(ValueError, "license"):
            transition_skill(skill_id, "APPROVED", db_path=self.db,
                             reviewer="maintainer", license_spdx="unknown",
                             license_evidence="")

    def test_risk_flags_block_approval(self):
        skill_id = self.advance_to_proposed()
        transition_skill(skill_id, "TESTED", db_path=self.db,
                         test_result="PASSED", test_command="python -m unittest",
                         test_report={"tests": 4, "failures": 0})
        with self.assertRaisesRegex(ValueError, "risk flags"):
            transition_skill(skill_id, "APPROVED", db_path=self.db,
                             reviewer="maintainer", risk_flags=["prompt_injection"])

    def test_only_reviewed_passed_candidate_can_be_activated(self):
        skill_id = self.advance_to_proposed()
        transition_skill(skill_id, "TESTED", db_path=self.db,
                         test_result="PASSED", test_command="python -m unittest",
                         test_report={"tests": 4, "failures": 0})
        approved = transition_skill(skill_id, "APPROVED", db_path=self.db, reviewer="reviewer-1")
        self.assertEqual(approved["status"], "APPROVED")
        self.assertEqual(approved["reviewer"], "reviewer-1")
        active = transition_skill(skill_id, "ACTIVE", db_path=self.db, reviewer="release-reviewer")
        self.assertEqual(active["status"], "ACTIVE")
        self.assertTrue(active["activated_at"])
        self.assertEqual(active["test_result"], "PASSED")

    def test_bad_source_url_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "source_url"):
            register_discovery("bad-source", "javascript:alert(1)", db_path=self.db)

    def test_content_hash_is_recorded(self):
        self.assertEqual(len(self.skill["source_content_sha256"]), 64)
        self.assertEqual(self.skill["content_sha256"], "")


if __name__ == "__main__":
    unittest.main()
