"""Publication review sample data must conserve inventory and existing samples."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_publication_review_samples as build


class PublicationBuilderTests(unittest.TestCase):
    def test_sample_id_uses_existing_type_sample_convention(self):
        self.assertEqual(build.stable_id("IMF"), "publications-5e45453b7353")

    def test_sample_inventory_mismatch_is_rejected(self):
        groups = {"A": [{"type": "A"}], "B": [{"type": "B"}]}
        samples = {"A": {"type": "A", "id": build.stable_id("A")}, "C": {"type": "C", "id": build.stable_id("C")}}
        with self.assertRaisesRegex(ValueError, "missing_samples=.*B.*extra_samples=.*C"):
            build.validate_sample_coverage(groups, samples)

    def test_missing_preview_group_stays_visible(self):
        rows = [{"source_id": "publications", "type": "테스트", "year": "2026", "extension": "PDF"}]
        samples = {"테스트": {"id": build.stable_id("테스트"), "type": "테스트", "sample": {"documents": []}}}
        groups = build.build_groups(rows, samples, [{"category_name": "테스트", "category_code": "999"}])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["documents"], [])
        self.assertIn("수동 판정", groups[0]["no_preview_reason"])

    def test_years_and_extensions_use_all_inventory_rows_not_samples(self):
        rows = [
            {"source_id": "publications", "type": "테스트", "year": "2024", "extension": "PDF"},
            {"source_id": "publications", "type": "테스트", "year": "2026", "extension": "zip"},
            {"source_id": "publications", "type": "테스트", "year": "2025", "extension": "HWP"},
        ]
        samples = {"테스트": {"id": build.stable_id("테스트"), "type": "테스트", "sample": {"documents": [
            {"title": "only one sample", "year": "2026", "extension": "pdf", "pages": []}
        ]}}}
        group = build.build_groups(rows, samples, [{"category_name": "테스트", "category_code": "999"} for _ in rows])[0]
        self.assertEqual(group["years"], ["2024", "2025", "2026"])
        self.assertEqual(group["extensions"], ["hwp", "pdf", "zip"])
        self.assertEqual(group["record_count"], 3)
        self.assertEqual(group["file_count"], 3)
        self.assertEqual(group["no_attachment_count"], 0)
        self.assertEqual(group["category_code"], "999")

    def test_no_attachment_rows_count_as_records_not_files_or_extensions(self):
        rows = [
            {"source_id": "publications", "type": "테스트", "year": "2026", "extension": "pdf", "status": "downloaded"},
            {"source_id": "publications", "type": "테스트", "year": "2024", "extension": "미상", "status": build.NO_ATTACHMENT_STATUS},
        ]
        samples = {"테스트": {"id": build.stable_id("테스트"), "type": "테스트", "sample": {"documents": []}}}
        group = build.build_groups(rows, samples, [{"category_name": "테스트", "category_code": "999"} for _ in rows])[0]
        self.assertEqual(group["record_count"], 2)
        self.assertEqual(group["file_count"], 1)
        self.assertEqual(group["no_attachment_count"], 1)
        self.assertEqual(group["years"], ["2024", "2026"])
        self.assertEqual(group["extensions"], ["pdf"])

    def test_source_checked_at_is_omitted_when_unknown(self):
        docs = [{"source_id": "publications", "type": "테스트", "year": "2026", "extension": "pdf", "status": "downloaded"}]
        manifest = [{"category_name": "테스트", "category_code": "999"}]
        with patch.object(build, "read_csv", side_effect=[docs, manifest]), \
             patch.object(build, "load_json", side_effect=[
                 {"generated_at": "samples-time", "samples": [{"id": build.stable_id("테스트"), "source_id": "publications", "type": "테스트", "sample": {"documents": []}}]},
                 {"generated_at": "inventory-time", "sources": [{"id": "publications"}]},
             ]):
            payload = build.build_payload()
        self.assertNotIn("source_checked_at", payload)


class PublishedPublicationDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not build.OUTPUT.exists():
            raise unittest.SkipTest("Generate publication_review_samples.json first")
        cls.data = json.loads(build.OUTPUT.read_text(encoding="utf-8"))
        cls.rows = build.publication_rows(build.read_csv(build.DOCUMENTS))
        cls.samples = build.publication_samples(json.loads(build.TYPE_SAMPLES.read_text(encoding="utf-8")))

    def test_all_publication_inventory_files_are_represented_once(self):
        grouped = build.grouped_inventory(self.rows)
        self.assertEqual(self.data["summary"]["record_count"], 1698)
        self.assertEqual(self.data["summary"]["file_count"], 1695)
        self.assertEqual(self.data["summary"]["no_attachment_count"], 3)
        self.assertEqual(self.data["summary"]["record_count"], len(self.rows))
        self.assertEqual(self.data["summary"]["group_count"], 15)
        self.assertEqual(len(self.data["groups"]), len(grouped))
        remaining = {name: rows for name, rows in grouped.items()}
        for group in self.data["groups"]:
            members = remaining.pop(group["data_name"])
            no_attachment_count = sum(row["status"] == build.NO_ATTACHMENT_STATUS for row in members)
            self.assertEqual(group["record_count"], len(members))
            self.assertEqual(group["no_attachment_count"], no_attachment_count)
            self.assertEqual(group["file_count"], len(members) - no_attachment_count)
            self.assertNotIn("odt_id", group)
            self.assertNotIn("classification", group)
            self.assertNotIn("exclusion_sets", group)
        self.assertEqual(remaining, {})
        self.assertNotIn("exclusion_sets", self.data)

    def test_sample_identity_and_document_count_are_conserved(self):
        self.assertEqual(self.data["summary"]["groups_with_samples"], 15)
        self.assertEqual(self.data["summary"]["representative_documents"], 43)
        for group in self.data["groups"]:
            sample = self.samples[group["data_name"]]
            self.assertEqual(group["id"], sample["id"])
            self.assertEqual(group["documents"], sample.get("sample", {}).get("documents", []))

    def test_sample_asset_paths_exist(self):
        for group in self.data["groups"]:
            if not group["documents"]:
                self.assertTrue(group["no_preview_reason"])
            for document in group["documents"]:
                self.assertGreater(len(document.get("pages", [])), 0)
                for page in document["pages"]:
                    self.assertTrue((ROOT / "docs/type-examples" / page["image"]).is_file(), page["image"])

    def test_group_years_and_extensions_match_full_inventory(self):
        grouped = build.grouped_inventory(self.rows)
        for group in self.data["groups"]:
            members = grouped[group["data_name"]]
            self.assertEqual(group["years"], sorted({row["year"] for row in members if row["year"]}, key=build.as_year))
            expected_extensions = sorted({row["extension"].lower() for row in members
                                          if row["status"] != build.NO_ATTACHMENT_STATUS and row["extension"] and row["extension"] != "미상"})
            self.assertEqual(group["extensions"], expected_extensions)

    def test_metadata_uses_known_generation_times_without_inventing_checked_at(self):
        dashboard = json.loads(build.DASHBOARD.read_text(encoding="utf-8"))
        samples = json.loads(build.TYPE_SAMPLES.read_text(encoding="utf-8"))
        self.assertEqual(self.data["source_url"], build.SOURCE_URL)
        self.assertEqual(self.data["inventory_generated_at"], dashboard["generated_at"])
        self.assertEqual(self.data["samples_generated_at"], samples["generated_at"])
        self.assertNotIn("source_checked_at", self.data)

    def test_category_codes_are_unique_manifest_codes(self):
        manifest_rows = build.read_csv(build.PUBLICATION_MANIFEST)
        grouped = build.grouped_inventory(self.rows)
        codes = build.category_codes(manifest_rows, grouped)
        self.assertEqual(len(codes), 15)
        self.assertEqual({group["data_name"]: group["category_code"] for group in self.data["groups"]}, codes)
        self.assertEqual(codes["회계·기금운용구조"], "505")
        self.assertEqual(codes["월간나라재정"], "516")
        self.assertEqual(codes["월간재정동향"], "501")


if __name__ == "__main__":
    unittest.main()
