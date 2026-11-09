"""DART 계정 → 표준 항목 연결.

fnlttSinglAcntAll 응답의 행은 표준 계정 ID(account_id, 예: ifrs-full_Revenue)가 붙어 있어 ID를 먼저 쓰고,
ID가 없을 때만 계정 이름(공백 제거 후 정확히 일치)으로 보완한다. 손익계산서는 회사에 따라 IS 또는 CIS에 있어 둘 다 본다.
"""
from dataclasses import dataclass

INCOME = ("IS", "CIS")


@dataclass(frozen=True)
class Rule:
    field: str  # calc.models.YearFinancials 필드 이름
    label: str  # 화면에 보일 표준 항목 이름
    sj: tuple[str, ...]  # 찾아볼 재무제표 구분(BS 재무상태표, IS 손익, CIS 포괄손익, CF 현금흐름) — 앞에서부터
    ids: tuple[str, ...]  # 표준 계정 ID — 앞에서부터
    names: tuple[str, ...] = ()  # ID가 없는 경우의 계정 이름


RULES = (
    Rule("revenue", "매출액", INCOME, ("ifrs-full_Revenue",), ("매출액", "영업수익", "수익(매출액)", "매출")),
    Rule("operating_income", "영업이익", INCOME, ("dart_OperatingIncomeLoss",), ("영업이익", "영업이익(손실)")),
    Rule("net_income", "당기순이익", INCOME, ("ifrs-full_ProfitLoss",), ("당기순이익", "당기순이익(손실)", "당기순손익")),
    # 지배주주 항목은 포괄손익(ComprehensiveIncome...)과 이름이 같아 ID로만 찾는다
    Rule("net_income_parent", "지배주주 순이익", INCOME, ("ifrs-full_ProfitLossAttributableToOwnersOfParent",)),
    Rule("total_assets", "자산총계", ("BS",), ("ifrs-full_Assets",), ("자산총계",)),
    Rule("total_liabilities", "부채총계", ("BS",), ("ifrs-full_Liabilities",), ("부채총계",)),
    Rule("total_equity", "자본총계", ("BS",), ("ifrs-full_Equity",), ("자본총계",)),
    Rule("equity_parent", "지배주주 자본", ("BS",), ("ifrs-full_EquityAttributableToOwnersOfParent",),
         ("지배기업의소유지분", "지배기업소유주지분", "지배기업의소유주에게귀속되는자본")),
    Rule("current_assets", "유동자산", ("BS",), ("ifrs-full_CurrentAssets",), ("유동자산",)),
    Rule("current_liabilities", "유동부채", ("BS",), ("ifrs-full_CurrentLiabilities",), ("유동부채",)),
    Rule("receivables", "매출채권", ("BS",), ("ifrs-full_CurrentTradeReceivables", "ifrs-full_TradeAndOtherCurrentReceivables"),
         ("매출채권", "매출채권및기타채권")),
    Rule("inventory", "재고자산", ("BS",), ("ifrs-full_Inventories",), ("재고자산",)),
    Rule("cost_of_sales", "매출원가", INCOME, ("ifrs-full_CostOfSales",), ("매출원가",)),
    # 손익계산서에 이자비용이 따로 없는 기업이 많아 금융비용으로 대체하고 그 사실을 표시한다
    Rule("interest_expense", "이자비용(또는 금융비용)", INCOME, ("ifrs-full_InterestExpense", "ifrs-full_FinanceCosts"),
         ("이자비용", "금융비용", "금융원가")),
    # 2026-11-04 손익계산서 분석: 매출총이익·판관비·금융손익·세전이익·법인세 (없으면 화면에서 계산 가능한 것만 계산)
    Rule("gross_profit", "매출총이익", INCOME, ("ifrs-full_GrossProfit",), ("매출총이익", "매출총이익(손실)")),
    Rule("sga", "판매비와관리비", INCOME, ("dart_TotalSellingGeneralAdministrativeExpenses", "ifrs-full_SellingGeneralAndAdministrativeExpense"),
         ("판매비와관리비", "판매비와일반관리비")),
    Rule("finance_income", "금융수익", INCOME, ("ifrs-full_FinanceIncome",), ("금융수익",)),
    Rule("finance_costs", "금융비용", INCOME, ("ifrs-full_FinanceCosts",), ("금융비용", "금융원가")),
    Rule("pretax_income", "법인세비용차감전순이익", INCOME, ("ifrs-full_ProfitLossBeforeTax",),
         ("법인세비용차감전순이익", "법인세비용차감전순이익(손실)", "법인세차감전순이익")),
    Rule("income_tax", "법인세비용", INCOME, ("ifrs-full_IncomeTaxExpenseContinuingOperations",), ("법인세비용", "법인세비용(수익)")),
    # 2026-11-04 현금흐름 분석: 설비투자·주주환원·차입·법인세 납부·기말 현금 (지출 항목은 회사마다 부호가 달라 calc에서 절댓값)
    Rule("capex_ppe", "유형자산의 취득", ("CF",), ("ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",), ("유형자산의취득",)),
    Rule("capex_intangible", "무형자산의 취득", ("CF",), ("ifrs-full_PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",), ("무형자산의취득",)),
    Rule("dividends_paid", "배당금의 지급", ("CF",), ("ifrs-full_DividendsPaidClassifiedAsFinancingActivities", "ifrs-full_DividendsPaid"), ("배당금의지급", "배당금지급")),
    Rule("buyback", "자기주식의 취득", ("CF",), ("ifrs-full_PaymentsToAcquireOrRedeemEntitysShares", "dart_AcquisitionOfTreasuryShares"), ("자기주식의취득",)),
    Rule("borrowing_in", "차입금의 차입", ("CF",), ("ifrs-full_ProceedsFromBorrowingsClassifiedAsFinancingActivities",), ("차입금의차입", "단기차입금의차입", "장기차입금의차입")),
    Rule("borrowing_out", "차입금의 상환", ("CF",), ("ifrs-full_RepaymentsOfBorrowingsClassifiedAsFinancingActivities",), ("차입금의상환", "단기차입금의상환", "장기차입금의상환")),
    Rule("tax_paid", "법인세의 납부", ("CF",), ("ifrs-full_IncomeTaxesPaidRefundClassifiedAsOperatingActivities",), ("법인세의납부", "법인세납부")),
    Rule("cash_end", "기말 현금및현금성자산", ("CF",), ("dart_CashAndCashEquivalentsAtEndOfPeriodCf",), ("기말현금및현금성자산", "기말의현금및현금성자산")),
    Rule("cfo", "영업활동 현금흐름", ("CF",), ("ifrs-full_CashFlowsFromUsedInOperatingActivities",), ("영업활동현금흐름",)),
    Rule("cfi", "투자활동 현금흐름", ("CF",), ("ifrs-full_CashFlowsFromUsedInInvestingActivities",), ("투자활동현금흐름",)),
    Rule("cff", "재무활동 현금흐름", ("CF",), ("ifrs-full_CashFlowsFromUsedInFinancingActivities",), ("재무활동현금흐름",)),
)
RULES_BY_FIELD = {r.field: r for r in RULES}

# ID가 이자비용이 아니라 대체 항목일 때 붙일 안내
SUBSTITUTE_NOTES = {
    "ifrs-full_FinanceCosts": "이자비용 계정이 없어 금융비용으로 대체 (이자보상배율은 금융비용 기준, 외환·파생상품 손실이 포함될 수 있음)",
    "ifrs-full_TradeAndOtherCurrentReceivables": "매출채권 계정이 없어 매출채권 및 기타채권으로 대체",
}
SUBSTITUTE_NAMES = {
    "금융비용": SUBSTITUTE_NOTES["ifrs-full_FinanceCosts"],
    "금융원가": SUBSTITUTE_NOTES["ifrs-full_FinanceCosts"],
    "매출채권및기타채권": SUBSTITUTE_NOTES["ifrs-full_TradeAndOtherCurrentReceivables"],
}

# 매칭되지 않은 항목의 후보를 찾을 때 볼 이름 키워드
CANDIDATE_KEYWORDS = {
    "revenue": ("매출", "수익"), "operating_income": ("영업",), "net_income": ("순이익", "순손익"),
    "net_income_parent": ("지배",), "equity_parent": ("지배",), "receivables": ("채권",), "inventory": ("재고",),
    "cost_of_sales": ("원가",), "interest_expense": ("이자", "금융"), "current_assets": ("유동자산",),
    "current_liabilities": ("유동부채",), "gross_profit": ("총이익",), "sga": ("판매비", "관리비"),
    "finance_income": ("금융수익",), "finance_costs": ("금융비용", "금융원가"), "pretax_income": ("법인세", "세전"),
    "income_tax": ("법인세",),
}


@dataclass(frozen=True)
class Matched:
    row: dict
    by: str  # "id" | "name"
    note: str | None = None


def _norm(name: str) -> str:
    return "".join((name or "").split())


def parse_amount(text) -> float | None:
    """DART 금액 문자열(원 단위). 비어 있거나 '-'면 None."""
    if text is None:
        return None
    t = str(text).strip().replace(",", "")
    if t in ("", "-"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def find_row(rows: list[dict], rule: Rule) -> Matched | None:
    for account_id in rule.ids:  # 1) 표준 계정 ID
        for sj in rule.sj:
            for r in rows:
                if r.get("sj_div") == sj and r.get("account_id") == account_id:
                    # 대체 안내는 그 항목의 첫 ID가 아닐 때만(금융비용 항목 자체는 '이자비용 대체'가 아니다)
                    return Matched(r, "id", SUBSTITUTE_NOTES.get(account_id) if account_id != rule.ids[0] else None)
    names = {_norm(n) for n in rule.names}  # 2) ID가 없으면 이름
    for sj in rule.sj:
        for r in rows:
            if r.get("sj_div") == sj and _norm(r.get("account_nm", "")) in names:
                first = _norm(rule.names[0]) if rule.names else None
                return Matched(r, "name", SUBSTITUTE_NAMES.get(_norm(r["account_nm"])) if _norm(r["account_nm"]) != first else None)
    return None


COLUMNS = ("thstrm", "frmtrm", "bfefrmtrm")  # 당기, 전기, 전전기


def extract(rows: list[dict]) -> tuple[dict[str, dict], dict[str, Matched]]:
    """({열: {필드: 금액}}, {필드: 매칭 결과}). 매칭 못 한 필드는 두 번째 결과에 없다."""
    matched = {}
    for rule in RULES:
        m = find_row(rows, rule)
        if m:
            matched[rule.field] = m
    values = {col: {f: parse_amount(m.row.get(f"{col}_amount")) for f, m in matched.items()} for col in COLUMNS}
    return values, matched


def unmatched_candidates(rows: list[dict], missing_fields: list[str]) -> dict[str, list[str]]:
    """매칭 못 한 항목마다 이름에 관련 키워드가 든 계정을 보여줘 사람이 확인할 수 있게 한다."""
    out = {}
    for f in missing_fields:
        words = CANDIDATE_KEYWORDS.get(f, ())
        seen, names = set(), []
        for r in rows:
            if r.get("sj_div") in ("BS", "IS", "CIS", "CF") and any(w in r.get("account_nm", "") for w in words):
                key = (r["sj_div"], r["account_id"], r["account_nm"])
                if key not in seen:
                    seen.add(key)
                    names.append(f'{r["sj_div"]} {r["account_nm"]} [{r["account_id"]}]')
        out[f] = names[:8]
    return out
