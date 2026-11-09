"""타법인 출자 현황(OpenDART otrCprInvstmntSttus): 회사가 지분을 가진 다른 회사들 (사업 구조 탭 ⑦, 2026-11-04). AI 없이 코드로 정리한다.

사업보고서 기준. 지분율 50% 이상은 보통 종속회사(회사가 지배하는 회사)이고, 그 아래는 관계회사·단순 투자다(회계상 지배 여부는 원문 확인).
응답은 data/dart_raw에 저장해 다시 부르지 않는다.
"""
import json

import httpx

from .config import DATA_DIR
from .dart import DartError, _get
from .fin_collect import DART_VIEWER

RAW_DIR = DATA_DIR / "dart_raw"
ANNUAL_REPORT = "11011"
SHOW = 15  # 화면에 보여 줄 최대 회사 수 (장부가액 큰 순)
TOTAL_NAMES = ("합계", "합 계", "계", "총계")


def _num(s) -> float | None:
    s = str(s or "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    try:
        v = float(s.strip("()"))
    except ValueError:
        return None
    return -v if neg else v


def summarize(rows: list[dict]) -> dict | None:
    """행 → {count, majority_count, items[...]}. 합계 행은 뺀다. 금액은 DART 응답 단위(원) 그대로."""
    items = []
    for r in rows:
        name = (r.get("inv_prm") or "").strip()
        if not name or name.replace(" ", "") in TOTAL_NAMES:
            continue
        items.append({
            "name": name,
            "purpose": (r.get("invstmnt_purps") or "").strip() or None,
            "share": _num(r.get("trmend_blce_qota_rt")),  # 기말 지분율(%)
            "book_won": _num(r.get("trmend_blce_acntbk_amount")),  # 기말 장부가액
            "assets_won": _num(r.get("recent_bsns_year_fnnr_sttus_tot_assets")),  # 그 회사 최근 사업연도 총자산
            "net_income_won": _num(r.get("recent_bsns_year_fnnr_sttus_thstrm_ntpf")),  # 그 회사 당기순손익
        })
    if not items:
        return None
    items.sort(key=lambda x: (x["book_won"] or 0), reverse=True)
    return {"count": len(items), "majority_count": sum(1 for x in items if (x["share"] or 0) >= 50),
            "items": items[:SHOW], "rcept_no": rows[0].get("rcept_no")}


async def fetch_subsidiaries(client: httpx.AsyncClient, corp_code: str, year: int, raw_dir=RAW_DIR) -> dict | None:
    """최근 사업연도 사업보고서의 타법인 출자 현황. 자료가 없으면 None."""
    path = raw_dir / f"{corp_code}_{year}_invest.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        resp = await _get(client, "otrCprInvstmntSttus.json", {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": ANNUAL_REPORT})
        try:
            data = resp.json()
        except ValueError:
            raise DartError("json", "타법인 출자 현황 응답을 읽지 못했습니다") from None
        if data.get("status") not in ("000", "013"):
            raise DartError(data.get("status") or "?", data.get("message", ""))
        raw_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if data.get("status") != "000":
        return None
    out = summarize(data.get("list") or [])
    if out:
        out["year"] = year
        out["url"] = DART_VIEWER.format(out["rcept_no"]) if out["rcept_no"] else None
    return out
