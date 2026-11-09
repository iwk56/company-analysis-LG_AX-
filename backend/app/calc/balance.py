"""DART 재무상태표 계정과 현금흐름표 세부 항목을 연도별로 묶는다."""
import re
from collections.abc import Callable

from .cash import detail as cash_detail

TOTAL_IDS = {
    "ifrs-full_Assets",
    "ifrs-full_CurrentAssets",
    "ifrs-full_NoncurrentAssets",
    "ifrs-full_Liabilities",
    "ifrs-full_CurrentLiabilities",
    "ifrs-full_NoncurrentLiabilities",
    "ifrs-full_Equity",
    "ifrs-full_EquityAttributableToOwnersOfParent",
    "ifrs-full_EquityAndLiabilities",
}
TOTAL_NAMES = {
    "자산",
    "자산총계",
    "유동자산",
    "비유동자산",
    "부채",
    "부채총계",
    "유동부채",
    "비유동부채",
    "자본",
    "자본총계",
    "지배기업의소유지분",
    "지배기업소유주지분",
    "자본과부채총계",
    "부채와자본총계",
    "자본및부채총계",
    "부채및자본총계",
}
INVALID_IDS = {"", "-", "-표준계정코드미사용-"}


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _group(account_id: str, name: str) -> str | None:
    account_id, name = account_id or "", _norm(name)
    if account_id in TOTAL_IDS or name in TOTAL_NAMES:
        return None
    if any(token in account_id for token in ("Equity", "Capital", "RetainedEarnings", "TreasuryShares")):
        return "equity"
    if any(token in account_id for token in ("Liabilit", "Borrowings", "Payables", "Provisions", "Debt", "Obligation")):
        return "liabilities"
    if any(token in account_id for token in ("Assets", "Receivable", "Inventories", "CashAndCash", "PropertyPlant",
                                             "Intangible", "Goodwill", "InvestmentProperty", "Loans")):
        return "assets"
    if any(token in name for token in ("자본", "이익잉여금", "주식발행초과금", "자기주식", "비지배지분")):
        return "equity"
    if any(token in name for token in ("부채", "차입", "사채", "매입채무", "미지급", "선수", "충당", "리스부채",
                                       "계약부채", "법인세부채", "이연법인세부채", "퇴직급여채무", "예수금", "금융부채")):
        return "liabilities"
    if any(token in name for token in ("자산", "현금", "채권", "재고", "유형자산", "무형자산", "영업권", "대여금",
                                       "투자부동산", "관계기업", "종속기업", "선급금", "계약자산")):
        return "assets"
    return None


def snapshot(rows: list[dict], amount_field: str, parse_amount: Callable[[object], float | None]) -> dict:
    """한 사업연도의 재무상태표 계정과 현금흐름표 세부 거래를 추출한다."""
    accounts: dict[str, list[dict]] = {"assets": [], "liabilities": [], "equity": []}
    seen: set[str] = set()
    for row in rows:
        if row.get("sj_div") != "BS":
            continue
        account_id = row.get("account_id") or ""
        name = (row.get("account_nm") or "").strip()
        group = _group(account_id, name)
        amount = parse_amount(row.get(amount_field))
        if group is None or amount is None:
            continue
        key = account_id if account_id not in INVALID_IDS else _norm(name)
        if not key or key in seen:
            continue
        seen.add(key)
        accounts[group].append({"key": key, "name": name, "value": amount})

    period_rows = [
        {**row, "thstrm_amount": row.get(amount_field), "frmtrm_amount": None}
        for row in rows if row.get("sj_div") == "CF"
    ]
    cash = cash_detail(period_rows, parse_amount)
    cashflow = [
        {"section": item["section"], "name": item["name"], "value": item["current"]}
        for item in cash["items"]
        if not item["total"] and item["current"] not in (None, 0)
    ]
    return {"accounts": accounts, "cashflow": cashflow}
