"""재무제표 수집·계정 매핑 테스트 — DART를 부르지 않는다 (실제 응답에서 뽑은 고정 자료 + 가짜 응답)."""
import asyncio
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.dart import DartError
from app.fin_collect import NoFinancialsError, collect_company, to_year_list
from app.fin_fetch import FinancialsFetcher
from app.fin_mapping import RULES, RULES_BY_FIELD, extract, parse_amount

SAMPLE = json.loads((Path(__file__).parent / "fixtures" / "dart_sk_hynix_2025_cfs_sample.json").read_text(encoding="utf-8"))
TODAY = date(2026, 11, 2)  # 최신 사업연도 = 2025


def run(coro):
    return asyncio.run(coro)


# ---------- 계정 매핑 (실제 SK하이닉스 2025 연결재무제표에서 뽑은 행) ----------
def test_real_sample_maps_all_17_items_with_exact_amounts():
    values, matched = extract(SAMPLE["list"])
    assert set(matched) == set(RULES_BY_FIELD)  # 17개 모두 매칭
    v = values["thstrm"]
    assert v["revenue"] == 97146675000000 and v["operating_income"] == 47206319000000
    assert v["net_income"] == 42947902000000 and v["net_income_parent"] == 42919287000000
    assert v["total_assets"] == 176107659000000 and v["total_liabilities"] == 55440908000000
    assert v["total_equity"] == 120666751000000 and v["equity_parent"] == 120516178000000
    assert v["cfo"] == 53373126000000 and v["cfi"] == -48054251000000 and v["cff"] == -1444992000000
    assert values["frmtrm"]["revenue"] == 66192960000000  # 전기 열 (2024)
    assert values["bfefrmtrm"]["total_assets"] == 100330165000000  # 전전기 열


def test_parent_net_income_is_not_confused_with_comprehensive_income_row():
    # 포괄손익의 '지배기업의 소유주지분'(총포괄이익 귀속)과 이름이 같지만 ID가 달라 섞이면 안 된다
    _, matched = extract(SAMPLE["list"])
    assert matched["net_income_parent"].row["account_id"] == "ifrs-full_ProfitLossAttributableToOwnersOfParent"
    assert matched["net_income_parent"].row["thstrm_amount"] == "42919287000000"


def row(sj, account_id, name, cur="1", prev="1", prev2="1"):
    return {"sj_div": sj, "account_id": account_id, "account_nm": name, "rcept_no": "R1",
            "thstrm_amount": cur, "frmtrm_amount": prev, "bfefrmtrm_amount": prev2}


def test_id_beats_name_and_name_is_used_when_id_missing():
    rows = [row("IS", "ifrs-full_Revenue", "매출액", "100"), row("IS", "x", "영업수익", "999")]
    assert extract(rows)[0]["thstrm"]["revenue"] == 100
    no_id = [row("IS", "-표준계정코드 미사용-", "영업수익", "777")]
    values, matched = extract(no_id)
    assert values["thstrm"]["revenue"] == 777 and matched["revenue"].by == "name"


def test_income_statement_can_be_in_is_or_cis():
    for sj in ("IS", "CIS"):
        assert extract([row(sj, "dart_OperatingIncomeLoss", "영업이익", "5")])[0]["thstrm"]["operating_income"] == 5


def test_finance_cost_and_receivable_substitution_are_noted():
    _, m = extract([row("CIS", "ifrs-full_FinanceCosts", "금융비용"),
                    row("BS", "ifrs-full_TradeAndOtherCurrentReceivables", "매출채권 및 기타채권")])
    assert "금융비용" in m["interest_expense"].note and "기타채권" in m["receivables"].note
    _, m2 = extract([row("CIS", "ifrs-full_InterestExpense", "이자비용")])
    assert m2["interest_expense"].note is None  # 이자비용이 있으면 대체 표시 없음


def test_cost_of_sales_missing_for_nature_of_expense_companies():
    _, matched = extract([row("CIS", "ifrs-full_Revenue", "영업수익")])
    assert "cost_of_sales" not in matched


@pytest.mark.parametrize("text, expected", [("97146675000000", 97146675000000.0), ("-7730313000000", -7730313000000.0),
                                              ("1,234", 1234.0), ("", None), ("-", None), (None, None), ("abc", None)])
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


# ---------- 5개 연도 수집 (가짜 DART) ----------
class FakeFetcher:
    """fetch(corp, year, fs_div) 호출을 기록하고, filings[(year, fs_div)] 를 돌려준다. 없으면 013."""

    def __init__(self, filings):
        self.filings, self.calls = filings, []

    async def fetch(self, corp_code, year, fs_div):
        self.calls.append((year, fs_div))
        return self.filings.get((year, fs_div), {"status": "013", "message": "no data", "list": []})


def filing(year, base, rcept, cfs=True, **overrides):
    """보고서 한 건: 당기=base+0, 전기=base-1000, 전전기=base-2000 처럼 열마다 다른 값을 넣는다."""
    def amt(delta, scale=1):
        return str(int((base + delta) * scale))
    rows = []
    for rule in RULES:
        if rule.field in ("net_income_parent", "equity_parent") and not cfs:
            continue
        sj = rule.sj[0]
        rows.append({"sj_div": sj, "account_id": rule.ids[0], "account_nm": rule.names[0] if rule.names else "x",
                     "rcept_no": rcept, "thstrm_amount": amt(0), "frmtrm_amount": amt(-1000), "bfefrmtrm_amount": amt(-2000)})
    for r in rows:
        r.update(overrides.get(r["account_id"], {}))
    return {"status": "000", "message": "정상", "list": rows}


def five_year_company(fs="CFS"):
    # 보고서 2025 → 2025/2024/2023, 2024 → 2024/2023/2022, 2023 → 2023/2022/2021 (열 값은 base 기준)
    return {(2025, fs): filing(2025, 10000, "R2025", cfs=fs == "CFS"),
            (2024, fs): filing(2024, 9000, "R2024", cfs=fs == "CFS"),
            (2023, fs): filing(2023, 8000, "R2023", cfs=fs == "CFS")}


def test_five_years_use_the_latest_report_that_contains_each_year():
    f = FakeFetcher(five_year_company())
    res = run(collect_company(f, "c", TODAY))
    assert sorted(res.years) == [2021, 2022, 2023, 2024, 2025] and res.basis == "연결" and res.latest_year == 2025
    # 2023은 2025 보고서(전전기)에서, 2022는 2024 보고서(전전기), 2021은 2023 보고서(전전기)에서 온다
    assert res.receipts == {2025: "R2025", 2024: "R2025", 2023: "R2025", 2022: "R2024", 2021: "R2023"}
    assert res.years[2023].revenue == 10000 - 2000      # 2025 보고서의 전전기 열 (2023 보고서 원본 8000이 아님)
    assert res.years[2022].revenue == 9000 - 2000       # 2024 보고서의 전전기 열
    assert res.years[2021].revenue == 8000 - 2000       # 2023 보고서의 전전기 열 = 5번째 연도(첫 연도)
    assert f.calls == [(2025, "CFS"), (2024, "CFS"), (2023, "CFS")]  # 기업당 3건
    assert res.source_link(2021).endswith("rcpNo=R2023")


def test_collected_years_feed_the_calculation_module():
    from app.calc import analyze
    res = run(collect_company(FakeFetcher(five_year_company()), "c", TODAY))
    out = analyze(to_year_list(res))
    assert out[2021].ratios["revenue_growth"].na_reason  # 첫 연도라 증가율 없음
    assert out[2022].ratios["revenue_growth"].value == pytest.approx((7000 - 6000) / 6000)


def test_falls_back_to_separate_statements_when_no_consolidated():
    filings = {k: v for k, v in five_year_company("OFS").items()}
    f = FakeFetcher(filings)
    res = run(collect_company(f, "c", TODAY))
    assert res.basis == "별도" and (2025, "CFS") in f.calls and (2025, "OFS") in f.calls
    y = res.years[2025]
    assert y.net_income_parent == y.net_income and y.equity_parent == y.total_equity  # 지배주주 항목 대체
    assert any("별도재무제표 기준" in n for n in res.notes)


def test_basis_is_not_mixed_across_years():
    # 2025는 연결이 있고 2023 보고서는 연결이 없다 → 별도를 섞지 않고 연결 가능한 연도까지만
    filings = {(2025, "CFS"): filing(2025, 10000, "R2025"), (2024, "CFS"): filing(2024, 9000, "R2024"),
               (2023, "OFS"): filing(2023, 8000, "R2023", cfs=False)}
    f = FakeFetcher(filings)
    res = run(collect_company(f, "c", TODAY))
    assert res.basis == "연결" and sorted(res.years) == [2022, 2023, 2024, 2025] and res.year_count == 4
    assert (2023, "OFS") not in f.calls


def test_company_listed_less_than_five_years():
    only_latest = {(2025, "CFS"): filing(2025, 10000, "R2025")}
    res = run(collect_company(FakeFetcher(only_latest), "c", TODAY))
    assert sorted(res.years) == [2023, 2024, 2025] and res.year_count == 3


def test_blank_prior_columns_of_newly_listed_company_are_skipped():
    f = filing(2025, 10000, "R2025")
    for r in f["list"]:
        r["bfefrmtrm_amount"] = "-"  # 상장 전이라 전전기 열이 비어 있음
    res = run(collect_company(FakeFetcher({(2025, "CFS"): f}), "c", TODAY))
    assert sorted(res.years) == [2024, 2025]


def test_latest_year_falls_back_when_this_years_report_is_not_filed_yet():
    filings = {(2024, "CFS"): filing(2024, 9000, "R2024")}
    res = run(collect_company(FakeFetcher(filings), "c", date(2026, 1, 15)))  # 2025 보고서 제출 전
    assert res.latest_year == 2024 and 2024 in res.years


def test_no_financials_raises():
    with pytest.raises(NoFinancialsError):
        run(collect_company(FakeFetcher({}), "c", TODAY))


def test_missing_items_and_candidates_are_reported():
    data = five_year_company()
    for key, fl in data.items():
        fl["list"] = [r for r in fl["list"] if r["account_id"] != "ifrs-full_CostOfSales"]
        fl["list"].append({"sj_div": "CIS", "account_id": "x_Other", "account_nm": "기타 매출원가성 비용", "rcept_no": "R",
                           "thstrm_amount": "1", "frmtrm_amount": "1", "bfefrmtrm_amount": "1"})
    res = run(collect_company(FakeFetcher(data), "c", TODAY))
    assert all("cost_of_sales" in res.missing[y] for y in res.years)
    assert any("매출원가성" in c for c in res.candidates["cost_of_sales"])


def test_balance_sheet_without_current_noncurrent_split_warns_possible_financial_company():
    data = five_year_company()
    for fl in data.values():
        fl["list"] = [r for r in fl["list"] if r["account_id"] not in ("ifrs-full_CurrentAssets", "ifrs-full_CurrentLiabilities")]
    res = run(collect_company(FakeFetcher(data), "c", TODAY))
    assert any("금융업일 수 있음" in w for w in res.warnings)
    assert not run(collect_company(FakeFetcher(five_year_company()), "c", TODAY)).warnings


# ---------- 수집기: 저장본 재사용·호출 간격 ----------
def make_fetcher(tmp_path, handler, sleeps):
    async def fake_sleep(sec):
        sleeps.append(round(sec, 2))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return FinancialsFetcher(client, raw_dir=tmp_path, interval=0.5, sleep=fake_sleep, today=TODAY)


def test_saved_responses_are_reused_and_new_calls_are_spaced(tmp_path, monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "SECRETKEY123")
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"status": "000", "message": "정상", "list": [{"x": 1}]})

    sleeps = []
    f = make_fetcher(tmp_path, handler, sleeps)
    run(f.fetch("c1", 2025, "CFS"))
    run(f.fetch("c1", 2024, "CFS"))
    run(f.fetch("c1", 2025, "CFS"))  # 저장본 → 호출 없음, 간격도 없음
    assert f.calls_made == 2 and len(seen) == 2
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 0.5  # 새 호출 사이에만 간격
    assert seen[0]["reprt_code"] == "11011" and seen[0]["fs_div"] == "CFS" and seen[0]["bsns_year"] == "2025"
    # 새 수집기(다음 실행)도 저장본을 읽는다
    f2 = make_fetcher(tmp_path, handler, [])
    run(f2.fetch("c1", 2025, "CFS"))
    assert f2.calls_made == 0 and len(seen) == 2


def test_no_data_is_cached_only_for_older_years(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"status": "013", "message": "조회된 데이터가 없습니다."})

    f = make_fetcher(tmp_path, handler, [])
    run(f.fetch("c1", 2025, "CFS"))   # 최근 연도의 '없음'은 아직 제출 전일 수 있어 저장하지 않는다
    run(f.fetch("c1", 2025, "CFS"))
    run(f.fetch("c1", 2020, "CFS"))   # 오래된 연도의 '없음'은 저장
    run(f.fetch("c1", 2020, "CFS"))
    assert f.calls_made == 3


def test_dart_errors_raise_without_saving_and_without_leaking_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "SECRETKEY123")
    f = make_fetcher(tmp_path, lambda r: httpx.Response(200, json={"status": "020", "message": "한도 초과"}), [])
    with pytest.raises(DartError) as e:
        run(f.fetch("c1", 2025, "CFS"))
    assert e.value.status == "020" and not list(tmp_path.glob("*.json"))

    def boom(request):
        raise httpx.ConnectError("fail " + str(request.url))

    f2 = make_fetcher(tmp_path, boom, [])
    with pytest.raises(DartError) as e2:
        run(f2.fetch("c1", 2025, "CFS"))
    assert "SECRETKEY123" not in str(e2.value)


# ---------- 이자보상배율 표시 ----------
def test_interest_coverage_is_labelled_as_finance_cost_basis_when_substituted():
    import show_financials
    res = run(collect_company(FakeFetcher(five_year_company()), "c", TODAY))
    assert res.interest_basis() == "이자비용"  # fixture 는 이자비용 계정을 가짐 (rule.ids[0])
    assert show_financials.ratio_labels(res)["interest_coverage"] == "이자보상배율"
    data = five_year_company()
    for fl in data.values():
        for r in fl["list"]:
            if r["account_id"] == "ifrs-full_InterestExpense":
                r["account_id"], r["account_nm"] = "ifrs-full_FinanceCosts", "금융비용"
    res2 = run(collect_company(FakeFetcher(data), "c", TODAY))
    assert res2.interest_basis() == "금융비용"
    assert show_financials.ratio_labels(res2)["interest_coverage"] == "이자보상배율(금융비용 기준)"
    assert any("외환·파생상품 손실" in n for n in res2.notes)
