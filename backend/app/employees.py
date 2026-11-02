"""직원 현황(OpenDART empSttus): AI 없이 코드로 합산한다. 사업보고서 기준이며 연결이 아니라 보고서 작성 회사(보통 별도) 기준이다."""
import json
from datetime import date

import httpx

from .config import DATA_DIR
from .dart import DartError, _get
from .fin_collect import DART_VIEWER

RAW_DIR = DATA_DIR / "dart_raw"
ANNUAL_REPORT = "11011"


def _num(s) -> float | None:
    s = str(s or "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None  # "-" 등


def summarize(rows: list[dict]) -> dict | None:
    """성별·사업부문 행을 합친다. 직원 수는 합계, 근속연수·1인 평균 급여는 직원 수로 가중한 평균(코드 계산).

    DART는 합계 행을 따로 주지 않아 여러 행을 합친 값이라, 원문의 합계와 약간 다를 수 있다.
    """
    heads = [(_num(r.get("sm")), _num(r.get("avrg_cnwk_sdytrn")), _num(r.get("jan_salary_am"))) for r in rows]
    heads = [h for h in heads if h[0]]
    if not heads:
        return None
    total = sum(h[0] for h in heads)

    def weighted(idx: int) -> float | None:
        known = [(h[0], h[idx]) for h in heads if h[idx] is not None]
        base = sum(w for w, _ in known)
        return round(sum(w * v for w, v in known) / base, 1) if base else None

    salary = weighted(2)
    return {"count": round(total), "avg_tenure_years": weighted(1),
            "avg_salary_won": None if salary is None else round(salary),
            "rcept_no": rows[0].get("rcept_no"), "settled_on": rows[0].get("stlm_dt")}


async def fetch_employees(client: httpx.AsyncClient, corp_code: str, year: int, raw_dir=RAW_DIR) -> dict | None:
    """최근 사업연도 사업보고서의 직원 현황. 응답은 저장해 두고 다시 부르지 않는다. 자료가 없으면 None."""
    path = raw_dir / f"{corp_code}_{year}_emp.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        resp = await _get(client, "empSttus.json", {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": ANNUAL_REPORT})
        try:
            data = resp.json()
        except ValueError:
            raise DartError("json", "직원 현황 응답을 읽지 못했습니다") from None
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
