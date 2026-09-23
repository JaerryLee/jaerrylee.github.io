# 이정재의 엔지니어링 노트

Applied AI, LLM Ops와 백엔드 개발 경험을 기록하는 한국어 기술 블로그.
Astro와 Markdown으로 빌드하는 정적 사이트다.

- 사이트 주소: `https://jaerrylee.github.io/`
- 대상 GitHub 저장소: `JaerryLee/jaerrylee.github.io`
- 포트폴리오: `https://jaerrylee.github.io/portfolio/`

## 로컬 실행

Node.js 24와 pnpm 12.5.1을 사용한다.

```bash
pnpm install --frozen-lockfile
pnpm dev
```

## 검증과 미리보기

```bash
pnpm build
pnpm preview
```

`build`는 Astro·TypeScript 검사와 Markdown 메타데이터 검증 뒤 정적 HTML을 생성한다.
RSS도 빌드된다. 글은 각각 실제 HTML 경로로 생성되어 새로고침과 직접 접근이 가능하다.

## 검색 노출 설정

블로그와 논문 노트의 모든 HTML에 `noindex, nofollow, noimageindex`를 적용한다.
사이트맵은 생성하지 않는다. `robots.txt`는 논문 이미지·RSS·공유 이미지 수집을 제한한다.
HTML은 검색엔진이 `noindex`를 읽을 수 있도록 수집을 허용한다. HTML까지 `Disallow: /`로 막으면
검색 제외 지시를 읽지 못해 주소가 검색 결과에 남을 수 있다.

이 설정은 검색엔진에 보내는 요청이며 인증이나 접근 제한이 아니다. 주소를 알거나 링크를 받은 방문자는
계속 접속할 수 있고, 기존 검색 결과는 검색엔진의 재수집 후 반영된다. 공개 GitHub 저장소의 노출 범위는 별개다.
`/portfolio/`는 별도 프로젝트 사이트이므로 이 블로그의 HTML 검색 제외 설정 대상이 아니다.

- [Google의 noindex 안내](https://developers.google.com/search/docs/crawling-indexing/block-indexing)

## 논문 노트

`/papers/`에서 107편의 한국어 해설을 검색하고 여섯 주제별 읽기 순서를 확인할 수 있다.
개별 노트는 `/papers/<id>/`이며 원문 저자와 공식 출처 링크를 표시한다.
읽기 가이드 글은 `/posts/paper-reading-map/`으로 게시하며 기존 RSS에도 포함된다.

- 분류와 추천 읽기 순서: `src/data/paper-topics.json`
- 공개용 메타데이터: `src/data/papers.json`
- 정리한 해설 본문: `src/content/papers/`
- 그림과 표 이미지: `public/paper-assets/`

바탕 화면의 원본 library 자료에서 다시 가져올 때:

```bash
uv run scripts/import-papers.py ../library
pnpm build
```

importer는 주제에 등록되어 있고 유효한 PDF와 한국어 해설이 함께 있는 자료만 가져온다.
주제를 먼저 지정하지 않은 신규 해설은 가져오기를 중단하므로 `paper-topics.json`에 먼저 분류한다.
원문 PDF는 복사하지 않고 공식 원문에 연결한다. 메타데이터의 개인 컴퓨터 경로와 실행 기록은 가져오지 않는다.
본문은 스크립트·인라인 스타일·이벤트 속성을 제거하고, 수식과 그림·표를 유지한다.
내장 이미지는 내용 해시로 중복 제거한 별도 파일로 저장하고 지연 로딩한다.
소스 라이브러리는 수정하지 않으며 가져오기 결과는 `scripts/paper-import-report.json`에 기록한다.

`pnpm build`는 논문 분류·출처·본문·목차·이미지 참조도 검사한다.
현재 해설이 없는 10편은 게시하지 않았으며, 그중 세 PDF는 404 HTML이라 가져오기 보고서에서 별도로 구분한다.

## 새 글 작성

`src/content/posts/`에 Markdown 파일을 추가한다. 파일명이 URL의 slug다.
예를 들어 `llm-ops-opentelemetry.md`의 주소는 `/posts/llm-ops-opentelemetry/`다.

```yaml
---
title: "글 제목"
description: "목록과 검색 결과에 사용할 짧은 설명"
date: 2026-09-21
category: LLM Ops
tags: [OpenTelemetry, FastAPI]
order: 1
draft: true
---
```

본문은 `##` 제목부터 작성한다. 해당 제목으로 목차가 자동 생성된다.
category는 `LLM Ops`, `Applied AI`, `Backend`, `Agentic AI`, `Research Notes` 중 하나다.
`order`는 같은 작성일의 표시 순서를 정한다. `draft: true`인 글은 목록·상세 경로·RSS에서 제외된다.
글을 게시하려면 `draft`를 제거하거나 `false`로 바꾼다.

코드 블록에는 언어를 붙이면 구문 강조가 적용된다. 본문은 작성자가 관리하는 Markdown이며,
외부 사용자의 HTML 입력을 받는 기능은 없다.

## 현재 원고

1. LLM 실행을 따라가는 OpenTelemetry 로깅과 트레이싱
2. AGP Note: 회의 기록을 팀의 다음 업무로 연결하기
3. VAETKI Commerce: AI 배너 작업의 상태와 크레딧 다루기
4. Dainos: 에이전트 실행을 업무 제품으로 연결하는 설계

2026-09-21에 코드·문서와 본인 작성 이력을 확인해 작성했다.
날짜는 글 작성일이며 프로젝트 종료일이 아니다. 설명용 코드와 실제 구현 범위는 본문에서 구분한다.
현재 직무는 LLM Ops이며 나머지 세 글은 이전 프로젝트의 기록이다.

## GitHub Pages 배포

계정 루트 사이트이므로 저장소 이름은 `jaerrylee.github.io`이고 Astro의 `base`는 `/`다.
저장소의 **Settings → Pages → Source**를 **GitHub Actions**로 설정한다.
`main`에 push하면 검사·빌드 후 Pages에 배포한다. PR에서는 빌드까지만 실행한다.

GitHub Free에서 Pages를 사용하려면 이 블로그 저장소가 public이어야 한다.
기존 `portfolio` 저장소의 공개 범위와 배포 설정은 별개다.

- [Astro의 GitHub Pages 배포 안내](https://docs.astro.build/en/guides/deploy/github/)
- [GitHub Pages 지원 조건과 사이트 생성](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site)

## 포트폴리오를 같은 주소에 게시하기

`public/portfolio/`에는 기존 포트폴리오의 **빌드 결과**를 보관한다.
이 파일들은 블로그와 함께 `/portfolio/`로 게시된다. 기존 portfolio 저장소의 원본·Git 이력·업무 근거 문서는 복사하지 않는다.
브라우저에 제공하는 HTML·JavaScript·이미지와 이 블로그의 글·소스는 공개 대상이다.

포트폴리오를 수정한 뒤, 두 저장소가 같은 부모 디렉터리에 있을 때 다음을 실행한다.

```bash
pnpm sync:portfolio
pnpm build
```

첫 명령이 인접한 `../portfolio`를 `/portfolio/` 경로로 빌드하고 정적 파일을 갱신한다.
GitHub Actions에서는 이 체크인된 빌드 결과를 사용하므로 private 저장소 접근 토큰이 필요 없다.
포트폴리오 변경을 반영하려면 이 명령으로 스냅샷도 갱신해 함께 커밋해야 한다.

기존 저장소의 Pages를 별도로 켜면 `/portfolio/` 경로가 별도 프로젝트 사이트로 제공될 수 있으므로,
이 배포 구성을 사용하는 동안에는 블로그 저장소에서 해당 경로를 관리한다.
