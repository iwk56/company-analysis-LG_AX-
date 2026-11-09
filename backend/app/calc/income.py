"""손익계산서 분석 (2026-11-04) — 한 해의 경영성과를 '매출 → 매출총이익 → 영업이익 → 세전이익 → 순이익' 단계로 본다.

- 공시에 없는 단계는 계산 가능한 것만 계산한다: 매출총이익 = 매출 − 매출원가, 판관비 = 매출총이익 − 영업이익(기타영업손익 포함일 수 있어 표시).
- 영업외손익 = 세전이익 − 영업이익, 그중 금융손익 = 금융수익 − 금융비용, 나머지는 '기타 영업외손익(지분법·외환 등)'.
- 비율은 모두 매출 대비(공통형 손익계산서). 유효세율 = 법인세 ÷ 세전이익.
- 영업이익 변화 분해: Δ영업이익 = Δ매출총이익 − Δ판관비. 매출총이익 변화는 다시 '매출이 늘어서' + '원가율이 바뀌어서'로 나눈다.
"""
from .models import YearFinancials


def _sub(a, b):
    return None if a is None or b is None else a - b


def _ratio(a, b):
    return None if a is None or not b else a / b


def statement(y: YearFinancials) -> dict:
    """한 해의 손익 단계(원)와 매출 대비 비율. 계산으로 채운 값은 derived에 이름을 남긴다."""
    derived = []
    gross = y.gross_profit
    if gross is None and y.revenue is not None and y.cost_of_sales is not None:
        gross = y.revenue - y.cost_of_sales
        derived.append("gross_profit")
    cost = y.cost_of_sales if y.cost_of_sales is not None else _sub(y.revenue, gross)
    sga = y.sga
    if sga is None and gross is not None and y.operating_income is not None:
        sga = gross - y.operating_income
        derived.append("sga")
    other_op = None if y.sga is None else _sub(_sub(gross, y.sga), y.operating_income)  # 판관비를 공시했을 때 나머지(기타영업손익)
    non_op = _sub(y.pretax_income, y.operating_income)
    fin_net = _sub(y.finance_income, y.finance_costs)
    other_non_op = _sub(non_op, fin_net)
    rows = {
        "revenue": y.revenue, "cost_of_sales": cost, "gross_profit": gross, "sga": sga, "other_operating": other_op,
        "operating_income": y.operating_income, "non_operating": non_op, "finance_net": fin_net, "other_non_operating": other_non_op,
        "pretax_income": y.pretax_income, "income_tax": y.income_tax, "net_income": y.net_income,
    }
    margins = {k: _ratio(v, y.revenue) for k, v in rows.items() if k != "revenue"}
    return {"rows": rows, "margins": margins, "effective_tax_rate": _ratio(y.income_tax, y.pretax_income)
            if (y.pretax_income or 0) > 0 else None, "derived": derived}


def bridge(cur: dict, prev: dict) -> dict | None:
    """전년 대비 영업이익 변화를 나눈다. 필요한 값이 없으면 None.
    volume: 전년 매출총이익률로 매출 증가분이 낸 이익, margin: 매출총이익률 변화의 효과, sga: 판관비 증감(늘면 이익 감소)."""
    c, p = cur["rows"], prev["rows"]
    need = (c["revenue"], p["revenue"], c["gross_profit"], p["gross_profit"], c["sga"], p["sga"], c["operating_income"], p["operating_income"])
    if any(v is None for v in need) or not p["revenue"]:
        return None
    gm_prev = p["gross_profit"] / p["revenue"]
    volume = (c["revenue"] - p["revenue"]) * gm_prev
    margin = c["gross_profit"] - p["gross_profit"] - volume
    sga = -(c["sga"] - p["sga"])
    total = c["operating_income"] - p["operating_income"]
    return {"total": total, "volume": volume, "margin": margin, "sga": sga, "other": total - volume - margin - sga}


def compute_income(years: dict[int, YearFinancials]) -> dict[str, dict]:
    """연도(문자열) → {statement, bridge(전년이 있을 때)}."""
    st = {yr: statement(y) for yr, y in years.items()}
    return {str(yr): {**st[yr], "bridge": bridge(st[yr], st[yr - 1]) if yr - 1 in st else None} for yr in sorted(st)}
