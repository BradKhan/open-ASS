"""Optional Open Knowledge Format v0.2 structural reader, with explicit limits."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import okf


class OKFTests(unittest.TestCase):
    def test_read_portable_bundle_and_preserve_native_provenance(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "index.md").write_text('---\nokf_version: "0.2"\n---\n# Index\n')
            note = root / "decision.md"
            raw = ('---\ntype: Architecture Decision\n'
                   'title: Delegation contract\n'
                   'sources:\n  - uri: https://example.invalid/reference\n'
                   'status: active\n'
                   'verified:\n  - by: human:maintainer\n'
                   '    at: "2026-10-21T01:00:00Z"\n'
                   '---\n# Why\nReadable without a model.\n')
            note.write_text(raw)
            result = okf.inspect(root)
            self.assertTrue(result["conformant_structure"])
            self.assertEqual(result["count"], 2)
            item = next(x for x in result["documents"] if x["path"] == "decision.md")
            self.assertEqual(item["type"], "Architecture Decision")
            self.assertEqual(item["sha256"], hashlib.sha256(raw.encode()).hexdigest())
            self.assertEqual(item["sources"][0]["uri"], "https://example.invalid/reference")
            self.assertEqual(item["verified"][0]["by"], "human:maintainer")
            self.assertIn("no independent provenance", result["note"].lower())

    def test_missing_type_is_finding_not_unrecognized_type_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "bad.md").write_text("# no frontmatter\n")
            (root / "custom.md").write_text("---\ntype: Wildly New Type\n---\n")
            result = okf.inspect(root)
            self.assertFalse(result["conformant_structure"])
            self.assertEqual(result["findings"][0]["code"], "missing-type-frontmatter")
            self.assertIn("Wildly New Type", [x["type"] for x in result["documents"]])

    def test_yaml_aliases_do_not_execute_arbitrary_objects(self):
        with self.assertRaises(okf.OKFError):
            okf.frontmatter(
                b"---\ntype: !!python/object/apply:os.system ['echo no']\n---\nBody\n", "evil.md"
            )

    def test_symlinks_are_never_followed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "real.md").write_text("---\ntype: Note\n---\n")
            (root / "outside").mkdir()
            (root / "outside" / "secret.md").write_text("---\ntype: Private\n---\n")
            (root / "alias.md").symlink_to(root / "outside" / "secret.md")
            (root / "path").symlink_to(root / "outside", target_is_directory=True)
            result = okf.inspect(root)
            self.assertEqual(result["count"], 2)
            self.assertNotIn("path/secret.md", [x["path"] for x in result["documents"]])
            self.assertEqual(result["findings"][0]["code"], "unsafe-file")
            with self.assertRaises(okf.OKFError):
                okf.inspect(root / "path")

    def test_invalid_frontmatter_and_document_limit(self):
        with self.assertRaises(okf.OKFError):
            okf.frontmatter(b"---\nfoo: [\n---\n", "invalid.md")
        with self.assertRaises(okf.OKFError):
            okf.frontmatter(b"A" * (okf.MAX_BYTES + 1), "oversize.md")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "good.md").write_text("---\ntype: Note\n---\n")
            with patch.object(okf, "MAX_DOCUMENTS", 0):
                with self.assertRaises(okf.OKFError):
                    okf.inspect(root)

    def test_reserved_index_scope_and_metadata_handling(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "notes").mkdir()
            (root / "notes" / "index.md").write_text("---\ntype: Note\n---\n")
            (root / "concept.md").write_text("---\ntype: Playbook\n---\n")
            result = okf.inspect(root)
            self.assertEqual(result["findings"][0]["code"], "reserved-index-frontmatter")

    def test_optional_dependency_has_clear_error(self):
        with patch.object(okf, "_yaml_parser", side_effect=okf.OKFError("PyYAML missing")):
            with self.assertRaisesRegex(okf.OKFError, "PyYAML"):
                okf.frontmatter(b"---\ntype: Note\n---\n", "note.md")


if __name__ == "__main__":
    unittest.main()
