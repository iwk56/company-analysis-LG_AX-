"""재무 계산 테스트 — 예시 숫자(억 원)로 손계산한 값과 비교한다."""
import pytest

from app.calc import analyze
from app.calc.cashflow import PATTERNS, classify_cashflow
from app.calc.models import (
    CAPITAL_IMPAIRED,
    FIRST_YEAR,
    NO_DATA,
    ZERO_DENOMINATOR,
    YearFinancials as Y,
)
from app.calc.ratios import compute_ratios

Y2022 = Y(2022, revenue=1000, operating_income=100, net_income=80, net_income_parent=70,
          total_assets=2000, total_liabilities=1200, total_equity=800, equity_parent=700,
          current_assets=900, current_liabilities=600, receivables=200, inventory=150,
          cost_of_sales=700, interest_expense=20, cfo=150, cfi=-100, cff=-30)
Y2023 = Y(2023, revenue=1100, operating_income=99, net_income=88, net_income_parent=77,
          total_assets=2200, total_liabilities=1300, total_equity=900, equity_parent=800,
          current_assets=1000, current_liabilities=625, receivables=240, inventory=170,
          cost_of_sales=770, interest_expense=25, cfo=180, cfi=-120, cff=-40)


def approx(x):
    return pytest.approx(x, rel=1e-9)


# ---------- 5대 비율 ----------
def test_ratios_with_averages():
    r = compute_ratios(Y2023, Y2022)
    assert r["operating_margin"].value == approx(0.09)
    assert r["net_margin"].value == approx(0.08)
    assert r["roe"].value == approx(77 / 750)  # 평균 지배주주 자본 (700+800)/2
    assert r["roa"].value == approx(88 / 2100)  # 평균 총자산 (2000+2200)/2
    assert r["debt_ratio"].value == approx(1300 / 900)
    assert r["current_ratio"].value == approx(1.6)
    assert r["interest_coverage"].value == approx(99 / 25)
    assert r["asset_turnover"].value == approx(1100 / 2100)
    assert r["receivable_turnover"].value == approx(5.0)  # 1100 ÷ 평균 220
    assert r["inventory_turnover"].value == approx(770 / 160)  # 매출원가 ÷ 평균 재고 160
    assert r["revenue_growth"].value == approx(0.1)
    assert r["operating_income_growth"].value == approx(-0.01)
    assert r["asset_growth"].value == approx(0.1)
    assert not any(m.year_end_only for m in r.values())


def test_first_year_uses_year_end_value_and_is_marked():
    r = compute_ratios(Y2022, None)
    assert r["roe"].value == approx(70 / 700) and r["roe"].year_end_only
    assert r["roa"].value == approx(80 / 2000) and r["roa"].year_end_only
    assert r["receivable_turnover"].value == approx(5.0) and r["receivable_turnover"].year_end_only
    assert r["operating_margin"].year_end_only is False  # 평균을 안 쓰는 비율은 표시 안 함
    for key in ("revenue_growth", "operating_income_growth", "asset_growth"):
        assert r[key].value is None and r[key].na_reason == FIRST_YEAR


def test_zero_denominators_are_not_applicable():
    cur = Y(2023, revenue=0, operating_income=5, interest_expense=0, current_liabilities=0,
            current_assets=10, receivables=0, inventory=0, cost_of_sales=1, net_income=1)
    r = compute_ratios(cur, None)
    for key in ("operating_margin", "net_margin", "interest_coverage", "current_ratio",
                "receivable_turnover", "inventory_turnover"):
        assert r[key].value is None and r[key].na_reason == ZERO_DENOMINATOR, key


def test_capital_impairment_is_not_applicable():
    cur = Y(2023, total_liabilities=500, total_equity=-100, net_income_parent=10, equity_parent=-100)
    r = compute_ratios(cur, None)
    assert r["debt_ratio"].value is None and r["debt_ratio"].na_reason == CAPITAL_IMPAIRED
    assert r["roe"].value is None and r["roe"].na_reason == CAPITAL_IMPAIRED


def test_loss_year_shows_negative_numbers_not_na():
    cur = Y(2023, revenue=1000, operating_income=-30, net_income=-52, net_income_parent=-50,
            equity_parent=625, total_assets=2000, interest_expense=20)
    r = compute_ratios(cur, None)
    assert r["net_margin"].value == approx(-0.052)
    assert r["roe"].value == approx(-0.08)
    assert r["interest_coverage"].value == approx(-1.5)


def test_missing_values_are_no_data():
    r = compute_ratios(Y(2023), None)
    assert all(m.value is None and m.na_reason in (NO_DATA, FIRST_YEAR) for m in r.values())


def test_operating_income_growth_loss_to_profit_and_back():
    up = compute_ratios(Y(2023, operating_income=30), Y(2022, operating_income=-20))
    assert up["operating_income_growth"].value is None and up["operating_income_growth"].na_reason == "흑자전환"
    down = compute_ratios(Y(2023, operating_income=-20), Y(2022, operating_income=30))
    assert down["operating_income_growth"].na_reason == "적자전환"
    still = compute_ratios(Y(2023, operating_income=-5), Y(2022, operating_income=-20))
    assert still["operating_income_growth"].na_reason == "적자지속"
    zero = compute_ratios(Y(2023, operating_income=30), Y(2022, operating_income=0))
    assert zero["operating_income_growth"].na_reason == ZERO_DENOMINATOR


def test_revenue_growth_needs_positive_previous_revenue():
    r = compute_ratios(Y(2023, revenue=100), Y(2022, revenue=0))
    assert r["revenue_growth"].na_reason == ZERO_DENOMINATOR


def test_gap_year_is_treated_as_first_year():
    out = analyze([Y(2020, revenue=100), Y(2022, revenue=200)])
    assert out[2022].ratios["revenue_growth"].na_reason == FIRST_YEAR


# ---------- 듀퐁 ----------
def test_dupont_product_equals_roe_and_picks_main_driver():
    out = analyze([Y2022, Y2023])
    d = out[2023].dupont
    assert d["net_margin"].value == approx(0.07)
    assert d["asset_turnover"].value == approx(1100 / 2100)
    assert d["leverage"].value == approx(2100 / 750)
    assert d["roe"].value == approx(out[2023].ratios["roe"].value)  # 지배주주 기준이라 정확히 같다
    assert out[2022].dupont["roe"].value == approx(0.1) and out[2022].dupont["roe"].year_end_only
    # 전년 대비 변화율: 순이익률 0%, 회전율 +4.76%, 레버리지 -2% → 총자산회전율
    assert out[2023].dupont_driver.factor == "총자산회전율"
    assert out[2023].dupont_driver.changes["재무레버리지"] == approx(-0.02)
    assert out[2022].dupont_driver is None and out[2022].dupont_driver_na


def test_dupont_roe_matches_even_with_minority_interest():
    out = analyze([Y2022, Y2023])  # 당기순이익 88 ≠ 지배주주 77
    assert out[2023].dupont["roe"].value == approx(77 / 750)


def test_dupont_driver_not_judged_when_previous_factor_is_zero():
    prev = Y(2022, revenue=1000, net_income_parent=0, total_assets=2000, equity_parent=700)
    cur = Y(2023, revenue=1000, net_income_parent=50, total_assets=2000, equity_parent=700)
    out = analyze([prev, cur])
    assert out[2023].dupont_driver is None and "0" in out[2023].dupont_driver_na


# ---------- 현금흐름 패턴 ----------
@pytest.mark.parametrize("signs,name", list(PATTERNS.items()))
def test_all_eight_cashflow_patterns(signs, name):
    flows = [1 if s == "+" else -1 for s in signs]
    assert classify_cashflow(Y(2023, cfo=flows[0], cfi=flows[1], cff=flows[2])) == (name, None)


def test_there_are_eight_distinct_patterns():
    assert len(PATTERNS) == 8 and len(set(PATTERNS.values())) == 8


def test_cashflow_zero_or_missing_is_not_classified():
    assert classify_cashflow(Y(2023, cfo=0, cfi=-1, cff=-1))[0] is None
    assert classify_cashflow(Y(2023, cfo=1, cfi=-1))[0] is None


# ---------- 신호등 ----------
def sig(prev: Y, cur: Y, key: str):
    s = analyze([prev, cur])[cur.year].signals[key]
    return s.level if s else None


def rev(cur_rev):
    return sig(Y(2022, revenue=100), Y(2023, revenue=cur_rev), "revenue_growth")


def test_revenue_growth_boundaries():
    assert rev(100) == "양호"  # 정확히 0%
    assert rev(99.9) == "주의"
    assert rev(90) == "주의"  # 정확히 -10%
    assert rev(89.9) == "위험"


def margin(prev_pct, cur_pct):
    return sig(Y(2022, revenue=1000, operating_income=prev_pct * 10),
               Y(2023, revenue=1000, operating_income=cur_pct * 10), "operating_margin")


def test_operating_margin_boundaries():
    assert margin(10, 10) == "양호"  # 같음
    assert margin(10, 12) == "양호"
    assert margin(10, 9.9) == "주의"
    assert margin(10, 7) == "주의"  # 정확히 3%p 하락
    assert margin(10, 6.9) == "위험"
    assert margin(1, 0) == "주의"  # 영업이익 0은 적자가 아님 (1%p 하락)
    assert margin(10, 0) == "위험"  # 10%p 하락
    assert margin(-5, -2) == "위험"  # 적자는 전년보다 개선돼도 위험


def debt(prev_ratio, cur_ratio):
    return sig(Y(2022, total_liabilities=prev_ratio * 100, total_equity=100),
               Y(2023, total_liabilities=cur_ratio * 100, total_equity=100), "debt_ratio")


def test_debt_ratio_boundaries():
    assert debt(1.0, 1.0) == "양호"
    assert debt(1.0, 0.8) == "양호"
    assert debt(1.0, 1.1) == "주의"
    assert debt(1.0, 1.5) == "주의"  # 정확히 50%p 상승
    assert debt(1.0, 1.51) == "위험"
    assert debt(2.5, 2.0) == "양호"  # 정확히 200%는 초과가 아님
    assert debt(2.5, 2.4) == "위험"  # 200% 초과가 전년 대비 개선보다 우선
    assert debt(1.9, 2.01) == "위험"


def cf(prev_cfo, cur_cfo):
    return sig(Y(2022, cfo=prev_cfo), Y(2023, cfo=cur_cfo), "operating_cashflow")


def test_operating_cashflow_boundaries():
    assert cf(100, 101) == "양호"
    assert cf(100, 99) == "주의"
    assert cf(100, 100) == "주의"  # 전년과 같으면 주의
    assert cf(100, 0) == "주의"  # 0은 적자가 아님
    assert cf(100, -1) == "위험"
    assert cf(-50, 10) == "양호"  # 적자에서 흑자로 증가


def test_first_year_only_absolute_danger_rules_apply():
    ok = analyze([Y(2023, revenue=100, operating_income=10, total_liabilities=100, total_equity=100, cfo=5)])[2023]
    assert all(v is None for v in ok.signals.values())
    bad = analyze([Y(2023, revenue=100, operating_income=-10, total_liabilities=300, total_equity=100, cfo=-5)])[2023]
    assert bad.signals["operating_margin"].level == "위험"
    assert bad.signals["debt_ratio"].level == "위험"
    assert bad.signals["operating_cashflow"].level == "위험"
    assert bad.signals["revenue_growth"] is None


def test_full_example_signals_and_pattern():
    out = analyze([Y2022, Y2023])[2023]
    assert out.cashflow_pattern == "우량형"
    assert {k: v.level for k, v in out.signals.items()} == {
        "revenue_growth": "양호",
        "operating_margin": "주의",  # 10% → 9%
        "debt_ratio": "양호",  # 150% → 144.4%
        "operating_cashflow": "양호",  # 150 → 180
    }
