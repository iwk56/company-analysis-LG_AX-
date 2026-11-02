"""경쟁사 비교 계산: 순위(동률·방향)·평균 대비·상위 절반 기준·제외·점 그래프."""
import pytest

from app.calc.models import NO_DATA, Metric
from app.comparison import COLUMN_DEFS, Entry, Excluded, build_comparison


def entry(name, revenue=100, growth=0.1, margin=0.1, roe=0.1, debt=1.0, target=False):
    def m(v):
        return Metric(v) if v is not None else Metric(None, NO_DATA)

    return Entry(name, name, "연결", None, {"revenue": m(revenue), "revenue_growth": m(growth),
                                           "operating_margin": m(margin), "roe": m(roe), "debt_ratio": m(debt)}, target)


def cell(comp, name, key):
    return next(r for r in comp["rows"] if r["corp_name"] == name)["values"][key]


def test_rank_direction_debt_ratio_lower_is_first_and_others_higher():
    comp = build_comparison(2025, entry("A", revenue=300, debt=2.0, target=True), [entry("B", revenue=100, debt=0.5), entry("C", revenue=200, debt=1.0)])
    assert [cell(comp, n, "revenue")["rank"] for n in "ABC"] == [1, 3, 2]
    assert [cell(comp, n, "debt_ratio")["rank"] for n in "ABC"] == [3, 1, 2]


def test_ties_share_rank_and_next_rank_is_skipped():
    comp = build_comparison(2025, entry("A", margin=0.2, target=True), [entry("B", margin=0.2), entry("C", margin=0.1)])
    assert [cell(comp, n, "operating_margin")["rank"] for n in "ABC"] == [1, 1, 3]


def test_average_includes_target_and_vs_average_marks():
    comp = build_comparison(2025, entry("A", roe=0.3, target=True), [entry("B", roe=0.1), entry("C", roe=0.2)])
    assert comp["averages"]["roe"] == pytest.approx(0.2)
    assert [cell(comp, n, "roe")["vs_average"] for n in "ABC"] == ["above", "below", "same"]


def test_na_values_are_left_out_of_rank_and_average():
    comp = build_comparison(2025, entry("A", roe=0.3, target=True), [entry("B", roe=None), entry("C", roe=0.1)])
    assert comp["ranked_counts"]["roe"] == 2 and comp["averages"]["roe"] == pytest.approx(0.2)
    b = cell(comp, "B", "roe")
    assert b["rank"] is None and b["vs_average"] is None and b["na_reason"] == NO_DATA


def test_single_comparable_company_gets_no_rank():
    comp = build_comparison(2025, entry("A", roe=0.3, target=True), [entry("B", roe=None)])
    assert cell(comp, "A", "roe")["rank"] is None
    assert "ROE" in comp["position"]["unavailable"] and comp["position"]["better"] == []


def test_position_uses_average_comparison_and_debt_ratio_lower_is_better():
    comp = build_comparison(2025, entry("A", revenue=300, growth=0.0, margin=0.3, roe=0.3, debt=2.0, target=True),
                            [entry("B", revenue=100, growth=0.1, margin=0.1, roe=0.1, debt=1.0)])
    pos = comp["position"]
    assert pos["better"] == ["매출액", "영업이익률", "ROE"] and pos["worse"] == ["매출액증가율", "부채비율"]
    assert pos["text"] == "A: 비교한 5개 중 3개 지표가 평균보다 좋음(매출액, 영업이익률, ROE), 2개는 평균보다 낮음(매출액증가율, 부채비율)."
    # 표의 ▲▼와 같은 기준: 부채비율 A는 평균보다 높음(above)이지만 '좋음'이 아니다
    assert cell(comp, "A", "debt_ratio")["vs_average"] == "above"


def test_position_low_debt_is_better_and_equal_to_average_is_same():
    comp = build_comparison(2025, entry("A", debt=0.5, roe=0.2, target=True), [entry("B", debt=1.5, roe=0.2)])
    pos = comp["position"]
    assert "부채비율" in pos["better"] and "ROE" in pos["same"]
    assert "평균과 같음(" in pos["text"] and "ROE" in pos["text"].split("평균과 같음(")[1]


def test_position_is_independent_of_rank_ties_and_odd_counts():
    # 3곳 중 2위여도 평균보다 높으면 '좋음' (순위 기준이 아니다)
    comp = build_comparison(2025, entry("A", revenue=200, target=True), [entry("B", revenue=1000), entry("C", revenue=10)])
    assert cell(comp, "A", "revenue")["rank"] == 2 and cell(comp, "A", "revenue")["vs_average"] == "below"
    comp = build_comparison(2025, entry("A", revenue=500, target=True), [entry("B", revenue=1000), entry("C", revenue=10)])
    assert cell(comp, "A", "revenue")["rank"] == 2 and cell(comp, "A", "revenue")["vs_average"] == "below"
    comp = build_comparison(2025, entry("A", revenue=600, target=True), [entry("B", revenue=1000), entry("C", revenue=10)])
    assert cell(comp, "A", "revenue")["rank"] == 2 and cell(comp, "A", "revenue")["vs_average"] == "above"
    assert "매출액" in comp["position"]["better"]


def test_excluded_and_scatter():
    comp = build_comparison(2025, entry("A", target=True), [entry("B", growth=None), Excluded("X", "X사", "데이터 부족으로 제외 (2025 사업연도 자료 없음)")])
    assert comp["excluded"] == [{"corp_code": "X", "corp_name": "X사", "reason": "데이터 부족으로 제외 (2025 사업연도 자료 없음)"}]
    assert [p["corp_name"] for p in comp["scatter"]] == ["A"] and comp["scatter"][0]["is_target"]
    assert [r["corp_name"] for r in comp["rows"]] == ["A", "B"]


def test_columns_come_from_definitions_so_5b_can_add_more():
    comp = build_comparison(2025, entry("A", target=True), [entry("B")])
    assert [c["key"] for c in comp["columns"]] == [d.key for d in COLUMN_DEFS]
    assert all(set(r["values"]) == {d.key for d in COLUMN_DEFS} for r in comp["rows"])
