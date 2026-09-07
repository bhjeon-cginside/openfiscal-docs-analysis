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

## 갱신 및 로컬 확인

```bash
.venv/bin/python scripts/build_type_samples.py
python3 scripts/build_github_pages.py
python3 -m http.server 8000 --directory docs
```

브라우저에서 `http://localhost:8000`을 열어 확인합니다.

## GitHub Pages 배포

`.github/workflows/deploy-pages.yml`은 `main` 브랜치에 push될 때 `docs/`를 GitHub Pages에 배포합니다. 저장소 **Settings → Pages**에서 Source를 **GitHub Actions**로 한 번 설정하면 됩니다.
