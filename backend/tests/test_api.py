"""검색 API 전체 경로 (DART 호출 없이: 고유번호·개황 캐시를 미리 채워 둔다)."""
import time

import pytest
from fastapi.testclient import TestClient

from app import company_cache, corp_codes, main

CORPS = [
    {"corp_code": "00126380", "corp_name": "삼성전자", "stock_code": "005930"},
    {"corp_code": "00126256", "corp_name": "삼성생명", "stock_code": "032830"},
    {"corp_code": "00688996", "corp_name": "KB금융", "stock_code": "105560"},
    {"corp_code": "00120021", "corp_name": "LG", "stock_code": "003550"},
    {"corp_code": "99", "corp_name": "삼성옛날(상장폐지)", "stock_code": "000001"},
    {"corp_code": "98", "corp_name": "삼성코넥스", "stock_code": "000002"},
]
OVERVIEW = {
    "00126380": ("264", "Y"),
    "00126256": ("65110", "Y"),
    "00688996": ("64992", "Y"),
    "00120021": ("64992", "Y"),
    "99": ("64992", "E"),
    "98": ("264", "N"),
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(company_cache, "CACHE_FILE", tmp_path / "cache.json")
    monkeypatch.setattr(company_cache, "DATA_DIR", tmp_path)
    company_cache.save_cache(
        {k: {"induty_code": v[0], "corp_cls": v[1], "fetched_at": time.time()} for k, v in OVERVIEW.items()}
    )

    async def fake_load(_client):
        return CORPS

    monkeypatch.setattr(main, "load_listed_corps", fake_load)
    return TestClient(main.app)


def test_samsung_returns_only_y_k_with_industry_names(client):
    body = client.get("/api/companies/search", params={"q": "삼성"}).json()
    names = [i["corp_name"] for i in body["items"]]
    assert names == ["삼성생명", "삼성전자"]  # 상장폐지(E)·코넥스(N) 제외
    by = {i["corp_name"]: i for i in body["items"]}
    assert by["삼성전자"]["industry_name"] == "통신 및 방송장비 제조업"
    assert by["삼성전자"]["is_financial"] is False
    assert by["삼성생명"]["industry_label"] == "생명보험업" and by["삼성생명"]["is_financial"] is True


def test_holding_companies_split_by_exception_list(client):
    kb = client.get("/api/companies/search", params={"q": "KB금융"}).json()["items"][0]
    lg = client.get("/api/companies/search", params={"q": "LG"}).json()["items"][0]
    assert kb["industry_code"] == lg["industry_code"] == "64992"
    assert kb["is_financial"] is True and lg["is_financial"] is False


def test_short_query_and_no_result(client):
    r = client.get("/api/companies/search", params={"q": "삼"})
    assert r.status_code == 400 and "2글자" in r.json()["detail"]
    body = client.get("/api/companies/search", params={"q": "없는회사"}).json()
    assert body["items"] == [] and "일치하는 기업이 없습니다" in body["message"]


# ---------- DART 호출 상한·간격 (실제 호출 없이 fetch를 가짜로 바꿔 센다) ----------
def _many(n):
    return [{"corp_code": f"c{i:03d}", "corp_name": f"테스트{i:03d}", "stock_code": "1"} for i in range(n)]


@pytest.fixture
def lookups(tmp_path, monkeypatch):
    monkeypatch.setattr(company_cache, "CACHE_FILE", tmp_path / "cache.json")
    monkeypatch.setattr(company_cache, "DATA_DIR", tmp_path)
    log = {"fetched": [], "sleeps": []}

    async def fake_sleep(sec):
        log["sleeps"].append(sec)

    monkeypatch.setattr(main, "_sleep", fake_sleep)
    return log


def _patch_fetch(monkeypatch, log, cls_for):
    async def fake_fetch(_client, code):
        log["fetched"].append(code)
        result = cls_for(code)
        if isinstance(result, Exception):
            raise result
        return {"induty_code": "264", "corp_cls": result, "fetched_at": time.time()}

    monkeypatch.setattr(company_cache, "fetch_overview", fake_fetch)


def test_search_never_makes_more_than_20_dart_calls_and_spaces_them(lookups, monkeypatch):
    import asyncio
    _patch_fetch(monkeypatch, lookups, lambda code: "E")  # 전부 상장폐지라 계속 조회하게 된다
    m = asyncio.run(main._listed_matches(None, _many(50)))
    assert len(lookups["fetched"]) == 20 and m.listed == [] and m.more_results
    assert lookups["sleeps"] == [0.5] * 19  # 호출 사이마다 0.5초 (첫 호출 앞에는 없음)


def test_search_stops_as_soon_as_ten_listed_found(lookups, monkeypatch):
    import asyncio
    _patch_fetch(monkeypatch, lookups, lambda code: "Y")
    m = asyncio.run(main._listed_matches(None, _many(50)))
    assert len(m.listed) == 10 and len(lookups["fetched"]) == 10
    assert m.more_results  # 아직 확인 안 한 후보가 40곳 남아 있다


def test_cached_companies_do_not_count_toward_the_limit(lookups, monkeypatch):
    import asyncio
    hits = _many(30)
    company_cache.save_cache({h["corp_code"]: {"induty_code": "264", "corp_cls": "E", "fetched_at": time.time()}
                              for h in hits[:25]})
    _patch_fetch(monkeypatch, lookups, lambda code: "Y")
    m = asyncio.run(main._listed_matches(None, hits))
    assert lookups["fetched"] == [h["corp_code"] for h in hits[25:]] and len(m.listed) == 5 and not m.more_results
    assert asyncio.run(main._listed_matches(None, hits)).listed  # 두 번째 검색은 전부 캐시라 호출 0
    assert len(lookups["fetched"]) == 5


def test_search_stops_calling_after_connection_failure(lookups, monkeypatch):
    import asyncio
    from app.dart import DartError
    _patch_fetch(monkeypatch, lookups, lambda code: DartError("network", "x"))
    m = asyncio.run(main._listed_matches(None, _many(50)))
    assert len(lookups["fetched"]) == 1 and m.lookup_failed == 1 and m.stopped_early


def test_exactly_ten_listed_and_nothing_left_has_no_more_results_message(lookups, monkeypatch):
    import asyncio
    _patch_fetch(monkeypatch, lookups, lambda code: "Y")
    m = asyncio.run(main._listed_matches(None, _many(10)))
    assert len(m.listed) == 10 and not m.more_results


def test_remaining_delisted_only_candidates_do_not_trigger_more_results(lookups, monkeypatch):
    import asyncio
    hits = _many(14)
    company_cache.save_cache({h["corp_code"]: {"induty_code": "264", "corp_cls": "Y" if i < 10 else "E",
                                               "fetched_at": time.time()} for i, h in enumerate(hits)})
    m = asyncio.run(main._listed_matches(None, hits))
    assert len(m.listed) == 10 and not m.more_results  # 남은 4곳은 상장폐지로 확인됨


# ---------- 응답 형식·정렬·스팩 ----------
def test_json_responses_declare_utf8_charset(client):
    ok = client.get("/api/companies/search", params={"q": "삼성"})
    assert ok.headers["content-type"] == "application/json; charset=utf-8"
    err = client.get("/api/companies/search", params={"q": "삼"})  # 오류 응답도 같게
    assert err.status_code == 400 and err.headers["content-type"] == "application/json; charset=utf-8"


def test_response_message_when_more_than_ten(tmp_path, monkeypatch):
    names = [f"가나{i:02d}" for i in range(15)]
    corps = [{"corp_code": f"k{i}", "corp_name": n, "stock_code": "1"} for i, n in enumerate(names)]
    monkeypatch.setattr(company_cache, "CACHE_FILE", tmp_path / "cache.json")
    monkeypatch.setattr(company_cache, "DATA_DIR", tmp_path)
    company_cache.save_cache({c["corp_code"]: {"induty_code": "264", "corp_cls": "K", "fetched_at": time.time()}
                              for c in corps})

    async def fake_load(_client):
        return corps

    monkeypatch.setattr(main, "load_listed_corps", fake_load)
    body = TestClient(main.app).get("/api/companies/search", params={"q": "가나"}).json()
    assert body["count"] == 10 and body["message"] == "결과가 많습니다. 더 정확한 이름으로 검색해 주세요"


def test_samsung_electronics_comes_before_long_samsung_names(tmp_path, monkeypatch):
    """'삼성'으로 시작하는 기업이 많아도 가나다순이 아니라 짧은 이름이 앞에 와서 삼성전자가 10개 안에 든다."""
    others = ["삼성공조", "삼성에스디에스", "삼성바이오로직스", "삼성중공업", "삼성출판사", "삼성화재", "삼성생명",
              "삼성물산", "삼성전기", "삼성증권", "삼성엔지니어링", "삼성SDI", "삼성제약", "삼성에프엔씨"]
    names = others + ["삼성전자", "삼성스팩1호", "삼성머스트스팩2호"]
    corps = [{"corp_code": f"s{i}", "corp_name": n, "stock_code": "1"} for i, n in enumerate(names)]
    monkeypatch.setattr(company_cache, "CACHE_FILE", tmp_path / "cache.json")
    monkeypatch.setattr(company_cache, "DATA_DIR", tmp_path)
    company_cache.save_cache({c["corp_code"]: {"induty_code": "264", "corp_cls": "Y", "fetched_at": time.time()}
                              for c in corps})

    async def fake_load(_client):
        return corps

    monkeypatch.setattr(main, "load_listed_corps", fake_load)
    body = TestClient(main.app).get("/api/companies/search", params={"q": "삼성"}).json()
    got = [i["corp_name"] for i in body["items"]]
    assert "삼성전자" in got and not any("스팩" in n for n in got) and len(got) == 10
    exact = TestClient(main.app).get("/api/companies/search", params={"q": "삼성전자"}).json()
    assert [i["corp_name"] for i in exact["items"]] == ["삼성전자"] and exact["message"] is None
