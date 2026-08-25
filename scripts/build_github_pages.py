#!/usr/bin/env python3
"""Build the OCR-free GitHub Pages dataset for Open Fiscal documents.

The source manifests stay authoritative.  This script creates small, publishable
derivatives only: no original documents, extracted ZIP contents, or OCR output
is copied into ``docs/``.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DATA = DOCS / "data"

REPORT_MANIFEST = ROOT / "openfiscal_report_documents/lists/manifest.csv"
PUBLICATION_MANIFEST = ROOT / "openfiscal_publications/lists/manifest.csv"
BASE_PAGES = ROOT / "page_count_analysis/document_page_counts.csv"
HWP_PAGES = ROOT / "page_count_analysis/standalone_hwp_hwpx_page_counts_with_rhwp.csv"
HWP_LOSSY_PAGES = ROOT / "page_count_analysis/standalone_hwp_hwpx_page_counts_lossy_utf16_retry.csv"
ZIP_PAGES = ROOT / "page_count_analysis/zip_inner_page_counts_by_parent_with_rhwp.csv"
FINAL_PAGES = ROOT / "page_count_analysis/final_page_count_by_corpus_with_lossy_utf16_recovery.csv"

SOURCE_META = {
    "UOPKOFDA03_report_documents": {
        "id": "reports",
        "name": "재정보고서 및 문서",
        "url": "https://www.openfiscaldata.go.kr/op/ko/fd/UOPKOFDA03",
        "year_basis": "회계연도",
    },
    "UOPKOFDA01_publications": {
        "id": "publications",
        "name": "재정간행물",
        "url": "https://www.openfiscaldata.go.kr/op/ko/fd/UOPKOFDA01",
        "year_basis": "게시연도",
    },
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def as_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def sort_year(value: str) -> tuple[int, str]:
    parsed = as_int(value)
    return (parsed if parsed is not None else -1, value)


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def page_maps() -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    """Return direct, HWP/HWPX, and ZIP page measurements keyed by doc id."""
    direct: dict[str, dict[str, object]] = {}
    for row in read_csv(BASE_PAGES):
        if row["corpus"] not in SOURCE_META:
            continue
        pages = as_int(row.get("page_count"))
        if pages is not None:
            direct[row["doc_id"]] = {
                "page_count": pages,
                "page_status": row["page_status"],
                "page_method": "PDF 직접 측정",
                "included_file_count": 1,
            }

    hwp: dict[str, dict[str, object]] = {}
    for path, method in (
        (HWP_PAGES, "HWP/HWPX 렌더링"),
        (HWP_LOSSY_PAGES, "HWP/HWPX 렌더링 (UTF-16 복구)"),
    ):
        for row in read_csv(path):
            if row["corpus"] not in SOURCE_META:
                continue
            pages = as_int(row.get("page_count"))
            if pages is not None:
                # The lossy recovery file only changes previous failures, so an
                # overwrite is safe and prevents a document being counted twice.
                hwp[row["doc_id"]] = {
                    "page_count": pages,
                    "page_status": row["page_status"],
                    "page_method": method,
                    "included_file_count": 1,
                }

    zipped: dict[str, dict[str, object]] = {}
    for row in read_csv(ZIP_PAGES):
        if row["parent_corpus"] not in SOURCE_META:
            continue
        pages = as_int(row.get("total_pages"))
        if pages is not None:
            zipped[row["parent_doc_id"]] = {
                "page_count": pages,
                "page_status": row["page_status"],
                "page_method": "ZIP 내부 PDF/HWP/HWPX 합산",
                "included_file_count": as_int(row.get("inner_files")) or 0,
            }
    return direct, hwp, zipped


def build_documents() -> list[dict[str, object]]:
    direct, hwp, zipped = page_maps()
    documents: list[dict[str, object]] = []

    for row in read_csv(REPORT_MANIFEST):
        category = row.get("allDtaClsNm", "") or "미분류"
        major, _, detail = category.partition(">")
        doc_id = f"uopkofda03:{row.get('atchFileId', '')}:{row.get('atchFileSeq', '')}"
        measurement = zipped.get(doc_id) or hwp.get(doc_id) or direct.get(doc_id)
        local_path = ROOT / "openfiscal_report_documents/files" / row["dest_path"] if row.get("dest_path") else None
        documents.append(
            {
                "source_id": "reports",
                "source_name": SOURCE_META["UOPKOFDA03_report_documents"]["name"],
                "year_basis": SOURCE_META["UOPKOFDA03_report_documents"]["year_basis"],
                "year": str(row.get("acntYr", "") or "미상"),
                "major_type": major or "미분류",
                "type": category,
                "type_detail": detail,
                "title": row.get("dpFileNm", "") or row.get("odtNm", "") or "제목 없음",
                "extension": (row.get("fileExt", "") or "미상").lower(),
                "size_bytes": as_int(row.get("atchFileSz")) or 0,
                "verified_size_bytes": local_path.stat().st_size if local_path and local_path.is_file() else None,
                "status": row.get("status", "") or "미상",
                "page_count": measurement["page_count"] if measurement else None,
                "page_status": measurement["page_status"] if measurement else "미측정",
                "page_method": measurement["page_method"] if measurement else "미측정",
                "included_file_count": measurement["included_file_count"] if measurement else 1,
                "source_url": SOURCE_META["UOPKOFDA03_report_documents"]["url"],
            }
        )

    for row in read_csv(PUBLICATION_MANIFEST):
        doc_id = "uopkofda01:{category_code}:{publication_seq}:{atch_file_id}:{atch_file_seq}".format(**row)
        measurement = zipped.get(doc_id) or hwp.get(doc_id) or direct.get(doc_id)
        category = row.get("category_name", "") or "미분류"
        local_path = ROOT / "openfiscal_publications" / row["local_path"] if row.get("local_path") else None
        documents.append(
            {
                "source_id": "publications",
                "source_name": SOURCE_META["UOPKOFDA01_publications"]["name"],
                "year_basis": SOURCE_META["UOPKOFDA01_publications"]["year_basis"],
                "year": (row.get("publication_date", "") or "")[:4] or "미상",
                "major_type": category,
                "type": category,
                "type_detail": "",
                "title": row.get("publication_title", "") or row.get("source_original_name", "") or "제목 없음",
                "extension": Path(row.get("local_path", "") or row.get("source_original_name", "")).suffix.lower().lstrip(".") or "미상",
                "size_bytes": as_int(row.get("file_size")) or 0,
                "verified_size_bytes": local_path.stat().st_size if local_path and local_path.is_file() else None,
                "status": row.get("status", "") or "미상",
                "page_count": measurement["page_count"] if measurement else None,
                "page_status": measurement["page_status"] if measurement else "미측정",
                "page_method": measurement["page_method"] if measurement else "미측정",
                "included_file_count": measurement["included_file_count"] if measurement else 1,
                "source_url": row.get("detail_url", "") or SOURCE_META["UOPKOFDA01_publications"]["url"],
            }
        )
    return documents


def aggregate(documents: list[dict[str, object]], dimensions: list[str]) -> list[dict[str, object]]:
    groups: dict[tuple[object, ...], dict[str, object]] = {}
    for document in documents:
        key = tuple(document[dimension] for dimension in dimensions)
        group = groups.setdefault(key, {dimension: document[dimension] for dimension in dimensions})
        group["file_count"] = int(group.get("file_count", 0)) + 1
        group["size_bytes"] = int(group.get("size_bytes", 0)) + int(document["size_bytes"])
        if document["verified_size_bytes"] is not None:
            group["verified_size_bytes"] = int(group.get("verified_size_bytes", 0)) + int(document["verified_size_bytes"])
        group["embedded_file_count"] = int(group.get("embedded_file_count", 0)) + int(document["included_file_count"])
        if document["page_count"] is not None:
            group["measured_file_count"] = int(group.get("measured_file_count", 0)) + 1
            group["page_count"] = int(group.get("page_count", 0)) + int(document["page_count"])
        else:
            group["unmeasured_file_count"] = int(group.get("unmeasured_file_count", 0)) + 1
    for group in groups.values():
        group.setdefault("measured_file_count", 0)
        group.setdefault("unmeasured_file_count", 0)
        group.setdefault("page_count", 0)
        group.setdefault("verified_size_bytes", 0)
        group["page_coverage_pct"] = round(group["measured_file_count"] / group["file_count"] * 100, 2)
    return sorted(groups.values(), key=lambda item: tuple(str(item[key]) for key in dimensions))


def final_page_totals() -> dict[str, dict[str, int]]:
    totals: dict[str, dict[str, int]] = {}
    for row in read_csv(FINAL_PAGES):
        corpus = row["corpus"]
        if corpus in SOURCE_META:
            totals[SOURCE_META[corpus]["id"]] = {
                "final_total_pages": as_int(row.get("total_pages_with_lossy_recovery")) or 0,
                "remaining_page_errors": as_int(row.get("remaining_errors_after_lossy")) or 0,
            }
    return totals


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    documents = build_documents()
    by_source = aggregate(documents, ["source_id", "source_name", "year_basis"])
    by_year = aggregate(documents, ["source_id", "source_name", "year_basis", "year"])
    by_type = aggregate(documents, ["source_id", "source_name", "major_type", "type"])
    by_extension = aggregate(documents, ["source_id", "source_name", "extension"])

    totals = final_page_totals()
    for item in by_source:
        expected = totals[item["source_id"]]
        item.update(expected)
        item["page_total_matches_final"] = item["page_count"] == expected["final_total_pages"]

    source_names = {item["source_id"]: item["source_name"] for item in by_source}
    summary = {
        "title": "열린재정 재정보고서·재정간행물 문서 분석",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": {
            "included_sources": list(SOURCE_META.values()),
            "excluded": ["OCR 결과", "원문 파일", "ZIP 압축 해제본"],
            "unit": "첨부 파일 1건을 1건으로 집계하며, ZIP은 내부 문서 페이지 수만 부모 파일에 합산합니다.",
        },
        "totals": {
            "file_count": len(documents),
            "measured_file_count": sum(1 for item in documents if item["page_count"] is not None),
            "unmeasured_file_count": sum(1 for item in documents if item["page_count"] is None),
            "page_count": sum(int(item["page_count"] or 0) for item in documents),
            "metadata_size_bytes": sum(int(item["size_bytes"]) for item in documents),
            "verified_size_bytes": sum(int(item["verified_size_bytes"] or 0) for item in documents),
            "embedded_file_count": sum(int(item["included_file_count"]) for item in documents),
        },
        "by_source": by_source,
        "by_year": by_year,
        "by_type": by_type,
        "by_extension": by_extension,
        "methodology": [
            "재정보고서 및 문서는 열린재정 UOPKOFDA03의 회계연도를 사용합니다.",
            "재정간행물은 열린재정 UOPKOFDA01의 게시일 연도를 사용합니다.",
            "PDF는 원본 PDF 페이지를, HWP/HWPX는 rhwp 렌더링 결과를, ZIP은 내부 PDF/HWP/HWPX 페이지 합계를 사용합니다.",
            "측정하지 못한 파일은 0쪽이 아니라 미측정으로 남깁니다. 파일 수와 페이지 수의 분모는 다를 수 있습니다.",
            "원본 용량은 생성 시점에 확보된 로컬 원본 파일의 논리적(stat) 크기를 합산합니다. 목록 메타데이터의 첨부 용량은 별도 값으로 보존합니다.",
        ],
        "sources": [
            {"id": identifier, "name": value["name"], "url": value["url"], "year_basis": value["year_basis"]}
            for identifier, value in ((value["id"], value) for value in SOURCE_META.values())
        ],
    }

    public_documents = [
        {key: document[key] for key in (
            "source_id", "source_name", "year_basis", "year", "major_type", "type", "title", "extension",
            "size_bytes", "verified_size_bytes", "status", "page_count", "page_status", "page_method", "included_file_count", "source_url",
        )}
        for document in documents
    ]
    write_csv(DATA / "documents.csv", public_documents, list(public_documents[0]))
    write_csv(DATA / "summary_by_year.csv", by_year, list(by_year[0]))
    write_csv(DATA / "summary_by_type.csv", by_type, list(by_type[0]))
    write_csv(DATA / "summary_by_extension.csv", by_extension, list(by_extension[0]))
    (DATA / "dashboard.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA / "README.md").write_text(
        "# 공개 데이터\n\n"
        "이 폴더에는 GitHub Pages용 집계 및 인벤토리만 있습니다. 원문, OCR 산출물, ZIP 해제 파일은 포함하지 않습니다.\n\n"
        "- `dashboard.json`: 화면용 전체·연도·유형·확장자 집계\n"
        "- `documents.csv`: 파일별 공개 인벤토리\n"
        "- `summary_by_year.csv`: 출처별 연도 집계\n"
        "- `summary_by_type.csv`: 출처별 유형 집계\n"
        "- `summary_by_extension.csv`: 출처별 파일 형식 집계\n",
        encoding="utf-8",
    )
    print(json.dumps({"documents": len(documents), "pages": summary["totals"]["page_count"], "by_source": by_source}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
