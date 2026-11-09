"""현금흐름 분석 (2026-11-04, 현금흐름 탭) — 번 현금(영업)을 어디에 썼나(설비투자·주주환원·빚 갚기)를 금액으로 본다.

- 잉여현금흐름(FCF) = 영업활동 현금흐름 − 설비투자(유형자산 취득 + 무형자산 취득)
- 주주환원 = 배당금 지급 + 자기주식 취득, 순차입 = 차입 − 상환(+면 빌림, −면 갚음)
- 이익의 질 = 영업현금흐름 ÷ 당기순이익(1보다 크면 이익보다 현금이 더 들어옴)
- DART는 지출 항목(취득·지급·상환·납부)을 양수로 주는 회사가 많아 이 항목들은 절댓값으로 맞추고 화면에서 '나간 돈'으로 보인다.
- 최신 사업연도는 현금흐름표 전체 행(detail)으로 '기초 현금 → 기말 현금' 다리(bridge)를 만든다.
"""
import re

from .models import YearFinancials

SECTION_IDS = {"ifrs-full_CashFlowsFromUsedInOperatingActivities": "operating",
               "ifrs-full_CashFlowsFromUsedInInvestingActivities": "investing",
               "ifrs-full_CashFlowsFromUsedInFinancingActivities": "financing"}
CASH_IDS = {"dart_CashAndCashEquivalentsAtBeginningOfPeriodCf": "begin", "dart_CashAndCashEquivalentsAtEndOfPeriodCf": "end",
            "ifrs-full_EffectOfExchangeRateChangesOnCashAndCashEquivalents": "fx", "ifrs-full_IncreaseDecreaseInCashAndCashEquivalents": "net"}
_OUT = re.compile(r"(취득|증가|지급|상환|납부|유출|매입|감소$)")
_IN = re.compile(r"(처분|수취|수령|차입|발행|행사|유입|감소)")


def _abs(v):
    return None if v is None else abs(v)


def signed(name: str, value: float | None) -> float | None:
    """현금흐름표 한 행의 금액을 '들어온 돈 +, 나간 돈 −'로. 이름으로 방향을 정하고, 순증감·합계처럼 방향이 없는 행은 원래 부호."""
    if value is None:
        return None
    n = re.sub(r"\s", "", name)
    if "순증감" in n or "현금흐름" in n:
        return value
    if re.search(r"(자산|상품|채권|투자).*(증가)$", n) or re.search(r"(취득|지급|상환|납부|유출)", n):
        return -abs(value)
    if _IN.search(n):
        return abs(value)
    return value


def detail(rows: list[dict], parse) -> dict:
    """최신 보고서의 현금흐름표 행 → {"items": [{section, name, current, prior}], "cash": {begin, end, fx, net}}.
    DART 응답은 합계 행 뒤에 그 활동의 세부 행이 온다. parse: 금액 문자열 → 숫자."""
    items, cash, section = [], {}, None
    for r in rows:
        if r.get("sj_div") != "CF":
            continue
        aid, name = r.get("account_id") or "", (r.get("account_nm") or "").strip()
        cur, prev = parse(r.get("thstrm_amount")), parse(r.get("frmtrm_amount"))
        if aid in CASH_IDS:
            cash[CASH_IDS[aid]] = {"current": cur, "prior": prev}
            continue
        if aid in SECTION_IDS:
            section = SECTION_IDS[aid]
            items.append({"section": section, "name": name, "total": True, "current": cur, "prior": prev})
            continue
        if section:
            items.append({"section": section, "name": name, "total": False,
                          "current": signed(name, cur), "prior": signed(name, prev)})
    return {"items": items, "cash": cash}


def year_metrics(y: YearFinancials) -> dict:
    capex = None if y.capex_ppe is None and y.capex_intangible is None else (_abs(y.capex_ppe) or 0) + (_abs(y.capex_intangible) or 0)
    returns = None if y.dividends_paid is None and y.buyback is None else (_abs(y.dividends_paid) or 0) + (_abs(y.buyback) or 0)
    net_borrow = None if y.borrowing_in is None and y.borrowing_out is None else (_abs(y.borrowing_in) or 0) - (_abs(y.borrowing_out) or 0)
    fcf = None if y.cfo is None or capex is None else y.cfo - capex
    return {"cfo": y.cfo, "cfi": y.cfi, "cff": y.cff, "capex": capex, "fcf": fcf, "dividends": _abs(y.dividends_paid), "buyback": _abs(y.buyback),
            "shareholder_returns": returns, "net_borrowing": net_borrow, "tax_paid": _abs(y.tax_paid), "cash_end": y.cash_end,
            "net_income": y.net_income,
            "cfo_to_net_income": None if y.cfo is None or not y.net_income or y.net_income <= 0 else y.cfo / y.net_income,
            "capex_to_revenue": None if capex is None or not y.revenue else capex / y.revenue}


def bridge(m: dict, det: dict | None) -> dict | None:
    """기초 현금 → 영업 → 설비투자 → 기타 투자 → 주주환원 → 순차입 → 기타 재무 → 환율 → 기말 현금 (최신 연도)."""
    cash = (det or {}).get("cash") or {}
    begin, end = (cash.get("begin") or {}).get("current"), (cash.get("end") or {}).get("current")
    if None in (begin, end, m["cfo"], m["cfi"], m["cff"]):
        return None
    capex = m["capex"] or 0
    returns = m["shareholder_returns"] or 0
    borrow = m["net_borrowing"] or 0
    fx = (cash.get("fx") or {}).get("current") or 0
    steps = [("영업활동으로 번 현금", m["cfo"]), ("설비투자(유형·무형자산 취득)", -capex), ("설비투자 외 투자활동 순액", m["cfi"] + capex),
             ("주주환원(배당·자사주)", -returns), ("차입금 순증감", borrow), ("그 밖의 재무활동(리스 상환 등)", m["cff"] + returns - borrow),
             ("환율 변동 효과", fx)]
    gap = end - begin - sum(v for _, v in steps)
    return {"begin": begin, "end": end, "steps": [{"label": k, "amount": v} for k, v in steps], "unexplained": gap}


def compute_cash(years: dict[int, YearFinancials], det: dict | None = None) -> dict:
    """{"years": {연도: 지표}, "detail": 최신 연도 행(있으면), "bridge": 최신 연도 다리}."""
    ys = {str(yr): year_metrics(y) for yr, y in sorted(years.items())}
    latest = str(max(years)) if years else None
    return {"years": ys, "detail": det, "bridge": bridge(ys[latest], det) if latest else None}
