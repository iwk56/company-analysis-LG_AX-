# 진행 상황 (progress)

## 현재 위치

- Phase 1 (기업 검색) 진행 중 — 코드 작성 완료, 아직 실제 DART 호출 검증 전 (DART가 연결을 거부하는 상태, 아래 참고)

## 완료한 것

### Phase 0
- [x] `frontend/`, `backend/`, `database/` 폴더 생성
- [x] `README.md` 기본 틀
- [x] `AGENTS.md` 작업 규칙, `CLAUDE.md`(`@AGENTS.md`)
- [x] `backend/.env.example` (키 이름과 설명만)
- [x] Git 초기화, `.gitignore` (.env, 가상환경, node_modules, SQLite 파일)
- [x] `docs/progress.md` 생성

## 내가 할 일 (Phase 0)

- [x] Python·Node.js 설치 확인 (`backend/.venv` Python 3.13.16, Node v24.21.0)
- [ ] OpenDART 회원가입 후 인증키 발급, `backend/.env`에 직접 입력
- [ ] `git status`에 `.env`가 보이지 않는지 확인
- [ ] 확인 후 commit: `프로젝트 구조와 기획 문서 저장`

## Phase 1 진행 메모 (2026-11-02)

- 완료: 패키지 설치(`backend/requirements.txt`), 고유번호 파일 수집, 기업개황 캐시, 검색 API, 금융업 판별 규칙(`backend/app/industry.py`), 전체 업종코드 조사 스크립트(`app/survey_industry.py`), 자동 테스트 10개 통과
- 결정: 상장기업은 유가증권(Y)·코스닥(K)만 (코넥스 N·기타 E 제외). 고유번호 파일에는 상장폐지 기업도 종목코드가 남아 있어 개황의 `corp_cls`로 걸러냄
- 결정: 업종코드 64992는 기본 일반기업, 금융지주사만 고유번호 예외 목록(`FINANCIAL_HOLDING_CORP_CODES`)으로 관리 — 목록은 아직 비어 있음, 상장 금융지주사 조사 후 내 확인을 거쳐 확정
- KSIC는 10차로 임시 확정. 표(`backend/data/ksic/`)에서 코드 2,000개(2~5자리)를 읽는 데 성공. 일치율 확인은 전체가 아니라 시연할 기업과 경쟁사 몇 곳으로만 한다
- 막힌 것: DART가 모든 호출에 연결을 거부(Connection reset)함. 전체 조사 중 급하게 호출한 것이 원인일 가능성 — 복구 여부 확인 필요
- 전체 상장기업 업종코드 조사: **보류** (시간·사용량 절약). 나중에 필요해지면 `app/survey_industry.py`를 `--limit`으로 나눠 실행한다 (스크립트는 그대로 둠, 지금은 실행하지 않음)
- Phase 5 경쟁사 자동 추천(같은 업종 후보 추천)은 **나중으로 미룸**. 경쟁사는 직접 검색해서 추가하는 방식만 쓴다
- 금융지주사 예외 목록 확정(9곳, 업종코드와 상관없이 금융업): KB금융·신한지주·하나금융지주·우리금융지주(01350869)·BNK금융지주·iM금융지주·JB금융지주·메리츠금융지주·한국금융지주 — `industry.py`의 `FINANCIAL_HOLDING_CORP_CODES`
- 남은 것: 업종명 연결(KSIC 10차 표 사용), 검색 API 실제 확인("삼성")

## Phase 2 메모

- 재무상태표에 유동/비유동 구분이 없으면 "금융업일 수 있음" 경고를 띄우는 안전장치를 추가한다 (업종코드 기반 금융업 판별을 빠져나간 경우 대비)

## 다음 할 일

- DART 복구 확인(호출 1건) → '삼성' 검색 확인 → Phase 1 완료
- (오늘은 DART를 더 호출하지 않는다. Phase 1 코드는 'DART 실호출 확인 전' 저장점으로 commit함)
