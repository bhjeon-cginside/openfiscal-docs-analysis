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
import tempfile
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


def document_stem(row: dict[str, str]) -> str:
    return hashlib.sha256(row["path"].encode()).hexdigest()[:10]


def page_indices(page_count: int) -> list[int]:
    """Return up to ten evenly distributed source-page indices."""
    target = min(10, page_count)
    if target <= 1:
        return [0] if page_count else []
    return [round(position * (page_count - 1) / (target - 1)) for position in range(target)]


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


def hwp_page_count(path: Path) -> int:
    """Read the actual HWP/HWPX page count from the renderer.

    `export-text -p N` reports a one-page response even for a multi-page
    document because it describes the requested page, not the source file.
    The SVG renderer returns the source's real pageCount.
    """
    with tempfile.TemporaryDirectory(prefix="openfiscal-hwp-pages-") as temporary:
        command = [
            str(RHWP), "export-svg", str(path), "-p", "0", "-o", temporary,
            "--profile", "screen", "--json",
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
        return max(1, as_int(json.loads(result.stdout).get("pageCount"), 1))


def hwp_profile(row: dict[str, str]) -> dict[str, Any] | None:
    if not RHWP.exists():
        return None
    path = ROOT / row["path"]
    try:
        page_count = hwp_page_count(path)
        probes: list[dict[str, Any]] = []
        for index in page_indices(page_count):
            command = [str(RHWP), "export-text", str(path), "-p", str(index), "--json"]
            result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=90)
            payload = json.loads(result.stdout)
            page = payload["pages"][0]
            probes.append({"page": index + 1, **text_metrics(page.get("text", ""))})
        if not probes:
            return None
        best = max(probes, key=lambda item: item["content_score"])
        return {
            "row": row,
            "page_count": page_count,
            "probes": probes,
            "best": best,
            "median_table_score": round(median(item["table_score"] for item in probes), 3),
            "median_content_score": round(median(item["content_score"] for item in probes), 1),
        }
    except (subprocess.SubprocessError, json.JSONDecodeError, KeyError, OSError):
        return None


def render_hwp(profile: dict[str, Any], page_info: dict[str, Any], target: Path) -> bool:
    if not RHWP.exists():
        return False
    temporary = OUTPUT_ASSETS / f".tmp-{target.stem}"
    temporary.mkdir(parents=True, exist_ok=True)
    try:
        command = [
            str(RHWP), "export-svg", str(ROOT / profile["row"]["path"]),
            "-p", str(page_info["page"] - 1), "-o", str(temporary), "--profile", "screen", "--json",
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


def profile_for_row(row: dict[str, str]) -> tuple[dict[str, Any], str] | None:
    if row["file_ext"] == "pdf" and row["page_status"] == "counted_pdf":
        if profile := pdf_profile(row):
            return profile, "pdf"
    if row["file_ext"] in {"hwp", "hwpx"}:
        if profile := hwp_profile(row):
            return profile, "hwp"
    return None


def select_type_documents(rows: list[dict[str, str]], limit: int = 3) -> list[tuple[dict[str, Any], str]]:
    """Select up to three representative source documents for one type.

    Prefer one renderable document per available PDF/HWP/HWPX format, then
    fill remaining positions by recency. This exposes variation between files
    while preventing a large type from dominating the static review page.
    """
    ordered = sorted(rows, key=lambda row: (as_int(row["fiscal_year"], -1), as_int(row["page_count"], -1)), reverse=True)
    selected: list[tuple[dict[str, Any], str]] = []
    selected_paths: set[str] = set()

    def add_first(candidates: list[dict[str, str]]) -> None:
        for candidate in candidates:
            if candidate["path"] in selected_paths:
                continue
            if selection := profile_for_row(candidate):
                selected.append(selection)
                selected_paths.add(candidate["path"])
                return

    for extension in ("pdf", "hwp", "hwpx"):
        if len(selected) == limit:
            break
        add_first([row for row in ordered if row["file_ext"] == extension])
    for row in ordered:
        if len(selected) == limit:
            break
        add_first([row])
    return selected


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
        selected_profiles = select_type_documents(type_rows)
        if not selected_profiles:
            samples.append({
                "id": asset_stem(corpus, category), "source_id": SOURCE[corpus]["id"], "source_name": SOURCE[corpus]["name"],
                "type": category, "status": "review_required", "reason": "렌더링 가능한 대표 문서를 자동 선정하지 못해 수동 검토 필요",
            })
            continue
        documents: list[dict[str, Any]] = []
        for selected_profile, selected_renderer in selected_profiles:
            selected_row = selected_profile["row"]
            document_pages: list[dict[str, Any]] = []
            document_render_failed = False
            for page_info in representative_pages(selected_profile, selected_renderer, limit=10):
                asset_extension = ".jpg" if selected_renderer == "pdf" else ".svg"
                asset_name = f"{asset_stem(corpus, category)}-{document_stem(selected_row)}-{selected_row['file_ext']}-p{page_info['page']}{asset_extension}"
                target = OUTPUT_ASSETS / asset_name
                if selected_renderer == "pdf":
                    render_pdf(selected_profile, page_info, target)
                elif not render_hwp(selected_profile, page_info, target):
                    document_render_failed = True
                    break
                used_assets.add(asset_name)
                document_pages.append({
                    "page": page_info["page"], "image": f"../assets/type-samples/{asset_name}",
                    "text_chars": page_info["text_chars"], "digit_ratio": page_info["digit_ratio"],
                    "table_score": page_info["table_score"],
                })
            if document_render_failed or not document_pages:
                continue
            documents.append({
                "title": selected_row["title"], "year": selected_row["fiscal_year"],
                "extension": selected_row["file_ext"], "document_pages": selected_profile["page_count"], "pages": document_pages,
            })
        if not documents:
            samples.append({
                "id": asset_stem(corpus, category), "source_id": SOURCE[corpus]["id"], "source_name": SOURCE[corpus]["name"],
                "type": category, "status": "review_required", "reason": "대표 문서 페이지 렌더링에 실패해 수동 검토 필요",
            })
            continue
        primary_profile = selected_profiles[0][0]
        status, reason = decision(corpus, category, primary_profile)
        type_table_score = median(profile["median_table_score"] for profile, _ in selected_profiles)
        type_content_score = median(profile["median_content_score"] for profile, _ in selected_profiles)
        samples.append({
            "id": asset_stem(corpus, category),
            "source_id": SOURCE[corpus]["id"], "source_name": SOURCE[corpus]["name"], "type": category,
            "status": status, "reason": reason,
            "sample": {
                "documents": documents,
            },
            "type_profile": {
                "sampled_documents": len(documents),
                "table_score": round(type_table_score, 3), "content_score": round(type_content_score, 1),
            },
        })

    for stale in OUTPUT_ASSETS.iterdir():
        if stale.is_file() and stale.name not in used_assets:
            stale.unlink()
    output = {
        "title": "유형별 내용 예시 및 분석 적합성",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "methodology": [
            "각 유형에서 최근성과 형식 다양성을 고려해 대표 원본 문서를 최대 3건 선정했습니다.",
            "선정된 각 문서에서 앞부분·서술형·중간 부분 등 최대 10쪽을 저해상도로 발췌합니다.",
            "PDF와 HWP/HWPX가 함께 있는 유형은 가능한 한 각 형식의 대표 문서를 포함해 형식 편향을 줄입니다.",
            "제외 유형은 대표 페이지와 자료 성격을 함께 검토해 정했으며, 숫자·표 중심 원자료는 별도 데이터 조회 대상으로 분리합니다.",
            "제외된 유형도 전체 인벤토리에는 남으며, 문서 내용 분석 대상에서만 분리합니다.",
        ],
        "summary": {
            "type_count": len(samples),
            "included": sum(item["status"] == "included" for item in samples),
            "excluded": sum(item["status"] == "excluded" for item in samples),
            "review_required": sum(item["status"] == "review_required" for item in samples),
            "representative_documents": sum(len(item.get("sample", {}).get("documents", [])) for item in samples),
        },
        "samples": samples,
    }
    OUTPUT_DATA.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DATA.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
