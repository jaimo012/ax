# AX 성과 노트

AI 도입 성과(AX)를 어떻게 재고 설명할지에 대한 글을 연재하는 정적 사이트입니다.
배포 주소: https://jaimo012.github.io/ax/

AI 검색(ChatGPT·Perplexity·Gemini·Claude)이 읽고 인용하기 좋게 만드는 것이 목적입니다(GEO).
그래서 모든 본문·목록·개념 정의는 빌드할 때 HTML로 완성되고, 페이지에 JavaScript가 없습니다.

## 구조

```
posts/                     발행 원고 .md (파일명: YYYY-MM-DD-slug.md)
concepts.yml               개념 사전
site.yml                   사이트 설정 (사이트명·설명·저자명·연락 메일)
templates/                 Jinja2 템플릿 (base·post·index·glossary·404)
static/style.css           스타일
build.py                   원고 읽기·검증 → 페이지 생성 → _site/
scripts/site_model.py      공용 모델 (경로·URL·글 데이터)
scripts/md_ext.py          마크다운 확장 (수식 블록·그림 캡션·alt 검사)
scripts/render_pages.py    HTML 페이지 생성
scripts/site_extras.py     JSON-LD · sitemap.xml · feed.xml · llms.txt
scripts/verify_site.py     산출물 자기검사
scripts/check_banned.py    금지어 검사
hooks/pre-commit           커밋 전 금지어 검사 훅
.github/workflows/deploy.yml  main 에 푸시하면 검사 → 빌드 → GitHub Pages 배포
```

이 레포는 public 입니다. **발행 확정본만 둡니다.** 초안·메모 폴더는 만들지 않습니다.

## 글 발행 방법

1. `posts/YYYY-MM-DD-slug.md` 파일을 만듭니다. 파일명의 날짜와 slug 는 front matter 의 `date`·`slug` 와 같아야 합니다.
2. 로컬에서 빌드해 확인합니다(아래 "로컬 빌드").
3. 커밋하고 `main` 에 푸시하면 1~2분 뒤 사이트에 반영됩니다.

### 원고 형식

```yaml
---
title: 질문형 제목 (사람들이 AI에 실제로 던질 질문)
slug: outsourcing-ai-cost          # 영소문자·숫자·하이픈. 주소가 /ax/outsourcing-ai-cost/ 가 된다
summary: 2~3문장 직답. 페이지 최상단 박스와 meta description 에 쓴다
date: 2026-11-25
updated: 2026-11-25                # 고치면 이 날짜만 올린다 (sitemap·JSON-LD 수정일에 반영)
concepts: [realization-coefficient] # concepts.yml 의 id. 없는 id 를 쓰면 빌드가 멈춘다
faq:
  - q: 질문
    a: 답
---
본문 마크다운 (제목은 title 하나뿐이므로 본문 소제목은 ## 부터)
```

선택 항목: `category: 관찰 노트` (글 머리 분류 라벨. 없으면 `site.yml` 의 `default_category`)

### 본문 특수 문법

수식은 인용구(`>`)가 아니라 수식 전용 블록으로 씁니다.

````markdown
```formula
잠재 절감액 = 작업당 절감시간 × 연간 빈도 × 시간당 인건비 × 실현계수
```
````

그림은 `posts/figures/` 에 넣고, 문단에 그림 하나만 둡니다. 따옴표 안 문구가 캡션이 됩니다.

```markdown
![계약 형태별 절감분 귀속 도식](figures/contract-flow.svg "그림 1. 계약 형태별 절감분 귀속")
```

대체텍스트(`[]` 안)가 비어 있으면 빌드가 실패합니다. AI 가 그림 내용을 읽는 통로라서입니다.
목차는 본문 `##` 소제목으로 자동 생성되고, 읽는 시간은 글자 수(분당 500자)로 계산됩니다.

### 개념 추가

`concepts.yml` 에 항목을 추가합니다. 개념 사전의 "이 개념을 쓴 글" 목록은 빌드할 때 자동으로 만들어집니다.

```yaml
- id: realization-coefficient   # 영문 id. 주소 앵커가 된다 (/ax/glossary/#realization-coefficient)
  ko: 실현계수
  en: Realization Coefficient
  definition: 한 문장 정의
  description: ""               # 보충 설명 (비우면 표시 안 함)
```

## 로컬 빌드

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install "markdown>=3.11,<4" "pyyaml>=6,<7" "jinja2>=3.1,<4"
.venv\Scripts\python.exe build.py
```

빌드는 마지막에 산출물을 스스로 검사합니다: 금지된 외부 흔적 문자열 0건, JSON-LD 유효(작성자에 url·sameAs 없음), 모든 내부 링크·앵커가 `/ax/` 기준으로 실제 파일을 가리키는지. 하나라도 어긋나면 실패로 끝납니다.

## 금지어 검사 (2중)

금지어 목록은 레포에 두지 않습니다.

| 방어선 | 언제 | 목록 위치 |
|---|---|---|
| 1차 (본 방어선) | 커밋 직전, 로컬 훅 | `~/.ax_banned_terms` (줄바꿈 구분) |
| 2차 | 푸시 후 배포 직전, GitHub Actions | GitHub Secret `BANNED_TERMS` (줄바꿈 구분) |

public 레포는 푸시한 순간 히스토리에 남기 때문에 커밋 전에 막는 1차가 본 방어선입니다.
검사 대상은 원고(`posts/`)·`concepts.yml`·`site.yml`과, 공개 화면에 찍히는 `templates/`·`static/`, 레포 첫 화면인 `README.md`입니다.
로컬 훅은 작업 폴더가 아니라 **실제로 커밋될 스테이징 내용**을 검사합니다.
목록이 비어 있거나 파일이 없으면 검사는 **실패**로 끝납니다(빈 목록으로 통과하지 않게).
CI 로그는 공개되므로 걸린 단어 대신 `금지어 #번호` 로 표시합니다.

### 로컬 훅 설치 (레포를 받은 컴퓨터마다 한 번)

```powershell
git config core.hooksPath hooks
```

그다음 `%USERPROFILE%\.ax_banned_terms` 파일에 금지어를 한 줄에 하나씩 적습니다.

### 수동 검사

```powershell
$env:BANNED_TERMS = Get-Content $HOME\.ax_banned_terms -Raw; py scripts\check_banned.py
```
