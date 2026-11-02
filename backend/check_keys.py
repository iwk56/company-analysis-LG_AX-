"""API 키 확인 도구 (개발용, 터미널에서 실행).

    backend/.venv/bin/python check_keys.py                      # .env에 키가 들어 있는지만 확인 (외부 호출 없음)
    backend/.venv/bin/python check_keys.py --live               # 키마다 가장 가벼운 요청 1건씩 보내 작동 확인
    backend/.venv/bin/python check_keys.py --live --only dart,naver

키 값은 어떤 경우에도 출력하지 않는다(실패 사유도 분류 이름만 보여준다).
"""
import argparse
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Mapping
from urllib.parse import unquote

import httpx

import app.config  # noqa: F401  (backend/.env 를 읽어 환경변수에 올린다)
from app.key_specs import KEY_SPECS, KeySpec, get_provider, is_required, missing_env_names

KEY_ERROR, LIMIT, DISCONNECTED = "키 오류", "한도 초과", "연결 끊김"
TIMEOUT = 10


@dataclass(frozen=True)
class Outcome:
    ok: bool
    reason: str | None = None  # 실패 사유 (키 오류 / 한도 초과 / 연결 끊김 / 기타)
    note: str = ""


OK = Outcome(True)


def _get(client: httpx.Client, url: str, **kwargs) -> httpx.Response | Outcome:
    try:
        return client.get(url, timeout=TIMEOUT, **kwargs)
    except httpx.HTTPError as e:  # 예외 문자열에는 키가 담긴 URL이 있을 수 있어 종류만 남긴다
        return Outcome(False, DISCONNECTED, type(e).__name__)


def _json(resp: httpx.Response) -> dict | None:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else None
    except ValueError:
        return None


def _other(note: str) -> Outcome:
    return Outcome(False, "기타", note)


def _by_http_status(resp: httpx.Response) -> Outcome | None:
    """HTTP 상태만으로 사유가 정해지는 경우."""
    if resp.status_code in (401, 403):
        return Outcome(False, KEY_ERROR, f"HTTP {resp.status_code}")
    if resp.status_code == 429:
        return Outcome(False, LIMIT, "HTTP 429")
    return None


def check_dart(client: httpx.Client, env: Mapping[str, str]) -> Outcome:
    r = _get(client, "https://opendart.fss.or.kr/api/company.json",
             params={"crtfc_key": env["DART_API_KEY"], "corp_code": "00126380"})  # 삼성전자 기업개황 1건
    if isinstance(r, Outcome):
        return r
    data = _json(r)
    if data is None:
        return _other(f"HTTP {r.status_code}, JSON 아님")
    status = str(data.get("status"))
    if status == "000":
        return OK
    if status in ("010", "011", "012"):  # 미등록 키 / 사용 불가 키 / 접근 불가 IP
        return Outcome(False, KEY_ERROR, f"DART 코드 {status}")
    if status == "020":
        return Outcome(False, LIMIT, "DART 코드 020")
    return _other(f"DART 코드 {status}")


def check_data_go_kr(client: httpx.Client, env: Mapping[str, str]) -> Outcome:
    key = unquote(env["DATA_GO_KR_KEY"])  # 인코딩된 키를 붙여넣었어도 한 번만 인코딩되게 한다
    r = _get(client, "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo",
             params={"serviceKey": key, "numOfRows": 1, "pageNo": 1, "resultType": "json"})  # 주식시세 1행
    if isinstance(r, Outcome):
        return r
    if (by_status := _by_http_status(r)) is not None:
        return by_status
    data = _json(r)
    if data is not None and "response" in data:
        code = str(data["response"].get("header", {}).get("resultCode"))
    else:  # 키 문제는 XML 오류 본문으로 오는 경우가 많다
        text = r.text.upper()
        if "SERVICE_KEY_IS_NOT_REGISTERED" in text or "SERVICE KEY IS NOT REGISTERED" in text:
            code = "30"
        elif "LIMITED_NUMBER_OF_SERVICE_REQUESTS" in text:
            code = "22"
        else:
            return _other(f"HTTP {r.status_code}, 알 수 없는 응답")
    if code in ("00", "0"):
        return OK
    if code in ("30", "31", "32", "33"):  # 미등록·기간 만료·미등록 IP·서명 불가 키
        return Outcome(False, KEY_ERROR, f"응답 코드 {code}")
    if code == "22":
        return Outcome(False, LIMIT, "응답 코드 22")
    return _other(f"응답 코드 {code}")


def _error_code(resp: httpx.Response) -> str:
    """NAVER API HUB 에러 본문의 코드(예: SE02). 형식이 계층별로 다르다: 검색 API는 평면 {errorCode}, 게이트웨이는 {error:{errorCode}}."""
    data = _json(resp) or {}
    code = data.get("errorCode") or (data.get("error") or {}).get("errorCode")
    return str(code) if code and re.fullmatch(r"[A-Za-z0-9_-]{1,20}", str(code)) else ""


def check_naver(client: httpx.Client, env: Mapping[str, str]) -> Outcome:
    # NAVER API HUB (구 네이버 검색 API). 기존 openapi.naver.com 주소·X-Naver-* 헤더와 키는 쓸 수 없다.
    r = _get(client, "https://naverapihub.apigw.ntruss.com/search/v1/news",
             params={"query": "삼성전자", "display": 1},  # 뉴스 1건
             headers={"X-NCP-APIGW-API-KEY-ID": env["NAVER_CLIENT_ID"], "X-NCP-APIGW-API-KEY": env["NAVER_CLIENT_SECRET"]})
    if isinstance(r, Outcome):
        return r
    if r.status_code == 200:
        return OK
    code = _error_code(r)
    note = f"HTTP {r.status_code}" + (f", {code}" if code else "")
    if r.status_code == 401:  # 가이드: 인증 실패 (ID/Secret 누락·오류, 헤더 오류, API 권한 미설정)
        return Outcome(False, KEY_ERROR, note)
    if r.status_code == 429:  # 가이드: 하루 허용량 초과
        return Outcome(False, LIMIT, note)
    # 403은 키 오류가 아니라 호출 방식 문제(HTTP 사용, 파라미터 누락·인코딩), 300/404는 주소 오류
    return _other(note)


def check_ecos(client: httpx.Client, env: Mapping[str, str]) -> Outcome:
    end = date.today()
    start = end - timedelta(days=7)  # 휴장일이어도 최근 거래일 값이 잡히게 7일 창에서 1행만 요청
    url = (f"https://ecos.bok.or.kr/api/StatisticSearch/{env['ECOS_API_KEY']}/json/kr/1/1/"
           f"731Y001/D/{start:%Y%m%d}/{end:%Y%m%d}/0000001")  # 원/미국달러 환율
    r = _get(client, url)
    if isinstance(r, Outcome):
        return r
    data = _json(r)
    if data is None:
        return _other(f"HTTP {r.status_code}, JSON 아님")
    if "StatisticSearch" in data:
        return OK
    result = data.get("RESULT") or {}
    code = str(result.get("CODE"))
    if code == "INFO-200":  # 데이터가 없다는 뜻이므로 키는 정상
        return Outcome(True, note="최근 데이터 없음(키는 정상)")
    if code in ("INFO-100", "INFO-300"):  # 유효하지 않은 키 / 관리자가 사용을 제한한 키
        return Outcome(False, KEY_ERROR, f"ECOS 코드 {code}")
    if code == "ERROR-602":  # 과도한 호출로 이용 제한
        return Outcome(False, LIMIT, f"ECOS 코드 {code}")
    return _other(f"ECOS 코드 {code}")


def check_openai(client: httpx.Client, env: Mapping[str, str]) -> Outcome:
    r = _get(client, "https://api.openai.com/v1/models",  # 모델 목록 조회 (텍스트 생성은 하지 않는다)
             headers={"Authorization": f"Bearer {env['OPENAI_API_KEY']}"})
    if isinstance(r, Outcome):
        return r
    if r.status_code == 200:
        return OK
    return _by_http_status(r) or _other(f"HTTP {r.status_code}")


LIVE_CHECKS: dict[str, Callable[[httpx.Client, Mapping[str, str]], Outcome]] = {
    "dart": check_dart,
    "data_go_kr": check_data_go_kr,
    "naver": check_naver,
    "ecos": check_ecos,
    "openai": check_openai,
}  # anthropic은 선택 항목이라 입력 여부만 확인한다


@dataclass(frozen=True)
class Row:
    spec: KeySpec
    status: str
    note: str = ""


def collect(env: Mapping[str, str], only: set[str] | None, live: bool,
            client: httpx.Client | None = None) -> list[Row]:
    rows = []
    for spec in KEY_SPECS:
        if only is not None and spec.id not in only:
            continue
        missing = missing_env_names(spec, env)
        if missing:
            status = "미입력" if is_required(spec, env) else "미입력(선택)"
            rows.append(Row(spec, status, ", ".join(missing)))
        elif not live:
            rows.append(Row(spec, "입력됨", "호출 안 함"))
        elif spec.id not in LIVE_CHECKS:
            rows.append(Row(spec, "입력됨", "선택 항목이라 호출 안 함"))
        else:
            out = LIVE_CHECKS[spec.id](client, env)
            if out.ok:
                rows.append(Row(spec, "정상", out.note))
            else:
                rows.append(Row(spec, f"실패({out.reason})", out.note))
    return rows


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _pad(text: str, width: int) -> str:
    return text + " " * (width - _width(text))


def render(rows: list[Row], env: Mapping[str, str], secrets: list[str]) -> str:
    table = [("키", "이름", "상태", "비고")] + [(r.spec.id, r.spec.label, r.status, r.note) for r in rows]
    widths = [max(_width(line[i]) for line in table) for i in range(4)]
    lines = ["  ".join(_pad(cell, widths[i]) for i, cell in enumerate(line)).rstrip() for line in table]
    lines.insert(1, "  ".join("-" * w for w in widths))
    lines.append(f"\nLLM_PROVIDER = {get_provider(env)}")
    text = "\n".join(lines)
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):  # 안전장치: 키 값이 섞이면 가린다
        text = text.replace(secret, "***")
    return text


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None,
         client: httpx.Client | None = None) -> int:
    parser = argparse.ArgumentParser(description="API 키 입력 여부와 작동 여부를 확인합니다.")
    parser.add_argument("--live", action="store_true", help="키마다 가장 가벼운 요청 1건을 보내 작동 확인")
    parser.add_argument("--only", help="확인할 키만 쉼표로 (예: dart,naver)")
    args = parser.parse_args(argv)
    env = os.environ if env is None else env

    only = None
    if args.only:
        only = {x.strip() for x in args.only.split(",") if x.strip()}
        unknown = only - {s.id for s in KEY_SPECS}
        if unknown:
            print(f"알 수 없는 키: {', '.join(sorted(unknown))} (가능: {', '.join(s.id for s in KEY_SPECS)})")
            return 2

    owns_client = args.live and client is None
    if owns_client:
        client = httpx.Client()
    try:
        rows = collect(env, only, args.live, client)
    finally:
        if owns_client:
            client.close()

    secrets = [env.get(n, "") for s in KEY_SPECS for n in s.env_names] + [unquote(env.get("DATA_GO_KR_KEY", ""))]
    print(render(rows, env, secrets))
    bad = [r for r in rows if r.status == "미입력" or r.status.startswith("실패")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
