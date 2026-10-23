import unittest

from skill_evaluator import parse_evaluation_cases, run_benchmark, score_output


DOCUMENT = """---
name: evidence-first
description: Require evidence and uncertainty when reviewing technical claims.
version: 1
---

# Procedure
1. Identify the claim.
2. Require evidence and tests.

## Evaluation cases
### Case 1: Code review
Task: Review a fictional code change and explain how to validate it.
Must include: evidence; test
Must not include: fabricated

### Case 2: Research review
Task: Summarize a technical claim and identify what remains uncertain.
Must include: source; uncertainty
Must not include: guaranteed
"""


class SkillEvaluatorTests(unittest.TestCase):
    def test_parses_two_explicit_evaluation_cases(self):
        cases = parse_evaluation_cases(DOCUMENT)
        self.assertEqual(len(cases), 2)
        self.assertIn("evidence", cases[0]["must_include"])
        self.assertEqual(cases[1]["must_not_include"], ["guaranteed"])

    def test_rejects_missing_test_specification(self):
        with self.assertRaisesRegex(ValueError, "Evaluation cases"):
            parse_evaluation_cases("---\nname: x\ndescription: long enough description\n---\nNo test cases.")

    def test_scores_required_and_forbidden_terms(self):
        result = score_output("Evidence found; test planned; no fabricated result.", {
            "must_include": ["evidence", "test"],
            "must_not_include": ["guaranteed"],
        })
        self.assertTrue(result["passed"])

    def test_skill_must_pass_and_improve_over_baseline(self):
        def fake_model(task, skill):
            if skill:
                return "evidence test source uncertainty"
            return "general answer without evidence"
        report = run_benchmark(DOCUMENT, parse_evaluation_cases(DOCUMENT), fake_model)
        self.assertEqual(report["status"], "PASSED")
        self.assertEqual(report["tests"], 2)
        self.assertEqual(report["failures"], 0)
        self.assertGreater(report["improved_cases"], 0)

    def test_no_improvement_is_not_marked_as_passed(self):
        def fake_model(task, skill):
            return "evidence test source uncertainty"
        report = run_benchmark(DOCUMENT, parse_evaluation_cases(DOCUMENT), fake_model)
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["failures"], 1)


if __name__ == "__main__":
    unittest.main()
