# 열린재정 문서 분석 GitHub Pages

`docs/`는 GitHub Pages 게시 루트입니다. 원문 파일, ZIP 해제본, OCR 결과는 포함하지 않고 재현 가능한 경량 집계와 인벤토리를 게시합니다. `type-examples/`에는 문서 내용 분석 대상 여부를 검토할 수 있는 유형별 대표 문서의 저해상도 발췌 페이지를 최대 3장 포함합니다.

## 생성

저장소 루트에서 다음을 실행합니다.

```bash
.venv/bin/python scripts/build_type_samples.py
python3 scripts/build_github_pages.py
python3 -m http.server 8000 --directory docs
```

그 후 `http://localhost:8000`에서 확인합니다.

## GitHub Pages

`.github/workflows/deploy-pages.yml`이 `main`의 `docs/`를 GitHub Actions로 배포합니다. 저장소 **Settings → Pages**의 Source는 **GitHub Actions**여야 합니다. 대용량 원문 폴더는 저장소에 커밋하지 않습니다.
