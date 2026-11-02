# 기업분석 리포트 툴 (가칭)

상장 일반기업 1곳을 입력하면 공시·재무 데이터, 기사, 경제 지표를 모아 3페이지 분량의 기업분석 리포트를 만들고 저장해 주는 개인용 도구.

> 현재 Phase 0(프로젝트 준비) 단계입니다. 자세한 진행 상황은 [docs/progress.md](docs/progress.md)를 보세요.

## 폴더 구조

| 폴더 | 내용 |
| --- | --- |
| `frontend/` | React 화면 |
| `backend/` | Python FastAPI 서버 |
| `database/` | 데이터베이스 관련 파일 |
| `docs/` | mvp.md, prd.md, spec.md, plan.md, progress.md |

## 기술 스택

- 프론트: React
- 백엔드: Python FastAPI
- DB: 개발 중 SQLite → 마지막에 Supabase(PostgreSQL)

## 실행 방법

(Phase 4 이후 작성 예정)

## 사용한 API

OpenDART, 네이버 검색 API, 한국은행 ECOS, 공공데이터포털(금융위원회 주식시세정보), Claude API. 키는 `backend/.env`에만 둡니다. (`backend/.env.example` 참고)

## 숫자와 AI의 역할 분담

(Phase 10에서 작성 예정)
