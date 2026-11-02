"""재무 계산: 표준 항목(YearFinancials) → 비율·듀퐁·현금흐름 패턴·신호등. 숫자는 모두 여기서 코드로 계산한다."""
from .cashflow import classify_cashflow
from .dupont import compute_dupont, find_main_driver
from .models import YearAnalysis, YearFinancials
from .ratios import compute_ratios
from .signals import (
    debt_ratio_signal,
    operating_cashflow_signal,
    operating_margin_signal,
    revenue_growth_signal,
)


def analyze(years: list[YearFinancials]) -> dict[int, YearAnalysis]:
    """연도별 분석. 바로 앞 연도(year-1)가 없으면 그 해는 첫 연도처럼 처리한다."""
    by_year = {y.year: y for y in years}
    ratios_by_year, dupont_by_year, result = {}, {}, {}
    for year in sorted(by_year):
        prev = by_year.get(year - 1)
        ratios_by_year[year] = compute_ratios(by_year[year], prev)
        dupont_by_year[year] = compute_dupont(by_year[year], prev)

    for year in sorted(by_year):
        cur, prev = by_year[year], by_year.get(year - 1)
        r, pr = ratios_by_year[year], ratios_by_year.get(year - 1)
        driver, driver_na = find_main_driver(dupont_by_year[year], dupont_by_year.get(year - 1))
        pattern, pattern_na = classify_cashflow(cur)
        result[year] = YearAnalysis(
            year=year,
            ratios=r,
            dupont=dupont_by_year[year],
            dupont_driver=driver,
            dupont_driver_na=driver_na,
            cashflow_pattern=pattern,
            cashflow_na=pattern_na,
            signals={
                "revenue_growth": revenue_growth_signal(r["revenue_growth"]),
                "operating_margin": operating_margin_signal(cur, r["operating_margin"], pr["operating_margin"] if pr else None),
                "debt_ratio": debt_ratio_signal(r["debt_ratio"], pr["debt_ratio"] if pr else None),
                "operating_cashflow": operating_cashflow_signal(cur, prev),
            },
        )
    return result
