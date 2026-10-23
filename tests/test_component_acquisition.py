import base64
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

from component_acquisition import (acquire_repository, auto_acquire_repositories, inspect_repository, parse_repository_url)

OWNER = "example"
REPO = "safe-ai-tool"
REVISION = "a" * 40
BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"
FILES = {
    "LICENSE": b"MIT License\\nPermission is hereby granted, free of charge, to any person obtaining a copy",
    "README.md": b"# Safe AI Tool\nA small example library.",
    "src/tool.py": b"def answer():\n    return 'ok'\n",
    ".env": b"SECRET=should-not-copy",
    "src/private.key": b"PRIVATE KEY",
    "assets/model.bin": b"\\x00binary",
}
TREE = [
    {"path": path, "type": "blob", "mode": "100644", "size": len(content)}
    for path, content in FILES.items()
] + [
    {"path": "src/linked.py", "type": "blob", "mode": "120000", "size": 12},
    {"path": "../escape.py", "type": "blob", "mode": "100644", "size": 10},
]


def fake_fetcher(url):
    if url == BASE:
        return {
            "full_name": f"{OWNER}/{REPO}",
            "html_url": f"https://github.com/{OWNER}/{REPO}",
            "description": "A test fixture, not real software",
            "default_branch": "main",
            "private": False,
            "archived": False,
            "license": {"spdx_id": "MIT"},
            "stargazers_count": 42,
            "pushed_at": "2026-01-01T00:00:00Z",
        }
    if url == f"{BASE}/commits/main":
        return {"sha": REVISION}
    if url == f"{BASE}/git/trees/{REVISION}?recursive=1":
        return {"tree": TREE, "truncated": False}
    prefix = f"{BASE}/contents/"
    if url.startswith(prefix):
        remainder = url[len(prefix):]
        encoded_path, _, _query = remainder.partition("?")
        path = encoded_path.replace("%2F", "/").replace("%2f", "/")
        if path not in FILES:
            raise RuntimeError("Fixture file not found")
        return {
            "encoding": "base64",
            "content": base64.b64encode(FILES[path]).decode("ascii"),
        }
    raise AssertionError("Unexpected URL: " + url)


class ComponentAcquisitionTests(unittest.TestCase):
    def test_repository_url_must_be_a_root_url(self):
        self.assertEqual(parse_repository_url("https://github.com/example/safe-ai-tool"), (OWNER, REPO))
        for url in (
            "https://github.com/example/safe-ai-tool/tree/main",
            "https://github.com/example/safe-ai-tool/issues/1",
            "https://evil.example/example/safe-ai-tool",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_repository_url(url)

    def test_inspection_requires_allowlisted_license_and_fixed_revision(self):
        result = inspect_repository(f"https://github.com/{OWNER}/{REPO}", fetcher=fake_fetcher)
        self.assertEqual(result["license_spdx"], "MIT")
        self.assertEqual(result["revision"], REVISION)
        paths = {item["path"] for item in result["eligible_files"]}
        self.assertIn("LICENSE", paths)
        self.assertIn("src/tool.py", paths)
        self.assertNotIn(".env", paths)
        self.assertNotIn("src/private.key", paths)
        self.assertNotIn("assets/model.bin", paths)
        self.assertNotIn("src/linked.py", paths)
        self.assertNotIn("../escape.py", paths)

    def test_unknown_license_fails_closed(self):
        def unknown_license(url):
            result = fake_fetcher(url)
            if url == BASE:
                result["license"] = {"spdx_id": "UNKNOWN"}
            return result
        with self.assertRaisesRegex(ValueError, "License is not on the acquisition allowlist"):
            inspect_repository(f"https://github.com/{OWNER}/{REPO}", fetcher=unknown_license)

    def test_no_copy_without_explicit_approval(self):
        with self.assertRaises(PermissionError):
            acquire_repository(f"https://github.com/{OWNER}/{REPO}", approved=False, fetcher=fake_fetcher)

    def test_acquisition_copies_to_proposed_quarantine_and_records_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = acquire_repository(
                f"https://github.com/{OWNER}/{REPO}",
                approved=True,
                root=tmp,
                fetcher=fake_fetcher,
            )
            target = Path(result["destination"])
            manifest = result["manifest"]
            self.assertEqual(manifest["status"], "PROPOSED_REVIEW_REQUIRED")
            self.assertFalse(manifest["execution_allowed"])
            self.assertFalse(manifest["installation_allowed"])
            self.assertFalse(manifest["activation_allowed"])
            self.assertEqual((target / "LICENSE").read_bytes(), FILES["LICENSE"])
            self.assertEqual((target / "src" / "tool.py").read_bytes(), FILES["src/tool.py"])
            self.assertTrue((target / "ACQUISITION_MANIFEST.json").is_file())
            self.assertFalse((target / ".env").exists())
            self.assertFalse((target / "src" / "private.key").exists())
            self.assertFalse((target / "assets" / "model.bin").exists())
            self.assertTrue(all(len(item["sha256"]) == 64 for item in manifest["files"]))
            self.assertEqual(manifest["copied_file_count"], len(manifest["files"]))

    def test_truncated_tree_is_refused(self):
        def truncated(url):
            result = fake_fetcher(url)
            if url.endswith(f"/git/trees/{REVISION}?recursive=1"):
                result["truncated"] = True
            return result
        with self.assertRaisesRegex(ValueError, "truncated"):
            inspect_repository(f"https://github.com/{OWNER}/{REPO}", fetcher=truncated)


    def test_automatic_acquisition_is_opt_in_and_does_not_fetch_when_disabled(self):
        result = auto_acquire_repositories(
            [{"url": f"https://github.com/{OWNER}/{REPO}"}],
            enabled=False,
            root=tempfile.mkdtemp(),
            fetcher=lambda _url: self.fail("disabled mode must not fetch repositories"),
        )
        self.assertFalse(result["enabled"])
        self.assertEqual(result["copied"], 0)
        self.assertEqual(result["attempted"], 0)

    def test_automatic_acquisition_stages_eligible_repo_and_records_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = auto_acquire_repositories(
                [{"url": f"https://github.com/{OWNER}/{REPO}"}],
                enabled=True,
                max_items=2,
                root=tmp,
                fetcher=fake_fetcher,
            )
            self.assertTrue(result["enabled"])
            self.assertEqual(result["attempted"], 1)
            self.assertEqual(result["copied"], 1)
            item = result["items"][0]
            self.assertEqual(item["status"], "PROPOSED_REVIEW_REQUIRED")
            manifest = Path(item["destination"]) / "ACQUISITION_MANIFEST.json"
            self.assertTrue(manifest.is_file())
            self.assertFalse(item.get("activation_allowed", False))

    def test_automatic_acquisition_skips_unknown_license_without_copying(self):
        with tempfile.TemporaryDirectory() as tmp:
            def unknown_license(url):
                result = fake_fetcher(url)
                if url == BASE:
                    result["license"] = {"spdx_id": "UNKNOWN"}
                return result
            result = auto_acquire_repositories(
                [{"url": f"https://github.com/{OWNER}/{REPO}"}],
                enabled=True,
                root=tmp,
                fetcher=unknown_license,
            )
            self.assertEqual(result["copied"], 0)
            self.assertEqual(result["items"][0]["status"], "SKIPPED")
            self.assertFalse((Path(tmp) / "components" / "proposed").exists())



    def test_already_staged_revision_does_not_consume_auto_acquisition_quota(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = f"https://github.com/{OWNER}/{REPO}"
            first = auto_acquire_repositories(
                [{"url": url}], enabled=True, max_items=1, root=tmp, fetcher=fake_fetcher
            )
            self.assertEqual(first["copied"], 1)
            second = auto_acquire_repositories(
                [{"url": url}, {"url": url}], enabled=True, max_items=1, root=tmp, fetcher=fake_fetcher
            )
            self.assertEqual(second["attempted"], 0)
            self.assertEqual(second["copied"], 0)
            self.assertTrue(all(item["status"] == "ALREADY_STAGED" for item in second["items"]))



if __name__ == "__main__":
    unittest.main()
