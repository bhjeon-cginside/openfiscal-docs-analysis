# 열린재정 문서 분석 GitHub Pages

`docs/`는 GitHub Pages 게시 루트입니다. 원문 파일, ZIP 해제본, OCR 결과는 포함하지 않고 재현 가능한 경량 집계와 인벤토리만 게시합니다.

## 생성

저장소 루트에서 다음을 실행합니다.

```bash
python3 scripts/build_github_pages.py
python3 -m http.server 8000 --directory docs
```

그 후 `http://localhost:8000`에서 확인합니다.

## GitHub Pages

GitHub 저장소 **Settings → Pages → Deploy from a branch**에서 배포 브랜치와 `/docs` 폴더를 선택합니다. 대용량 원문 폴더는 저장소에 커밋하지 않습니다.
