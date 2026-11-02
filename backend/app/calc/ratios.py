"""5대 재무비율(시장가치 제외) — docs/spec.md 3장 '5대 재무비율'."""
from .models import (
    CAPITAL_IMPAIRED,
    FIRST_YEAR,
    NEGATIVE_DENOMINATOR,
    NO_DATA,
    ZERO_DENOMINATOR,
    Metric,
    YearFinancials,
)


def divide(num: float | None, den: float | None, negative_label: str = NEGATIVE_DENOMINATOR,
           year_end_only: bool = False) -> Metric:
    """분모가 0이거나 음수면 숫자 대신 해당 없음 사유를 돌려준다."""
    if num is None or den is None:
        return Metric(None, NO_DATA, year_end_only)
    if den == 0:
        return Metric(None, ZERO_DENOMINATOR, year_end_only)
    if den < 0:
        return Metric(None, negative_label, year_end_only)
    return Metric(num / den, None, year_end_only)


def average(cur: float | None, prev: float | None) -> tuple[float | None, bool]:
    """(기초+기말)÷2. 전기 값이 없으면(첫 연도) 기말 값만 쓰고 True로 표시한다."""
    if cur is None:
        return None, False
    if prev is None:
        return cur, True
    return (cur + prev) / 2, False


def growth(cur: float | None, prev: float | None, has_prior_year: bool, abs_denominator: bool = False) -> Metric:
    if not has_prior_year:
        return Metric(None, FIRST_YEAR)
    if cur is None or prev is None:
        return Metric(None, NO_DATA)
    return divide(cur - prev, abs(prev) if abs_denominator else prev)


def compute_ratios(cur: YearFinancials, prev: YearFinancials | None) -> dict[str, Metric]:
    p = prev  # 전기 연도 자료(없으면 None)

    def avg(field: str) -> tuple[float | None, bool]:
        return average(getattr(cur, field), getattr(p, field) if p else None)

    avg_equity_parent, eq_end_only = avg("equity_parent")
    avg_assets, assets_end_only = avg("total_assets")
    avg_receivables, rec_end_only = avg("receivables")
    avg_inventory, inv_end_only = avg("inventory")

    return {
        # 수익성
        "operating_margin": divide(cur.operating_income, cur.revenue),
        "net_margin": divide(cur.net_income, cur.revenue),
        "roe": divide(cur.net_income_parent, avg_equity_parent, CAPITAL_IMPAIRED, eq_end_only),
        "roa": divide(cur.net_income, avg_assets, year_end_only=assets_end_only),
        # 안정성
        "debt_ratio": divide(cur.total_liabilities, cur.total_equity, CAPITAL_IMPAIRED),
        "current_ratio": divide(cur.current_assets, cur.current_liabilities),
        "interest_coverage": divide(cur.operating_income, cur.interest_expense),
        # 활동성
        "asset_turnover": divide(cur.revenue, avg_assets, year_end_only=assets_end_only),
        "receivable_turnover": divide(cur.revenue, avg_receivables, year_end_only=rec_end_only),
        "inventory_turnover": divide(cur.cost_of_sales, avg_inventory, year_end_only=inv_end_only),
        # 성장성 (영업이익증가율은 전기 영업이익의 절댓값으로 나눠, 적자→흑자도 증가로 나온다)
        "revenue_growth": growth(cur.revenue, p.revenue if p else None, p is not None),
        "operating_income_growth": growth(
            cur.operating_income, p.operating_income if p else None, p is not None, abs_denominator=True
        ),
        "asset_growth": growth(cur.total_assets, p.total_assets if p else None, p is not None),
    }
