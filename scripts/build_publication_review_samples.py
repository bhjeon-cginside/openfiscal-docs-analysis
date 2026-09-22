#!/usr/bin/env python3
"""Build review units for fiscal publication document-type exclusion review.

The publication review groups are intentionally keyed only by the source type
name because UOPKOFDA01 inventory rows do not carry report-side odtId or the
three-level report classification fields.  Existing type sample page images are
reused; this script only conserves the full publication inventory around those
samples so a UI can review/exclude publication groups without losing counts.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_type_samples  # noqa: E402

DOCUMENTS = ROOT / "docs/data/documents.csv"
PUBLICATION_MANIFEST = ROOT / "openfiscal_publications/lists/manifest.csv"
TYPE_SAMPLES = ROOT / "docs/data/type_samples.json"
DASHBOARD = ROOT / "docs/data/dashboard.json"
OUTPUT = ROOT / "docs/data/publication_review_samples.json"
SOURCE_ID = "publications"
SOURCE_URL = "https://www.openfiscaldata.go.kr/op/ko/fd/UOPKOFDA01"
CORPUS = "UOPKOFDA01_publications"
NO_PREVIEW_REASON = "유형별 대표 미리보기가 없어 원문 확인 후 제외 여부를 수동 판정하세요. 제외 판정이 아닙니다."
NO_ATTACHMENT_STATUS = "no_downloadable_file"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def publication_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("source_id") == SOURCE_ID]


def stable_id(data_name: str) -> str:
    return build_type_samples.asset_stem(CORPUS, data_name)


def as_year(value: str) -> tuple[int, str]:
    try:
        return (int(value), value)
    except (TypeError, ValueError):
        return (-1, str(value))


def grouped_inventory(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        data_name = row.get("type", "").strip()
        if not data_name:
            raise ValueError(f"Publication row is missing type/data_name: {row}")
        groups[data_name].append(row)
    return dict(groups)


def publication_samples(payload: dict) -> dict[str, dict]:
    samples: dict[str, dict] = {}
    for sample in payload.get("samples", []):
        if sample.get("source_id") != SOURCE_ID:
            continue
        data_name = sample.get("type", "").strip()
        if not data_name:
            raise ValueError(f"Publication sample is missing type: {sample}")
        if data_name in samples:
            raise ValueError(f"Duplicate publication sample for type: {data_name}")
        expected = stable_id(data_name)
        if sample.get("id") != expected:
            raise ValueError(f"Unexpected sample id for {data_name}: {sample.get('id')} != {expected}")
        samples[data_name] = sample
    return samples


def category_codes(manifest_rows: list[dict[str, str]], groups: dict[str, list[dict[str, str]]]) -> dict[str, str]:
    """Return the exact UOPKOFDA01 category code per data name.

    The source field is `ofdBrdiDtsClsCd` in UOPKOFDA02 detail URLs; the
    tracked publication manifest stores that server/common-code value as
    `category_code` (common code OP061 under parent 05).
    """
    codes: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for row in manifest_rows:
        name = row.get("category_name", "").strip()
        code = row.get("category_code", "").strip()
        if not name or not code:
            raise ValueError(f"Publication manifest row missing category name/code: {row}")
        if name in codes and codes[name] != code:
            raise ValueError(f"Multiple category codes for {name}: {codes[name]} and {code}")
        codes[name] = code
        counts[name] += 1
    inventory_types = set(groups)
    manifest_types = set(codes)
    missing = sorted(inventory_types - manifest_types)
    extra = sorted(manifest_types - inventory_types)
    if missing or extra:
        raise ValueError(
            "Publication manifest/inventory category mismatch. "
            f"missing_manifest={missing}, extra_manifest={extra}"
        )
    count_mismatches = {name: (len(groups[name]), counts[name]) for name in sorted(groups) if len(groups[name]) != counts[name]}
    if count_mismatches:
        raise ValueError(f"Publication manifest/inventory count mismatch: {count_mismatches}")
    return codes


def validate_sample_coverage(groups: dict[str, list[dict[str, str]]], samples: dict[str, dict]) -> None:
    inventory_types = set(groups)
    sample_types = set(samples)
    missing = sorted(inventory_types - sample_types)
    extra = sorted(sample_types - inventory_types)
    if missing or extra:
        raise ValueError(
            "Publication sample/inventory mismatch; refusing to silently drop source data. "
            f"missing_samples={missing}, extra_samples={extra}"
        )


def sample_documents(sample: dict) -> list[dict]:
    documents = sample.get("sample", {}).get("documents", [])
    if not isinstance(documents, list):
        raise ValueError(f"Sample documents must be a list for {sample.get('type')}")
    return documents


def build_groups(rows: list[dict[str, str]], samples: dict[str, dict], manifest_rows: list[dict[str, str]]) -> list[dict]:
    groups = grouped_inventory(rows)
    validate_sample_coverage(groups, samples)
    codes = category_codes(manifest_rows, groups)
    output = []
    for data_name in sorted(groups):
        members = groups[data_name]
        documents = sample_documents(samples[data_name])
        no_attachment_count = sum(row.get("status") == NO_ATTACHMENT_STATUS for row in members)
        attachment_members = [row for row in members if row.get("status") != NO_ATTACHMENT_STATUS]
        output.append({
            "id": stable_id(data_name),
            "type": data_name,
            "data_name": data_name,
            "category_code": codes[data_name],
            "record_count": len(members),
            "no_attachment_count": no_attachment_count,
            "file_count": len(attachment_members),
            "years": sorted({row.get("year", "") for row in members if row.get("year", "")}, key=as_year),
            "extensions": sorted({row.get("extension", "").lower() for row in attachment_members if row.get("extension", "") and row.get("extension", "") != "미상"}),
            "documents": documents,
            "no_preview_reason": "" if documents else NO_PREVIEW_REASON,
            "source_url": SOURCE_URL,
        })
    return output


def known_source_checked_at(rows: list[dict[str, str]], dashboard: dict) -> str:
    candidates = [row.get("source_checked_at", "") or row.get("last_checked_at", "") for row in rows]
    for source in dashboard.get("sources", []):
        if source.get("id") == SOURCE_ID:
            candidates.extend([source.get("source_checked_at", ""), source.get("last_checked_at", "")])
    return max((value for value in candidates if value), default="")


def build_payload() -> dict:
    documents = read_csv(DOCUMENTS)
    rows = publication_rows(documents)
    manifest_rows = read_csv(PUBLICATION_MANIFEST)
    samples_payload = load_json(TYPE_SAMPLES)
    dashboard = load_json(DASHBOARD)
    groups = build_groups(rows, publication_samples(samples_payload), manifest_rows)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_url": SOURCE_URL,
        "inventory_generated_at": dashboard.get("generated_at", ""),
        "samples_generated_at": samples_payload.get("generated_at", ""),
        "summary": {
            "record_count": len(rows),
            "file_count": sum(group["file_count"] for group in groups),
            "no_attachment_count": sum(group["no_attachment_count"] for group in groups),
            "group_count": len(groups),
            "groups_with_samples": sum(bool(group["documents"]) for group in groups),
            "representative_documents": sum(len(group["documents"]) for group in groups),
        },
        "groups": groups,
    }
    if checked_at := known_source_checked_at(rows, dashboard):
        payload["source_checked_at"] = checked_at
    return payload


def main() -> None:
    payload = build_payload()
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
