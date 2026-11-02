"""듀퐁 분석 — docs/spec.md 3장 '듀퐁 분석'.

확정한 해석(2026-11-02): 세 요소 모두 지배주주 기준으로 통일해 곱이 5대 비율의 ROE와 정확히 같다.
  순이익률 = 지배주주 순이익 ÷ 매출액
  총자산회전율 = 매출액 ÷ 평균 총자산
  재무레버리지 = 평균 총자산 ÷ 평균 지배주주 자본
'전년 대비 가장 크게 변한 요소'는 요소별 전년 대비 변화율(%)의 절댓값이 가장 큰 것.
"""
from .models import CAPITAL_IMPAIRED, NO_DATA, DupontDriver, Metric, YearFinancials
from .ratios import average, divide

FACTORS = ("net_margin", "asset_turnover", "leverage")
FACTOR_NAMES = {"net_margin": "순이익률", "asset_turnover": "총자산회전율", "leverage": "재무레버리지"}


def compute_dupont(cur: YearFinancials, prev: YearFinancials | None) -> dict[str, Metric]:
    avg_assets, assets_end_only = average(cur.total_assets, prev.total_assets if prev else None)
    avg_equity, equity_end_only = average(cur.equity_parent, prev.equity_parent if prev else None)

    parts = {
        "net_margin": divide(cur.net_income_parent, cur.revenue),
        "asset_turnover": divide(cur.revenue, avg_assets, year_end_only=assets_end_only),
        "leverage": divide(avg_assets, avg_equity, CAPITAL_IMPAIRED, assets_end_only or equity_end_only),
    }
    if all(m.value is not None for m in parts.values()):
        roe = parts["net_margin"].value * parts["asset_turnover"].value * parts["leverage"].value
        parts["roe"] = Metric(roe, None, assets_end_only or equity_end_only)
    else:
        reason = next(m.na_reason for m in parts.values() if m.value is None)
        parts["roe"] = Metric(None, reason)
    return parts


def find_main_driver(cur: dict[str, Metric], prev: dict[str, Metric] | None) -> tuple[DupontDriver | None, str | None]:
    """(주된 요소, 비교 못 한 사유). 세 요소를 모두 비교할 수 있을 때만 판정한다."""
    if prev is None:
        return None, "첫 연도라 전년 비교 불가"
    changes: dict[str, float] = {}
    for f in FACTORS:
        c, p = cur[f].value, prev[f].value
        if c is None or p is None:
            return None, NO_DATA
        if p == 0:
            return None, "전년 값이 0이라 변화율 계산 불가"
        changes[f] = (c - p) / abs(p)
    top = max(FACTORS, key=lambda f: abs(changes[f]))
    return DupontDriver(FACTOR_NAMES[top], {FACTOR_NAMES[f]: v for f, v in changes.items()}), None
