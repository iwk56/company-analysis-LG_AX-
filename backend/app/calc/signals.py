"""신호등(전년 대비 기준) — docs/spec.md 3장 '신호등'.

확정한 겹침 규칙(2026-11-02): 위험 조건(적자·부채비율 200% 초과)이 전년 대비 판정보다 우선하고,
영업현금흐름이 0이거나 전년과 같으면 '주의'. 전기 자료가 없으면 절대 기준 위험만 판정하고 나머지는 None.
경계값 부동소수 오차를 막으려고 차이는 소수 9자리로 반올림해 비교한다.
"""
from .models import Metric, Signal, YearFinancials

GOOD, WARN, DANGER = "양호", "주의", "위험"


def _r(x: float) -> float:
    return round(x, 9)


def revenue_growth_signal(growth: Metric) -> Signal | None:
    if growth.value is None:
        return None
    g = _r(growth.value)
    if g >= 0:
        return Signal(GOOD, "매출이 전년 이상")
    if g >= -0.10:
        return Signal(WARN, "매출이 전년보다 10% 이내 감소")
    return Signal(DANGER, "매출이 전년보다 10% 넘게 감소")


def operating_margin_signal(cur: YearFinancials, margin: Metric, prev_margin: Metric | None) -> Signal | None:
    if cur.operating_income is not None and cur.operating_income < 0:
        return Signal(DANGER, "영업적자")
    if margin.value is None or prev_margin is None or prev_margin.value is None:
        return None
    diff = _r(margin.value - prev_margin.value)
    if diff >= 0:
        return Signal(GOOD, "영업이익률이 전년과 같거나 높음")
    if diff >= -0.03:
        return Signal(WARN, "영업이익률이 전년보다 3%p 이내 하락")
    return Signal(DANGER, "영업이익률이 전년보다 3%p 넘게 하락")


def debt_ratio_signal(debt: Metric, prev_debt: Metric | None) -> Signal | None:
    if debt.value is None:
        return None
    if _r(debt.value) > 2.0:
        return Signal(DANGER, "부채비율 200% 초과")
    if prev_debt is None or prev_debt.value is None:
        return None
    diff = _r(debt.value - prev_debt.value)
    if diff <= 0:
        return Signal(GOOD, "부채비율이 전년과 같거나 낮음")
    if diff <= 0.5:
        return Signal(WARN, "부채비율이 전년보다 50%p 이내 상승")
    return Signal(DANGER, "부채비율이 전년보다 50%p 넘게 상승")


def operating_cashflow_signal(cur: YearFinancials, prev: YearFinancials | None) -> Signal | None:
    if cur.cfo is None:
        return None
    if cur.cfo < 0:
        return Signal(DANGER, "영업현금흐름 적자")
    if cur.cfo == 0:
        return Signal(WARN, "영업현금흐름 0")
    if prev is None or prev.cfo is None:
        return None
    if cur.cfo > prev.cfo:
        return Signal(GOOD, "영업현금흐름 흑자, 전년보다 증가")
    return Signal(WARN, "영업현금흐름 흑자, 전년과 같거나 감소")
