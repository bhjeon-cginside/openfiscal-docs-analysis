#!/usr/bin/env python3
"""Build classification/data-name review units without changing source manifests.

Uses only the tracked report manifest, existing legacy samples and local originals.
Missing previews remain visible; no broad legacy exclusion decision is inherited.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

import build_type_samples as renderer

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "openfiscal_report_documents/lists/manifest.csv"
FILES_ROOT = ROOT / "openfiscal_report_documents/files"
OUTPUT = ROOT / "docs/data/report_review_samples.json"
ASSETS = ROOT / "docs/assets/report-review"
SOURCE_URL = "https://www.openfiscaldata.go.kr/op/ko/fd/UOPKOFDA03"


def classification(path: str) -> dict[str, str]:
    parts = [part.strip() for part in path.split(">")]
    if len(parts) > 3:
        raise ValueError(f"Unexpected classification depth: {path}")
    parts += [""] * (3 - len(parts))
    return dict(zip(("large", "middle", "small"), parts))


def group_key(row: dict[str, str]) -> tuple[str, str, str]:
    return row["allDtaClsNm"], row["odtId"], row["odtNm"]


def stable_id(parts: tuple[str, ...]) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:16]


def attachment_id(row: dict[str, str]) -> str:
    return f"{row['atchFileId']}:{row['atchFileSeq']}"


def current_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("source_in_current_list", "").lower() != "false"]


def resolve_source_path(dest_path: str) -> Path:
    relative = Path(dest_path)
    root = FILES_ROOT.resolve()
    source = (root / relative).resolve()
    if relative.is_absolute() or not source.is_relative_to(root):
        raise ValueError(f"Source path escapes report files directory: {dest_path!r}")
    return source


def legacy_previews() -> dict[str, dict]:
    result = {}
    legacy = json.loads((ROOT / "docs/data/type_samples.json").read_text())
    for sample in legacy["samples"]:
        if sample["source_id"] != "reports":
            continue
        for document in sample.get("sample", {}).get("documents", []):
            pages = document.get("pages", [])
            if pages:
                # Existing asset names embed sha256(source relative path)[:10].
                source_hash = Path(pages[0]["image"]).name.split("-")[2]
                if all((ROOT / "docs/type-examples" / page["image"]).is_file() for page in pages):
                    result[source_hash] = document
    return result


def make_document(row: dict[str, str], cache: dict[str, dict], legacy: dict[str, dict]) -> dict | None:
    source = resolve_source_path(row["dest_path"])
    path = source.relative_to(ROOT)
    if not source.is_file():
        return None
    identity = attachment_id(row)
    fingerprint = f"{source.stat().st_size}:{source.stat().st_mtime_ns}"
    metadata = {
        "id": identity, "title": row["dpFileNm"], "year": row["acntYr"],
        "extension": row["fileExt"].lower(), "source_fingerprint": fingerprint,
    }
    cached = cache.get(identity)
    if cached and cached.get("source_fingerprint") == fingerprint:
        if all((ROOT / "docs/type-examples" / p["image"]).is_file() for p in cached["pages"]):
            return {**cached, **metadata}
    old = legacy.get(hashlib.sha256(str(path).encode()).hexdigest()[:10])
    if old and old["title"] == row["dpFileNm"] and str(old["year"]) == row["acntYr"]:
        return {**old, **metadata}
    render_row = {
        "path": str(path), "file_ext": row["fileExt"].lower(),
        "page_status": "counted_pdf", "fiscal_year": row["acntYr"],
        "title": row["dpFileNm"], "page_count": "",
    }
    selected = renderer.profile_for_row(render_row)
    if selected is None:
        return None
    profile, method = selected
    pages = []
    for probe in renderer.representative_pages(profile, method, limit=6):
        suffix = "jpg" if method == "pdf" else "svg"
        name = f"{stable_id((identity, fingerprint))}-p{probe['page']}.{suffix}"
        target = ASSETS / name
        if method == "pdf":
            renderer.render_pdf(profile, probe, target)
        elif not renderer.render_hwp(profile, probe, target):
            return None
        pages.append({"page": probe["page"], "image": f"../assets/report-review/{name}"})
    return {**metadata, "document_pages": profile["page_count"], "pages": pages} if pages else None


def select_documents(rows: list[dict[str, str]], cache: dict[str, dict], legacy: dict[str, dict]) -> list[dict]:
    ordered = sorted(rows, key=lambda row: (renderer.as_int(row["acntYr"]), row["dpFileNm"], attachment_id(row)), reverse=True)
    documents = []
    attempted = set()
    # At most two source documents per review unit, with format diversity first.
    # Bound fallback attempts so corrupt files cannot cause an unbounded render run.
    for extension in ("pdf", "hwp", "hwpx", None):
        if len(documents) == 2:
            break
        candidates = [r for r in ordered if (extension is None or r["fileExt"].lower() == extension)
                      and r["fileExt"].lower() in {"pdf", "hwp", "hwpx"} and attachment_id(r) not in attempted]
        for row in candidates[:4]:
            attempted.add(attachment_id(row))
            if document := make_document(row, cache, legacy):
                documents.append(document)
                break
    return documents


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-only", action="store_true", help="Build groups without rendering previews")
    args = parser.parse_args()
    rows = renderer.read_csv(MANIFEST)
    active = current_rows(rows)
    grouped = defaultdict(list)
    for row in active:
        grouped[group_key(row)].append(row)
    cache = {}
    if OUTPUT.exists():
        previous = json.loads(OUTPUT.read_text())
        cache = {doc["id"]: doc for group in previous["groups"] for doc in group["documents"]}
    legacy = legacy_previews()
    ASSETS.mkdir(parents=True, exist_ok=True)
    groups = []
    for index, (key, members) in enumerate(sorted(grouped.items()), 1):
        path, odt_id, name = key
        documents = [] if args.metadata_only else select_documents(members, cache, legacy)
        group = {
            "id": stable_id(key), "classification": classification(path),
            "classification_path": path, "odt_id": odt_id, "data_name": name,
            "file_count": len(members), "years": sorted({r["acntYr"] for r in members}),
            "extensions": sorted({r["fileExt"].lower() for r in members}), "documents": documents,
            "no_preview_reason": "" if documents else "미리보기 미생성: ZIP 전용·원본 미확보·렌더링 실패 여부를 원문에서 확인하세요. 제외 판정이 아닙니다.",
            "source_url": SOURCE_URL + "?" + urlencode({"odtNm": name}),
        }
        groups.append(group)
        print(f"[{index}/{len(grouped)}] {path} / {name}: {len(documents)} samples", flush=True)
    output = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_checked_at": max((r.get("last_checked_at", "") for r in active), default=""),
        "source_url": SOURCE_URL,
        "summary": {"file_count": len(active), "group_count": len(groups),
                    "groups_with_samples": sum(bool(g["documents"]) for g in groups),
                    "representative_documents": sum(len(g["documents"]) for g in groups),
                    "omitted_historical_files": len(rows) - len(active)},
        "groups": groups,
    }
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps(output["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
