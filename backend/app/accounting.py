"""회계 이슈 체크 중 AI 없이 코드로 하는 두 가지 (Phase 6-B): 감사의견(OpenDART 정형 API)과 정정공시(공시 목록).

판정은 이 모듈이 한다. 상태는 clear(이상 없음) / check(확인 필요)이고, 자료를 못 받거나 읽지 못하면 호출한 쪽이 '확인 불가'로 둔다.
"""
import json
import re
from datetime import date

import httpx

from .config import DATA_DIR
from .dart import DartError, _get
from .fin_collect import DART_VIEWER

RAW_DIR = DATA_DIR / "dart_raw"
ANNUAL_REPORT = "11011"
UNQUALIFIED = "적정의견"
_BLANK = {"", "-", "해당사항없음", "해당없음", "없음"}
MAX_CORRECTIONS_SHOWN = 10


def _squash(s: str | None) -> str:
    return re.sub(r"\s+", "", s or "")


def _text_or_none(s: str | None) -> str | None:
    """'해당사항 없음'·'-' 같은 빈 표시는 None, 나머지는 줄바꿈을 공백으로 바꾼 문장."""
    return None if _squash(s) in _BLANK else re.sub(r"\s+", " ", s or "").strip()


# ───────────────────────── 감사의견
async def fetch_audit(client: httpx.AsyncClient, corp_code: str, year: int, raw_dir=RAW_DIR) -> list[dict] | None:
    """회계감사인의 명칭 및 감사의견(accnutAdtorNmNdAdtOpinion). 사업보고서 기준이며 당기·전기·전전기 행이 함께 온다.

    응답은 저장해 두고 다시 부르지 않는다. 자료가 없으면(013) None.
    """
    path = raw_dir / f"{corp_code}_{year}_audit.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        resp = await _get(client, "accnutAdtorNmNdAdtOpinion.json",
                          {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": ANNUAL_REPORT})
        try:
            data = resp.json()
        except ValueError:
            raise DartError("json", "감사의견 응답을 읽지 못했습니다") from None
        if data.get("status") not in ("000", "013"):
            raise DartError(data.get("status") or "?", data.get("message", ""))
        raw_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data.get("list") if data.get("status") == "000" else None


def judge_audit(rows: list[dict] | None) -> dict | None:
    """당기 행(별도·연결)의 감사의견을 본다. 모두 '적정의견'이면 clear, 하나라도 다르면 check. 당기 행이 없으면 None."""
    current = [r for r in rows or [] if "(당기)" in _squash(r.get("bsns_year"))]
    if not current:
        return None
    opinions = list(dict.fromkeys(_squash(r.get("adt_opinion")) or "의견 없음" for r in current))
    emphasis = list(dict.fromkeys(t for r in current if (t := _text_or_none(r.get("emphs_matter")))))
    matters = list(dict.fromkeys(t for r in current if (t := _text_or_none(r.get("core_adt_matter")))))
    rcept_no = current[0].get("rcept_no")
    return {
        "verdict": "clear" if opinions == [UNQUALIFIED] else "check",
        "opinion": " / ".join(opinions),
        "auditor": " / ".join(dict.fromkeys(r.get("adtor", "").strip() for r in current if r.get("adtor"))) or None,
        "fiscal_term": _squash(current[0].get("bsns_year")).replace("(당기)", ""),
        "settled_on": current[0].get("stlm_dt"),
        "emphasis": emphasis,
        "key_audit_matters": matters,
        "rcept_no": rcept_no,
        "url": DART_VIEWER.format(rcept_no) if rcept_no else None,
    }


# ───────────────────────── 정정공시
async def fetch_corrections(client: httpx.AsyncClient, corp_code: str, start: date, end: date) -> list[dict]:
    """기간 안 정기공시(pblntf_ty=A) 목록 중 보고서명에 '정정'이 든 것. 한 번 호출한다(최대 100건)."""
    resp = await _get(client, "list.json", {"corp_code": corp_code, "bgn_de": start.strftime("%Y%m%d"), "end_de": end.strftime("%Y%m%d"),
                                            "pblntf_ty": "A", "page_count": "100"})
    try:
        data = resp.json()
    except ValueError:
        raise DartError("json", "공시 목록 응답을 읽지 못했습니다") from None
    if data.get("status") == "013":
        return []
    if data.get("status") != "000":
        raise DartError(data.get("status") or "?", data.get("message", ""))
    return [r for r in data.get("list") or [] if "정정" in (r.get("report_nm") or "")]


def judge_corrections(filings: list[dict], start: date, end: date) -> dict:
    items = sorted(({"title": re.sub(r"\s+", " ", f["report_nm"]).strip(), "date": f"{f['rcept_dt'][:4]}-{f['rcept_dt'][4:6]}-{f['rcept_dt'][6:8]}",
                     "url": DART_VIEWER.format(f["rcept_no"])} for f in filings if f.get("rcept_dt") and f.get("rcept_no")),
                   key=lambda x: x["date"], reverse=True)
    return {"verdict": "check" if items else "clear", "count": len(items), "items": items[:MAX_CORRECTIONS_SHOWN],
            "period_start": start.isoformat(), "period_end": end.isoformat()}
