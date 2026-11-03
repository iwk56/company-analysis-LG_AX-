"""주가·시가총액(Phase 5-B): 공공데이터포털 응답 읽기·오류 분류, 지수(기준일=100)·왜곡 안내, PER·PBR, 비교표 열과 저장. 외부 호출 없음."""
import asyncio
from datetime import date

import httpx
import pytest

from app import stocks
from app.calc.models import NO_DATA, Metric, YearFinancials
from app.comparison import COLUMN_DEFS, build_comparison, market_values
from tests.test_comparison import cell, entry
from tests.test_reports import client, create, wait_done  # noqa: F401  (client는 pytest 픽스처)

START, END = date(2025, 11, 3), date(2026, 11, 3)


def item(d, code="000660", close="1418000", shares="730492365", cap="1035838173570000"):
    return {"basDt": d, "srtnCd": code, "itmsNm": "SK하이닉스", "clpr": close, "lstgStCnt": shares, "mrktTotAmt": cap}


def ok_body(items, total=None):
    return {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                         "body": {"totalCount": total if total is not None else len(items), "items": {"item": items}}}}


def call(handler, code="000660"):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await stocks.fetch_prices(c, code, START, END)
    return asyncio.run(go())


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", "TESTKEY123")


# ───────────────────────── 응답 읽기
def test_parse_keeps_exact_code_sorted_and_numbers():
    rows = stocks.parse_items([item("20261030"), item("20261029", close="1526000"), item("20261030", code="0006600")], "000660")
    assert [r["date"] for r in rows] == ["2026-10-29", "2026-10-30"]  # 부분 일치로 섞인 다른 종목은 뺀다
    assert rows[1] == {"date": "2026-10-30", "close": 1418000, "shares": 730492365, "market_cap": 1035838173570000}


def test_fetch_sends_v2_address_period_and_code(key):
    seen = {}

    def handler(req):
        seen.update(path=req.url.path, **dict(req.url.params))
        return httpx.Response(200, json=ok_body([item("20261030")]))

    assert len(call(handler)) == 1
    assert seen["path"] == "/1160100/GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2"
    assert seen["likeSrtnCd"] == "000660" and seen["beginBasDt"] == "20251103"
    assert seen["endBasDt"] == "20261104"  # endBasDt는 '미만'이라 오늘을 넣으려면 하루 뒤
    assert seen["numOfRows"] == "400" and seen["resultType"] == "json"


def test_single_item_object_and_empty_result(key):
    assert len(call(lambda r: httpx.Response(200, json={"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": item("20261030")}}}}))) == 1
    assert call(lambda r: httpx.Response(200, json={"response": {"header": {"resultCode": "00"}, "body": {"totalCount": 0, "items": ""}}})) == []


@pytest.mark.parametrize("resp, words", [
    (httpx.Response(403, json={"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR", "returnReasonCode": "30"}}}), "인증키"),
    (httpx.Response(429, text="LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"), "한도"),
    (httpx.Response(200, json={"response": {"header": {"resultCode": "99", "resultMsg": "x"}}}), "코드 99"),
    (httpx.Response(500, text="<html>"), "읽지 못했습니다"),
])
def test_errors_are_classified_without_key(key, resp, words):
    with pytest.raises(stocks.StockError) as e:
        call(lambda r: resp)
    assert words in str(e.value) and "TESTKEY123" not in str(e.value)


def test_connection_error_hides_url_with_key(key):
    def boom(req):
        raise httpx.ConnectError("failed for https://apis.data.go.kr/...serviceKey=TESTKEY123")

    with pytest.raises(stocks.StockError) as e:
        call(boom)
    assert "TESTKEY123" not in str(e.value) and "ConnectError" in str(e.value)


def test_missing_key_stops_before_calling():
    with pytest.raises(stocks.StockError) as e:  # conftest가 키를 비워 둔다
        call(lambda r: pytest.fail("호출하면 안 됨"))
    assert "DATA_GO_KR_KEY" in str(e.value)


# ───────────────────────── 지수·안내
CO = {"corp_code": "00164779", "corp_name": "SK하이닉스", "stock_code": "000660"}


def rows(*spec):
    return [{"date": d, "close": c, "shares": s, "market_cap": c * s} for d, c, s in spec]


def test_index_uses_first_trading_day_as_100():
    s = stocks.build_series(CO, rows(("2025-11-03", 500, 10), ("2026-05-01", 750, 10), ("2026-10-30", 1000, 10)), START, END, True)
    assert s["base_date"] == "2025-11-03" and [p["index"] for p in s["points"]] == [100.0, 150.0, 200.0]
    assert s["notes"] == [] and s["is_target"] is True
    assert stocks.latest_market(s) == {"market_cap": 10000, "as_of": "2026-10-30"}


def test_late_first_day_and_share_jump_are_noted():
    s = stocks.build_series(CO, rows(("2026-03-02", 100, 10), ("2026-03-03", 20, 50), ("2026-03-04", 21, 50)), START, END, False)
    assert s["base_date"] == "2026-03-02"
    assert any("첫 거래일(2026-03-02)" in n for n in s["notes"])
    assert any("2026-03-03" in n and "액면분할" in n for n in s["notes"])  # 상장주식수 5배 → 왜곡 안내


def test_small_share_change_is_not_noted():  # SK하이닉스 실제 1년: 712.7백만 → 730.5백만주
    s = stocks.build_series(CO, rows(("2025-11-03", 100, 712702365), ("2026-10-30", 100, 730492365)), START, END, True)
    assert s["notes"] == []


def test_no_rows_means_no_market():
    s = stocks.build_series(CO, [], START, END, False)
    assert s["points"] == [] and s["base_date"] is None and "시세가 없습니다" in s["notes"][0]
    assert stocks.latest_market(s) is None and stocks.latest_market(None) is None


def test_fetch_stocks_calls_once_per_company_and_skips_missing_code(monkeypatch):
    called = []

    async def fake(_c, code, start, end):
        called.append(code)
        return rows(("2025-11-04", 100, 10))

    monkeypatch.setattr(stocks, "fetch_prices", fake)
    out = asyncio.run(stocks.fetch_stocks(None, [(CO, True), ({**CO, "corp_code": "x", "stock_code": ""}, False)], END))
    assert called == ["000660"] and out[0]["base_date"] == "2025-11-04" and out[1]["points"] == []


# ───────────────────────── PER·PBR과 비교표
def fin(ni, eq):
    return YearFinancials(year=2025, net_income_parent=ni, equity_parent=eq)


def test_per_pbr_are_market_cap_over_parent_income_and_equity():
    v = market_values({"market_cap": 1000, "as_of": "2026-10-30"}, fin(50, 400))
    assert v["market_cap"].value == 1000 and v["per"].value == 20 and v["pbr"].value == 2.5


def test_loss_and_capital_impairment_are_not_applicable():
    v = market_values({"market_cap": 1000, "as_of": "x"}, fin(-5, 0))
    assert v["per"].value is None and v["per"].na_reason == "해당 없음(적자)"
    assert v["pbr"].value is None and v["pbr"].na_reason == "해당 없음(자본잠식)"
    assert market_values({"market_cap": 1000, "as_of": "x"}, fin(None, None))["per"].na_reason == NO_DATA


def test_no_market_means_no_quote_for_three_columns():
    v = market_values(None, fin(50, 400))
    assert all(v[k].value is None and v[k].na_reason == "시세 없음" for k in ("market_cap", "per", "pbr"))


def test_market_cap_ranked_largest_first_per_pbr_unranked_but_vs_average():
    comp = build_comparison(2025, entry("A", cap=300, per=10, pbr=1.0, target=True), [entry("B", cap=100, per=30, pbr=3.0), entry("C", cap=200, per=20, pbr=2.0)])
    assert [cell(comp, n, "market_cap")["rank"] for n in "ABC"] == [1, 3, 2]
    assert all(cell(comp, n, "per")["rank"] is None for n in "ABC")
    assert [cell(comp, n, "per")["vs_average"] for n in "ABC"] == ["below", "above", "same"]
    assert comp["averages"]["pbr"] == pytest.approx(2.0)


def test_position_sentence_ignores_market_columns():
    comp = build_comparison(2025, entry("A", revenue=300, growth=0.0, margin=0.3, roe=0.3, debt=2.0, cap=999, per=99, pbr=9, target=True),
                            [entry("B", revenue=100, growth=0.1, margin=0.1, roe=0.1, debt=1.0, cap=1, per=1, pbr=1)])
    assert comp["position"]["text"] == "A: 비교한 5개 지표 중 3개 우위(매출액, 영업이익률, ROE), 2개 열위(매출액증가율, 부채비율)."
    assert {c["key"]: c["in_position"] for c in comp["columns"]}["market_cap"] is False
    assert [d.key for d in COLUMN_DEFS][-3:] == ["market_cap", "per", "pbr"]


# ───────────────────────── 생성·저장 흐름 (가짜 시세)
def test_report_saves_stock_series_and_market_columns(client):
    job = wait_done(client, create(client)["job_id"])
    assert job["status"] == "done" and any(s["key"] == "stocks" and s["label"] == "주가 수집" for s in job["steps"])
    d = client.get(f"/api/reports/{job['report_id']}").json()
    st = {s["stock_code"]: s for s in d["stocks"]}
    assert set(st) == {"000660", "005930"} and st["000660"]["is_target"] and not st["005930"]["is_target"]
    assert [p["index"] for p in st["000660"]["points"]] == [100.0, 110.0, 120.0]
    assert [p["index"] for p in st["005930"]["points"]] == [100.0, 100.0, 80.0]
    comp = d["results"]["comparison"]
    row = next(r for r in comp["rows"] if r["is_target"])
    fy = next(f for f in d["financial_years"] if f["year"] == d["base_year"])
    assert row["values"]["market_cap"]["value"] == 120_000 * 1_000_000 and row["market_as_of"] == st["000660"]["points"][-1]["date"]
    assert row["values"]["per"]["value"] == pytest.approx(120_000 * 1_000_000 / fy["net_income_parent"])
    assert row["values"]["pbr"]["value"] == pytest.approx(120_000 * 1_000_000 / fy["equity_parent"])
    assert row["values"]["market_cap"]["rank"] == 1  # 삼성전자 가짜 시가총액 400억 < SK하이닉스 1,200억


def test_stock_failure_fails_step_and_saves_nothing(client, monkeypatch):
    async def boom(_c, code, start, end):
        raise stocks.StockError("공공데이터포털 하루 호출 한도를 넘었습니다. 내일 다시 시도해 주세요")

    monkeypatch.setattr(stocks, "fetch_prices", boom)
    job = wait_done(client, create(client)["job_id"])
    assert job["status"] == "failed" and job["error"]["step"] == "stocks" and "한도" in job["error"]["message"]
    assert client.get("/api/reports").json()["count"] == 0


def test_company_without_prices_shows_no_quote_but_report_is_made(client, monkeypatch):
    async def none_for_samsung(_c, code, start, end):
        return [] if code == "005930" else rows(("2025-11-04", 100, 10))

    monkeypatch.setattr(stocks, "fetch_prices", none_for_samsung)
    job = wait_done(client, create(client)["job_id"])
    d = client.get(f"/api/reports/{job['report_id']}").json()
    other = next(r for r in d["results"]["comparison"]["rows"] if not r["is_target"])
    assert other["values"]["market_cap"]["na_reason"] == "시세 없음" and other["market_as_of"] is None
