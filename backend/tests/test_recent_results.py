"""최근 실적 박스 테스트 — DART를 부르지 않는다 (가짜 응답)."""
import asyncio
from datetime import date

import pytest

from app.fin_collect import CompanyFinancials
from app.recent_results import NOT_FILED, collect_recent

TODAY = date(2026, 11, 2)


def run(coro):
    return asyncio.run(coro)


class FakeFetcher:
    def __init__(self, filings):
        self.filings, self.calls = filings, []

    async def fetch(self, corp_code, year, fs_div, reprt_code="11011"):
        self.calls.append((year, fs_div, reprt_code))
        return self.filings.get((year, fs_div, reprt_code), {"status": "013", "message": "no data", "list": []})


def interim(cur, prior, cur_3m=999, prior_3m=999, rcept="RQ", net_income_name="반기순이익"):
    """cur/prior: {revenue, operating_income, net_income_parent, net_income} 누적 값. 3개월 값은 일부러 다른 값을 넣어 섞이면 드러나게 한다."""
    ids = {"revenue": ("ifrs-full_Revenue", "매출액"), "operating_income": ("dart_OperatingIncomeLoss", "영업이익"),
           "net_income": ("ifrs-full_ProfitLoss", net_income_name),
           "net_income_parent": ("ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업의 소유주지분")}
    rows = []
    for key, (aid, nm) in ids.items():
        row = {"rcept_no": rcept, "sj_div": "CIS", "account_id": aid, "account_nm": nm,
               "thstrm_amount": str(cur_3m), "frmtrm_q_amount": str(prior_3m)}
        if cur.get(key) is not None:
            row["thstrm_add_amount"] = str(cur[key])
        if prior.get(key) is not None:
            row["frmtrm_add_amount"] = str(prior[key])
        rows.append(row)
    return {"status": "000", "message": "정상", "list": rows}


def company(basis="연결", latest=2025):
    return CompanyFinancials(corp_code="c", basis=basis, latest_year=latest, fs_div="CFS" if basis == "연결" else "OFS")


CUR = {"revenue": 1000, "operating_income": 300, "net_income_parent": 250, "net_income": 260}
PRIOR = {"revenue": 400, "operating_income": 40, "net_income_parent": 100, "net_income": 105}


def test_half_year_cumulative_compared_with_same_period_last_year():
    f = FakeFetcher({(2026, "CFS", "11012"): interim(CUR, PRIOR)})
    r, reason = run(collect_recent(f, company(), TODAY))
    assert reason is None and r.report_name == "반기" and r.year == 2026 and r.basis == "연결"
    assert r.period_current == "2026.01~06" and r.period_prior == "2025.01~06"
    assert r.current["revenue"] == 1000 and r.prior["revenue"] == 400  # 3개월 값(999)이 아니라 누적
    assert r.changes["revenue"].value == pytest.approx(1.5)             # (1000-400)/400
    assert r.changes["operating_income"].value == pytest.approx(6.5)    # (300-40)/40
    assert r.changes["net_income_parent"].value == pytest.approx(1.5)   # (250-100)/100
    assert r.operating_margin_current.value == pytest.approx(0.3) and r.operating_margin_prior.value == pytest.approx(0.1)
    assert r.changes["operating_margin"].value == pytest.approx(0.2)    # +20.0%p
    assert r.rcept_no == "RQ"
    assert f.calls == [(2026, "CFS", "11014"), (2026, "CFS", "11012")]  # 3분기 먼저 찾아보고 없으면 반기


def test_third_quarter_is_preferred_and_covers_nine_months():
    f = FakeFetcher({(2026, "CFS", "11014"): interim(CUR, PRIOR, rcept="Q3"), (2026, "CFS", "11012"): interim(CUR, PRIOR, rcept="H1")})
    r, _ = run(collect_recent(f, company(), TODAY))
    assert r.report_name == "3분기" and r.period_current == "2026.01~09" and r.period_prior == "2025.01~09" and r.rcept_no == "Q3"
    assert f.calls == [(2026, "CFS", "11014")]  # 3분기가 있으면 반기는 부르지 않는다


def test_no_report_yet_returns_reason():
    r, reason = run(collect_recent(FakeFetcher({}), company(), TODAY))
    assert r is None and reason == NOT_FILED


def test_periods_not_ended_yet_are_not_requested():
    f = FakeFetcher({})
    run(collect_recent(f, company(), date(2026, 8, 20)))   # 반기는 끝났고 3분기는 아직
    assert f.calls == [(2026, "CFS", "11012")]
    f2 = FakeFetcher({})
    run(collect_recent(f2, company(), date(2026, 3, 20)))  # 둘 다 아직
    assert f2.calls == []


def test_year_after_the_last_annual_year_is_used():
    # 2026 사업보고서가 아직 없을 때(2027년 1월): 5년 추이 마지막 연도 2025 → 2026 3분기를 쓴다
    f = FakeFetcher({(2026, "CFS", "11014"): interim(CUR, PRIOR)})
    r, _ = run(collect_recent(f, company(latest=2025), date(2027, 1, 20)))
    assert r.year == 2026
    # 2026 사업보고서가 나온 뒤(5년 추이 마지막 연도 2026)에는 2027년 보고서만 보므로 작년 3분기를 쓰지 않는다
    f2 = FakeFetcher({(2026, "CFS", "11014"): interim(CUR, PRIOR)})
    r2, reason = run(collect_recent(f2, company(latest=2026), date(2027, 4, 20)))
    assert r2 is None and f2.calls == []


def test_same_basis_as_the_five_year_chart():
    f = FakeFetcher({(2026, "OFS", "11012"): interim(CUR, PRIOR)})
    run(collect_recent(f, company(basis="별도"), TODAY))
    assert all(call[1] == "OFS" for call in f.calls)


def test_separate_basis_uses_net_income_as_parent_net_income():
    cur = {**CUR, "net_income_parent": None}  # 별도에는 지배주주 항목이 없다
    prior = {**PRIOR, "net_income_parent": None}
    r, _ = run(collect_recent(FakeFetcher({(2026, "OFS", "11012"): interim(cur, prior)}), company(basis="별도"), TODAY))
    assert r.current["net_income_parent"] == 260 and r.prior["net_income_parent"] == 105
    assert any("당기순이익으로 대신" in n for n in r.notes)


def test_loss_to_profit_and_zero_denominators():
    cur = {"revenue": 500, "operating_income": 50, "net_income_parent": 30, "net_income": 30}
    prior = {"revenue": 0, "operating_income": -100, "net_income_parent": 0, "net_income": 0}
    r, _ = run(collect_recent(FakeFetcher({(2026, "CFS", "11012"): interim(cur, prior)}), company(), TODAY))
    assert r.changes["operating_income"].na_reason == "흑자전환"             # 부호가 바뀌면 % 대신 흑자전환
    assert r.changes["revenue"].value is None and "분모 0" in r.changes["revenue"].na_reason
    assert r.changes["net_income_parent"].value is None
    assert r.operating_margin_prior.value is None and r.changes["operating_margin"].value is None  # 전년 매출 0


def test_missing_cumulative_columns_are_reported_not_guessed():
    cur = {**CUR, "revenue": None}  # 누적 열이 없고 3개월 값만 있는 경우
    r, _ = run(collect_recent(FakeFetcher({(2026, "CFS", "11012"): interim(cur, PRIOR)}), company(), TODAY))
    assert r.current["revenue"] is None and r.changes["revenue"].value is None
    assert any("매출액" in n and "누적" in n for n in r.notes)
