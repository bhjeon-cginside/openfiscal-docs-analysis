#!/usr/bin/env python3
"""Create one reviewable content-page sample for every Open Fiscal document type.

The published samples are low-resolution page images, not original documents.
They support a conservative type-level separation between narrative documents
that can enter content analysis and material that is primarily numeric tables.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import fitz


ROOT = Path(__file__).resolve().parents[1]
PAGE_COUNTS = ROOT / "page_count_analysis/document_page_counts.csv"
OUTPUT_DATA = ROOT / "docs/data/type_samples.json"
OUTPUT_ASSETS = ROOT / "docs/assets/type-samples"
RHWP = Path("/mnt/data/bhjeon/ocr-labs/rhwp-bin/v0.8.4/rhwp/rhwp")

SOURCE = {
    "UOPKOFDA03_report_documents": {"id": "reports", "name": "재정보고서 및 문서"},
    "UOPKOFDA01_publications": {"id": "publications", "name": "재정간행물"},
}

# These types are published chiefly as reusable numerical reference data.  They
# remain in the inventory but are excluded from *content* analysis; the sample
# page makes the decision auditable rather than silently removing them.
EXCLUDED_TYPE_REASONS = {
    ("UOPKOFDA01_publications", "주요재정통계"): "재정 통계표·시계열 중심 자료로, 원자료 조회 대상으로 분리",
    ("UOPKOFDA03_report_documents", "수지"): "통합재정수지 수치표 중심 자료로, 원자료 조회 대상으로 분리",
    ("UOPKOFDA03_report_documents", "결산>재정증권"): "월별 재정증권 발행계획 수치표 중심 자료로, 원자료 조회 대상으로 분리",
    ("UOPKOFDA03_report_documents", "지방재정"): "지방재정 연감·통합재정 수치표 중심 자료로, 원자료 조회 대상으로 분리",
    ("UOPKOFDA03_report_documents", "집행실적>복권"): "복권 판매·기금 집행 수치표 중심 자료로, 원자료 조회 대상으로 분리",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def as_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def asset_stem(corpus: str, category: str) -> str:
    digest = hashlib.sha256(f"{corpus}|{category}".encode()).hexdigest()[:12]
    return f"{SOURCE[corpus]['id']}-{digest}"


def page_indices(page_count: int) -> list[int]:
    # A short spread catches introductory prose, interior tables, and summary pages.
    raw = [0, 1, 2, 3, page_count // 4, page_count // 2, (page_count * 3) // 4]
    return sorted({index for index in raw if 0 <= index < page_count})


def text_metrics(text: str, drawing_count: int = 0) -> dict[str, float | int]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    letters = sum(character.isalpha() or "가" <= character <= "힣" for character in text)
    digits = sum(character.isdigit() for character in text)
    numeric_lines = sum(
        1
        for line in lines
        if sum(character.isdigit() for character in line) > sum(character.isalpha() or "가" <= character <= "힣" for character in line)
    )
    alpha_digit_total = letters + digits
    digit_ratio = digits / alpha_digit_total if alpha_digit_total else 1.0
    numeric_line_ratio = numeric_lines / len(lines) if lines else 1.0
    drawing_signal = min(drawing_count / 30, 1.0)
    table_score = min(1.0, digit_ratio * 0.52 + numeric_line_ratio * 0.34 + drawing_signal * 0.14)
    # Strong prose is useful for a human reviewer; numeric pages are deliberately
    # not preferred merely because they contain many characters.
    content_score = letters * (1 - table_score) - digits * 0.12
    return {
        "text_chars": len(re.sub(r"\s+", "", text)),
        "letters": letters,
        "digits": digits,
        "digit_ratio": round(digit_ratio, 3),
        "numeric_line_ratio": round(numeric_line_ratio, 3),
        "table_score": round(table_score, 3),
        "content_score": round(content_score, 1),
    }


def pdf_profile(row: dict[str, str]) -> dict[str, Any] | None:
    path = ROOT / row["path"]
    try:
        document = fitz.open(path)
        probes: list[dict[str, Any]] = []
        for index in page_indices(len(document)):
            page = document[index]
            metrics = text_metrics(page.get_text("text"), len(page.get_drawings()))
            probes.append({"page": index + 1, **metrics})
        if not probes:
            return None
        best = max(probes, key=lambda item: item["content_score"])
        profile = {
            "row": row,
            "page_count": len(document),
            "probes": probes,
            "best": best,
            "median_table_score": round(median(item["table_score"] for item in probes), 3),
            "median_content_score": round(median(item["content_score"] for item in probes), 1),
        }
        document.close()
        return profile
    except Exception:
        return None


def render_pdf(profile: dict[str, Any], page_info: dict[str, Any], target: Path) -> None:
    path = ROOT / profile["row"]["path"]
    document = fitz.open(path)
    page = document[page_info["page"] - 1]
    # 108 dpi is legible in an expanded browser view but deliberately not a
    # substitute for the original PDF.
    pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    target.write_bytes(pixmap.tobytes("jpeg", jpg_quality=78))
    document.close()


def hwp_profile(row: dict[str, str]) -> dict[str, Any] | None:
    if not RHWP.exists():
        return None
    path = ROOT / row["path"]
    try:
        command = [str(RHWP), "export-text", str(path), "-p", "1", "--json"]
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=90)
        payload = json.loads(result.stdout)
        page = payload["pages"][0]
        metrics = text_metrics(page.get("text", ""))
        return {
            "row": row,
            "page_count": as_int(payload.get("pageCount"), 1),
            "probes": [{"page": page.get("page", 1), **metrics}],
            "best": {"page": page.get("page", 1), **metrics},
            "median_table_score": metrics["table_score"],
            "median_content_score": metrics["content_score"],
        }
    except (subprocess.SubprocessError, json.JSONDecodeError, KeyError, OSError):
        return None


def render_hwp(profile: dict[str, Any], target: Path) -> bool:
    if not RHWP.exists():
        return False
    temporary = OUTPUT_ASSETS / f".tmp-{target.stem}"
    temporary.mkdir(parents=True, exist_ok=True)
    try:
        command = [
            str(RHWP), "export-svg", str(ROOT / profile["row"]["path"]),
            "-p", str(profile["best"]["page"] - 1), "-o", str(temporary), "--profile", "screen", "--json",
        ]
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
        result = next(temporary.glob("*.svg"), None)
        if result is None:
            return False
        target.write_bytes(result.read_bytes())
        return True
    except (subprocess.SubprocessError, OSError):
        return False
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def select_type(corpus: str, category: str, rows: list[dict[str, str]]) -> tuple[dict[str, Any] | None, str]:
    # Newer documents first; process only a small, diverse set for a type-level
    # profile rather than rendering all thousands of originals.
    rows = sorted(rows, key=lambda row: (as_int(row["fiscal_year"], -1), as_int(row["page_count"], -1)), reverse=True)
    pdf_rows = [row for row in rows if row["file_ext"] == "pdf" and row["page_status"] == "counted_pdf" and row["exists"] == "True"]
    profiles = [profile for row in pdf_rows[:4] if (profile := pdf_profile(row))]
    renderer = "pdf"
    if not profiles:
        hwp_rows = [row for row in rows if row["file_ext"] in {"hwp", "hwpx"} and row["exists"] == "True"]
        profiles = [profile for row in hwp_rows[:1] if (profile := hwp_profile(row))]
        renderer = "hwp"
    if not profiles:
        return None, renderer

    sample = max(profiles, key=lambda profile: profile["best"]["content_score"])
    type_table_score = median(profile["median_table_score"] for profile in profiles)
    type_content_score = median(profile["median_content_score"] for profile in profiles)
    sample["type_table_score"] = round(type_table_score, 3)
    sample["type_content_score"] = round(type_content_score, 1)
    sample["profile_document_count"] = len(profiles)
    return sample, renderer


def decision(corpus: str, category: str, profile: dict[str, Any]) -> tuple[str, str]:
    if reason := EXCLUDED_TYPE_REASONS.get((corpus, category)):
        return "excluded", reason
    return "included", "대표 페이지에서 서술형 내용이 확인되어 문서 내용 분석 대상으로 유지"


def representative_pages(profile: dict[str, Any], renderer: str, limit: int) -> list[dict[str, Any]]:
    """Choose a small, varied spread from one representative document.

    A cover or a single prose-rich page is insufficient for judging whether a
    type is really narrative.  The spread deliberately includes an early
    readable page, the strongest prose page, and a middle page, allowing the
    reviewer to see both explanatory and tabular portions where they exist.
    """
    if renderer == "hwp":
        return [profile["best"]]

    probes = profile["probes"]
    readable = [probe for probe in probes if probe["text_chars"] >= 100]
    early = min(readable or probes, key=lambda probe: probe["page"])
    middle = min(probes, key=lambda probe: abs(probe["page"] - (profile["page_count"] + 1) / 2))
    preferred = [early, profile["best"], middle]
    chosen: list[dict[str, Any]] = []
    seen_pages: set[int] = set()
    for probe in preferred + sorted(probes, key=lambda probe: probe["content_score"], reverse=True):
        if probe["page"] not in seen_pages:
            chosen.append(probe)
            seen_pages.add(probe["page"])
        if len(chosen) == limit:
            break
    return chosen


def alternative_format_profiles(
    rows: list[dict[str, str]], primary_profile: dict[str, Any],
) -> list[tuple[dict[str, Any], str]]:
    """Return one renderable HWP/HWPX document for each available format.

    PDFs remain the most common source representation, but showing only PDF
    makes it impossible to judge whether equivalent Hangul-format material is
    substantive.  Reserve a page for each locally available HWP/HWPX format
    whenever the type also contains PDF files.
    """
    alternatives: list[tuple[dict[str, Any], str]] = []
    for extension in ("hwp", "hwpx"):
        if primary_profile["row"]["file_ext"] == extension:
            continue
        candidates = sorted(
            (row for row in rows if row["file_ext"] == extension),
            key=lambda row: (as_int(row["fiscal_year"], -1), as_int(row["page_count"], -1)),
            reverse=True,
        )
        for row in candidates[:4]:
            if profile := hwp_profile(row):
                alternatives.append((profile, "hwp"))
                break
    return alternatives


def main() -> None:
    OUTPUT_ASSETS.mkdir(parents=True, exist_ok=True)
    rows = [
        row for row in read_csv(PAGE_COUNTS)
        if row["corpus"] in SOURCE and row["exists"] == "True"
    ]
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["corpus"], row["category"] or "미분류")].append(row)

    samples: list[dict[str, Any]] = []
    used_assets: set[str] = set()
    for (corpus, category), type_rows in sorted(grouped.items(), key=lambda item: (SOURCE[item[0][0]]["id"], item[0][1])):
        profile, renderer = select_type(corpus, category, type_rows)
        if profile is None:
            samples.append({
                "id": asset_stem(corpus, category), "source_id": SOURCE[corpus]["id"], "source_name": SOURCE[corpus]["name"],
                "type": category, "status": "review_required", "reason": "렌더링 가능한 대표 문서를 자동 선정하지 못해 수동 검토 필요",
            })
            continue
        alternatives = alternative_format_profiles(type_rows, profile)
        selected_profiles = [(profile, renderer, max(1, 5 - len(alternatives)))] + [
            (alternative, alternative_renderer, 1) for alternative, alternative_renderer in alternatives
        ]
        page_assets: list[dict[str, Any]] = []
        documents: list[dict[str, Any]] = []
        for selected_profile, selected_renderer, limit in selected_profiles:
            selected_row = selected_profile["row"]
            documents.append({
                "title": selected_row["title"], "year": selected_row["fiscal_year"],
                "extension": selected_row["file_ext"], "document_pages": selected_profile["page_count"],
            })
            for page_info in representative_pages(selected_profile, selected_renderer, limit):
                asset_extension = ".jpg" if selected_renderer == "pdf" else ".svg"
                asset_name = f"{asset_stem(corpus, category)}-{selected_row['file_ext']}-p{page_info['page']}{asset_extension}"
                target = OUTPUT_ASSETS / asset_name
                if selected_renderer == "pdf":
                    render_pdf(selected_profile, page_info, target)
                elif not render_hwp(selected_profile, target):
                    samples.append({
                        "id": asset_stem(corpus, category), "source_id": SOURCE[corpus]["id"], "source_name": SOURCE[corpus]["name"],
                        "type": category, "status": "review_required", "reason": "HWP/HWPX 대표 페이지 렌더링에 실패해 수동 검토 필요",
                    })
                    page_assets = []
                    break
                used_assets.add(asset_name)
                page_assets.append({
                    "page": page_info["page"], "image": f"../assets/type-samples/{asset_name}",
                    "title": selected_row["title"], "year": selected_row["fiscal_year"],
                    "extension": selected_row["file_ext"], "text_chars": page_info["text_chars"],
                    "digit_ratio": page_info["digit_ratio"], "table_score": page_info["table_score"],
                })
            if not page_assets:
                break
        if not page_assets:
            continue
        status, reason = decision(corpus, category, profile)
        samples.append({
            "id": asset_stem(corpus, category),
            "source_id": SOURCE[corpus]["id"], "source_name": SOURCE[corpus]["name"], "type": category,
            "status": status, "reason": reason,
            "sample": {
                "documents": documents, "pages": page_assets,
            },
            "type_profile": {
                "sampled_documents": profile["profile_document_count"],
                "table_score": profile["type_table_score"], "content_score": profile["type_content_score"],
            },
        })

    for stale in OUTPUT_ASSETS.iterdir():
        if stale.is_file() and stale.name not in used_assets:
            stale.unlink()
    output = {
        "title": "유형별 내용 예시 및 분석 적합성",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "methodology": [
            "유형별 최근 원본 문서 최대 4건에서 여러 페이지를 표본 추출했습니다.",
            "각 유형은 대표 문서에서 앞부분·서술형·중간 부분 등 최대 5쪽을 저해상도로 발췌합니다.",
            "PDF와 HWP/HWPX가 함께 있는 유형은 렌더링 가능한 각 형식에서 대표 페이지를 포함해 형식 편향을 줄입니다.",
            "제외 유형은 대표 페이지와 자료 성격을 함께 검토해 정했으며, 숫자·표 중심 원자료는 별도 데이터 조회 대상으로 분리합니다.",
            "제외된 유형도 전체 인벤토리에는 남으며, 문서 내용 분석 대상에서만 분리합니다.",
        ],
        "summary": {
            "type_count": len(samples),
            "included": sum(item["status"] == "included" for item in samples),
            "excluded": sum(item["status"] == "excluded" for item in samples),
            "review_required": sum(item["status"] == "review_required" for item in samples),
        },
        "samples": samples,
    }
    OUTPUT_DATA.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DATA.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
