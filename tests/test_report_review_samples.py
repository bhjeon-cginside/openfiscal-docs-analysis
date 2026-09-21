"""Classification boundaries and preview coverage must be explicit and stable."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_report_review_samples as build


class ClassificationTests(unittest.TestCase):
    def test_three_levels_not_data_name(self):
        self.assertEqual(build.classification("예산>정부예산기금안>기금운용계획안"),
                         {"large": "예산", "middle": "정부예산기금안", "small": "기금운용계획안"})

    def test_missing_levels_preserved(self):
        self.assertEqual(build.classification("지방재정"),
                         {"large": "지방재정", "middle": "", "small": ""})
        self.assertEqual(build.classification("결산>결산보고서")["small"], "")
        self.assertEqual(build.classification("A>>C")["middle"], "")

    def test_unexpected_depth_rejected(self):
        with self.assertRaises(ValueError):
            build.classification("a>b>c>d")

    def test_same_name_different_id_or_path_stays_separate(self):
        row = {"allDtaClsNm": "A>B", "odtId": "id1", "odtNm": "보고서"}
        first = build.stable_id(build.group_key(row))
        self.assertNotEqual(first, build.stable_id(build.group_key({**row, "odtId": "id2"})))
        self.assertNotEqual(first, build.stable_id(build.group_key({**row, "allDtaClsNm": "A>C"})))

    def test_only_explicit_historical_rows_omitted(self):
        rows = [{"source_in_current_list": "False"}, {"source_in_current_list": "True"}, {}]
        self.assertEqual(build.current_rows(rows), rows[1:])

    def test_source_path_rejects_absolute_and_traversal(self):
        for path in ("../outside.pdf", "/tmp/outside.pdf"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                build.resolve_source_path(path)
        self.assertTrue(build.resolve_source_path("예산/example.pdf").is_relative_to(build.FILES_ROOT.resolve()))

    def test_source_path_rejects_escaping_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "files"
            root.mkdir()
            (root / "link.pdf").symlink_to(Path(temporary) / "outside.pdf")
            with patch.object(build, "FILES_ROOT", root), self.assertRaises(ValueError):
                build.resolve_source_path("link.pdf")

    def test_preview_format_diversity_and_limit(self):
        rows = [{"fileExt": ext, "acntYr": str(2026-i), "dpFileNm": "test",
                 "atchFileId": "id", "atchFileSeq": str(i)}
                for i, ext in enumerate(["pdf", "pdf", "hwp", "zip"])]
        with patch.object(build, "make_document", side_effect=lambda r, *_: {"id": build.attachment_id(r)}):
            self.assertEqual(build.select_documents(rows, {}, {}), [{"id": "id:0"}, {"id": "id:2"}])

    def test_failed_previews_do_not_remove_review_unit(self):
        rows = [{"fileExt": "zip", "acntYr": "2026", "dpFileNm": "test",
                 "atchFileId": "id", "atchFileSeq": "1"}]
        with patch.object(build, "make_document") as render:
            self.assertEqual(build.select_documents(rows, {}, {}), [])
            render.assert_not_called()


class PublishedDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not build.OUTPUT.exists():
            raise unittest.SkipTest("Generate report_review_samples.json first")
        cls.data = json.loads(build.OUTPUT.read_text())

    def test_all_current_manifest_files_represented_once(self):
        rows = build.current_rows(build.renderer.read_csv(build.MANIFEST))
        from collections import Counter
        counts = Counter(build.group_key(row) for row in rows)
        self.assertEqual(self.data["summary"]["file_count"], len(rows))
        self.assertEqual(len(self.data["groups"]), len(counts))
        for group in self.data["groups"]:
            key = (group["classification_path"], group["odt_id"], group["data_name"])
            self.assertEqual(group["file_count"], counts.pop(key))
            self.assertEqual(group["classification"], build.classification(key[0]))
            self.assertNotIn("status", group, "Do not inherit broad exclusion judgments")
        self.assertEqual(counts, {})

    def test_sample_identity_belongs_to_group_and_assets_exist(self):
        rows = build.current_rows(build.renderer.read_csv(build.MANIFEST))
        allowed = {build.group_key(row): set() for row in rows}
        for row in rows:
            allowed[build.group_key(row)].add(build.attachment_id(row))
        for group in self.data["groups"]:
            key = (group["classification_path"], group["odt_id"], group["data_name"])
            self.assertLessEqual(len(group["documents"]), 2)
            if not group["documents"]:
                self.assertTrue(group["no_preview_reason"])
            for document in group["documents"]:
                self.assertIn(document["id"], allowed[key])
                self.assertGreater(len(document["pages"]), 0)
                self.assertLessEqual(len(document["pages"]), 10)
                for page in document["pages"]:
                    self.assertTrue((ROOT / "docs/type-examples" / page["image"]).is_file(), page["image"])
                    self.assertLessEqual(page["page"], document["document_pages"])


if __name__ == "__main__":
    unittest.main()
