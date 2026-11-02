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
