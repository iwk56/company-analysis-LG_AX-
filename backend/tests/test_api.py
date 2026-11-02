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
    listed, _, failed, incomplete = asyncio.run(main._listed_matches(None, _many(50)))
    assert len(lookups["fetched"]) == 20 and listed == [] and incomplete
    assert lookups["sleeps"] == [0.5] * 19  # 호출 사이마다 0.5초 (첫 호출 앞에는 없음)


def test_search_stops_as_soon_as_ten_listed_found(lookups, monkeypatch):
    import asyncio
    _patch_fetch(monkeypatch, lookups, lambda code: "Y")
    listed, _, _, incomplete = asyncio.run(main._listed_matches(None, _many(50)))
    assert len(listed) == 10 and len(lookups["fetched"]) == 10 and not incomplete


def test_cached_companies_do_not_count_toward_the_limit(lookups, monkeypatch):
    import asyncio
    hits = _many(30)
    company_cache.save_cache({h["corp_code"]: {"induty_code": "264", "corp_cls": "E", "fetched_at": time.time()}
                              for h in hits[:25]})
    _patch_fetch(monkeypatch, lookups, lambda code: "Y")
    listed, _, _, incomplete = asyncio.run(main._listed_matches(None, hits))
    assert lookups["fetched"] == [h["corp_code"] for h in hits[25:]] and len(listed) == 5 and not incomplete
    assert asyncio.run(main._listed_matches(None, hits))[0]  # 두 번째 검색은 전부 캐시라 호출 0
    assert len(lookups["fetched"]) == 5


def test_search_stops_calling_after_connection_failure(lookups, monkeypatch):
    import asyncio
    from app.dart import DartError
    _patch_fetch(monkeypatch, lookups, lambda code: DartError("network", "x"))
    _, _, failed, incomplete = asyncio.run(main._listed_matches(None, _many(50)))
    assert len(lookups["fetched"]) == 1 and failed == 1 and incomplete
