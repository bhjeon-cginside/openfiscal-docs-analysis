# 열린재정 문서 분석

열린재정의 **재정보고서 및 문서**와 **재정간행물**을 파일 단위로 집계한 GitHub Pages 정적 사이트입니다. 연도별·유형별 파일 수, 파일 형식, 파일 용량, 측정된 페이지 수를 공개합니다.

- 사이트 루트: [`docs/index.html`](docs/index.html)
- 유형별 대표 페이지·분석 대상: [`docs/type-examples/`](docs/type-examples/)
- 공개 데이터: [`docs/data/`](docs/data/)
- 재현 스크립트: [`scripts/build_github_pages.py`](scripts/build_github_pages.py)

## 범위와 집계 기준

| 구분 | 원천 | 연도 기준 | 파일 수 | 측정 페이지 |
|---|---|---|---:|---:|
| 재정보고서 및 문서 | `UOPKOFDA03` | 회계연도 | 7,103 | 1,923,525쪽 |
| 재정간행물 | `UOPKOFDA01` | 게시연도 | 1,698 | 367,977쪽 |
| 합계 | 두 공개 목록 | 출처별 기준 유지 | 8,801 | 2,291,502쪽 |

페이지 수는 PDF 직접 측정, HWP/HWPX 렌더링, ZIP 내부 파일의 페이지 합산으로 산출합니다. 측정 실패·첨부 없음 파일은 0쪽으로 처리하지 않고 `미측정`으로 남깁니다.

원본 파일 용량은 수집 시점에 실제 확보된 원본의 논리적 파일 크기(`stat`)를 합산합니다. 현재 확보본은 **65,174,584,524 bytes (65.2 GB)**이며, 열린재정 목록 메타데이터상 첨부 용량 합계 **65,671,361,582 bytes (65.7 GB)**와는 496,777,058 bytes 차이가 있습니다. 이 차이에는 원본 미확보 6건과 일부 출처 메타데이터 크기 불일치가 포함됩니다.

이 저장소의 Pages 산출물에는 원문 파일, ZIP 해제본, OCR 결과를 포함하지 않습니다. 원문은 열린재정의 [재정보고서 및 문서](https://www.openfiscaldata.go.kr/op/ko/fd/UOPKOFDA03) 및 [재정간행물](https://www.openfiscaldata.go.kr/op/ko/fd/UOPKOFDA01)에서 확인할 수 있습니다.

문서 내용을 분석할 유형을 검토할 수 있도록 유형별 대표 문서를 최대 3건, 문서당 저해상도 페이지를 최대 10장 게시합니다. 앞부분·서술형·중간 부분을 함께 보여 주어 한 장만으로 판단하는 한계를 줄이고, PDF와 HWP/HWPX가 함께 있는 유형은 가능한 한 각 형식의 대표 문서를 포함합니다. 수지·통계·발행계획처럼 표와 수치가 주된 유형은 인벤토리에서는 유지하되, 원자료 조회가 더 적합하므로 문서 내용 분석 대상에서만 분리합니다. 대표 페이지 생성에는 PDF 렌더러와 로컬 HWP 도구가 필요합니다.

## 분류별 보고서 검토

[`docs/type-examples/`](docs/type-examples/)에서는 재정보고서 및 문서를
**대분류 → 중분류 → 소분류 → 재정데이터명**으로 좁혀 대표 페이지를 검토합니다.
분류는 원천 `allDtaClsNm`의 각 단계, 재정데이터명은 `odtNm`입니다.
소분류가 없는 자료는 `해당 없음`으로 유지하며, 동일 이름이라도 `odtId`가 다르면
별도 검토 단위로 표시합니다. 재정간행물은 별도 유형별 검토·제외 목록으로 분리합니다.
각 카드의 열린재정 링크는 재정데이터명 검색입니다. 원천 사이트에서는 동명의 다른
`odtId` 자료도 함께 나올 수 있으므로 정확한 검토 단위는 카드·CSV의 분류와 ID로 확인합니다.

- 새 보고서 검토 단위에는 기존 유형별 제외 결정을 상속하지 않습니다.
- 각 카드의 **이 그룹 전체 제외** 체크와 제외 사유를 현재 브라우저에 자동 저장합니다.
  체크는 대표 문서 한 건이 아니라 분류·재정데이터 ID로 구분한 그룹 전체에 적용됩니다.
  미체크는 포함 확정이 아닙니다. 원천 목록이나 다른 사용자의 화면은 바뀌지 않습니다.
- **최종 제외 CSV**는 필터·현재 페이지와 관계없이 제외 선택한 모든 현재 그룹을 내보냅니다.
  **검토 목록 CSV**는 현재 필터 결과와 그 선택 상태·사유를 내보냅니다.
  두 파일 모두 그룹 ID, 분류, 재정데이터 ID·이름, 파일 수와 사유를 포함합니다.
- **일괄 선택 · 백업 / 복원**에서 필터 결과 전체(다른 페이지 포함)를 선택·해제할 수 있습니다.
  소분류 필터 후 일괄 선택하면 그 소분류를 제외 대상으로 묶어 검토할 수 있습니다.
  이름이 같은 두 ID를 함께 처리하려면 해당 재정데이터명으로 검색 후 일괄 선택합니다.
- 선택은 `localStorage`에 저장됩니다. 기기·브라우저 간 자동 공유되지 않으며 브라우저 데이터
  삭제·시크릿 모드 종료 시 사라질 수 있습니다. **JSON 백업/복원**으로 수동 이동·보관하세요.
  복원은 형식 검증 후 기존 선택을 교체하며, 초기화는 확인 후 모든 선택과 사유를 삭제합니다.
- 저장이 차단되거나 기존 저장 자료가 손상되면 경고하고 현재 탭에서만 계속 작업합니다.
  읽지 못한 저장값을 자동으로 덮어쓰지 않습니다. 창을 닫기 전에 CSV/JSON을 저장하세요.
  현재 목록에 없는 과거 선택은 경고하고 JSON 백업에 보존하되 최종 CSV에서는 제외합니다.
- **사용자 지정 제외(2026-09-21):** 지출구조조정 1건, 지방재정연감(결산) 5건,
  지방재정연감(예산) 5건 — 총 3개 그룹·ZIP 첨부 11건입니다. 이 결정은
  `docs/data/report_exclusion_decisions.json`에 정확한 분류·재정데이터 ID로 기록하며,
  [`report_exclusions.csv`](docs/data/report_exclusions.csv)로도 제공합니다.
  배포 후 처음 방문할 때 이 3개 그룹만 저장된 선택에 병합합니다. 다른 선택은 유지하고,
  적용 이후 사용자가 해제·초기화하거나 백업을 복원한 결과를 반복해서 덮어쓰지 않습니다.
  미리보기 없음만으로 다른 그룹을 자동 제외하지는 않습니다.
- 원본 목록에서 `source_in_current_list=False`인 과거 첨부는 이 검토 화면에서만 제외합니다.
  전체 인벤토리와 검토 화면의 목록 기준일·집계 범위는 다를 수 있습니다.
- 단위별 대표 원문은 최대 2건입니다. 신규 샘플은 최대 6쪽, 재사용한 기존 샘플은
  최대 10쪽입니다. ZIP 전용 자료·원본 미확보·렌더링 실패는 미리보기 없음으로
  표시하며, 이를 보고서 제외 판정으로 해석하지 않습니다.
- 재생성은 원본이 확보된 로컬 환경에서 수행합니다. 기존 PDF/HWP 렌더러를 재사용하고,
  원문 대신 `docs/data/report_review_samples.json`과 `docs/assets/report-review/`만 게시합니다.

```bash
.venv/bin/python scripts/build_report_review_samples.py
.venv/bin/python -m unittest discover -s tests -v
```

기존 유형 샘플을 재생성해 기존 이미지가 바뀐 경우, 위 분류별 샘플 생성기도 다시 실행합니다.
브라우저 회귀검증은 `tests/test_report_review_browser.cjs`를 사용합니다
(`PLAYWRIGHT_MODULE`, `CHROMIUM_PATH`, `REVIEW_BASE_URL`로 설치된 도구·로컬 서버 지정).
제외 선택·저장·CSV·JSON 복원 검증은 `tests/test_report_exclusions_browser.cjs`를 사용합니다.

## 재정간행물 검토 및 제외 목록

같은 페이지의 **재정간행물 유형** 탭에서 유형·대표 문서명으로 검색하고,
대표 문서 탭과 페이지 확대를 확인한 뒤 **이 유형 전체 제외**를 선택합니다.
현재 공개 인벤토리 기준 **15개 유형·목록 1,698행(첨부 1,695건 + 첨부 없는 게시물 3건)·대표 문서 43건**입니다.
보고서의 대·중·소분류나 `odt_id`는 간행물에 임의로 부여하지 않습니다.

- 기존 자동 분석의 포함·제외 판정은 초기 선택으로 가져오지 않습니다.
- 체크와 사유는 간행물 유형 전체에 적용합니다. ZIP은 첨부 1건이며 내부 파일을 별도 집계하지 않습니다.
- 선택 상태 필터, 전체 필터 결과 일괄 선택/해제, 최종 제외 CSV, 검토 목록 CSV,
  JSON 백업/복원, 확인 후 초기화를 보고서와 동일하게 지원합니다.
- **보고서와 간행물은 저장 키·백업 형식·내보내기 파일이 분리됩니다.** 현재 자료의
  초기화나 복원은 다른 자료에 영향을 주지 않습니다. 다른 종류의 JSON 복원은 거부합니다.
- 기존 보고서 저장 키 `openfiscal-docs-analysis:report-exclusions:v1`과 백업 형식은 유지합니다.
  간행물은 `openfiscal-docs-analysis:publication-exclusions:v1`을 사용합니다.
- 인벤토리 생성일은 2026-08-25, 대표 샘플 생성일은 2026-09-07입니다.
  새 검토 JSON 생성일은 원천 사이트의 최신 조회일을 뜻하지 않습니다.
- 간행물 CSV 컬럼: `group_id,type,category_code,record_count,file_count,no_attachment_count,years,extensions,exclusion_decision,exclusion_reason`.
  개별 원본이 아닌 유형별 목록입니다. 최종 제외 CSV는 현재 필터와 무관하게 모든 선택을 포함합니다.

간행물 유형은 서버의 **`ofdBrdiDtsClsCd`**로 구분됩니다. 공통코드 API
`POST /op/ko/cm/selectItgCdList.do`의 `itgClsCd=OP061`, `uprItgDtsCd=05` 응답
`itgDtsCd`/`itgDtsCdNm`이 코드/명칭입니다. 예: `501` 월간재정동향,
`504` 주요재정통계, `509` IMF, `516` 월간나라재정. 2026-09-23 서버 응답에서
기존 15개 코드 매핑을 재확인했으며, 전체 게시물 목록을 새로 수집한 것은 아닙니다.
보고서 `odtId`나 화면 내부의 `publications-...` 샘플 ID와는 다른 값입니다.
기존 내부 ID를 유지하여 코드 표시 추가가 저장된 선택을 바꾸지 않습니다.

**[재정간행물 전체 목록 Excel](docs/data/publication_full_list.xlsx)**에는
전체 목록·유형코드표·작성 기준을 별도 시트로 제공합니다. 첨부 없는 3건도 비고로
명시하며, 현재 수집 인벤토리 전체를 보존합니다. 표지 제외·원문 우선 수집 기준이므로
사이트의 모든 표지·목차 파일 목록이나 개인 브라우저의 제외 결과와는 다릅니다.

기존 인벤토리와 대표 이미지로 재생성하며 원문 재다운로드나 렌더링은 필요하지 않습니다.

```bash
.venv/bin/python scripts/build_publication_review_samples.py
.venv/bin/python scripts/export_publication_list.py
.venv/bin/python -m unittest discover -s tests -v
# docs/ 로컬 서버와 설치된 Playwright를 지정한 뒤 실행
node tests/test_publication_exclusions_browser.cjs
```

## 갱신 및 로컬 확인

```bash
.venv/bin/python scripts/build_type_samples.py
python3 scripts/build_github_pages.py
.venv/bin/python scripts/build_publication_review_samples.py
python3 -m http.server 8000 --directory docs
```

브라우저에서 `http://localhost:8000`을 열어 확인합니다.

## GitHub Pages 배포

`.github/workflows/deploy-pages.yml`은 `main` 브랜치에 push될 때 `docs/`를 GitHub Pages에 배포합니다. 저장소 **Settings → Pages**에서 Source를 **GitHub Actions**로 한 번 설정하면 됩니다.
