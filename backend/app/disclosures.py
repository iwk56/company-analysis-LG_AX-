"""최근 공시 목록 (OpenDART 공시검색 list.json) — 3페이지 공시 주제 묶음의 재료 (Phase 7-B, docs/spec.md 1장).

네이버 기사는 약관상 AI에 넣을 수 없어(spec 0장 규칙 10) 외부 사건의 재료로 DART 공시를 쓴다.
보고서명·접수일·제출인·원문 링크만 쓰고, 한 번 호출로 최근 3개월 최대 100건을 받는다(접수일 최신순).
"""
import re
from datetime import date

import httpx

from .dart import DartError, _get
from .fin_collect import DART_VIEWER

MONTHS = 3
PAGE_COUNT = 100


def months_ago(today: date, months: int) -> date:
    y, m = divmod(today.year * 12 + today.month - 1 - months, 12)
    m += 1
    for day in (today.day, 30, 29, 28):  # 말일이 없는 달이면 앞당긴다
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise AssertionError


def _date(s: str) -> str:
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


async def fetch_disclosures(client: httpx.AsyncClient, corp_code: str, end: date) -> dict:
    """end(리포트 생성일) 기준 최근 3개월 공시. {"period_start", "period_end", "total", "items": [{rcept_no, title, date, filer, url}]}"""
    start = months_ago(end, MONTHS)
    resp = await _get(client, "list.json", {"corp_code": corp_code, "bgn_de": start.strftime("%Y%m%d"),
                                            "end_de": end.strftime("%Y%m%d"), "page_count": str(PAGE_COUNT)})
    try:
        data = resp.json()
    except ValueError:
        raise DartError("json", "공시 목록 응답을 읽지 못했습니다") from None
    if data.get("status") == "013":  # 조회된 데이터 없음
        rows, total = [], 0
    elif data.get("status") != "000":
        raise DartError(data.get("status") or "?", data.get("message", ""))
    else:
        rows, total = data.get("list") or [], int(data.get("total_count") or 0)
    items = [{"rcept_no": r["rcept_no"], "title": re.sub(r"\s+", " ", r.get("report_nm") or "").strip(), "date": _date(r["rcept_dt"]),
              "filer": (r.get("flr_nm") or "").strip(), "url": DART_VIEWER.format(r["rcept_no"])}
             for r in rows if r.get("rcept_no") and r.get("rcept_dt")]
    return {"period_start": start.isoformat(), "period_end": end.isoformat(), "total": max(total, len(items)), "items": items}
