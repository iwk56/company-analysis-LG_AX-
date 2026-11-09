"""사업 지역·판매 경로의 DART 웹 검색 결과 검증."""
import asyncio

from app import ai_business_web as W
from app.llm import WebResult

REPORT = {"company": {"corp_name": "테스트", "corp_code": "00123456"}, "base_year": 2025}
DART_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260317000635"
IR_URL = "https://ir.testcompany.com/reports/2025"


def run(monkeypatch, data, cited, searches=2):
    seen = {}
    monkeypatch.setattr(W.company_cache, "load_cache", lambda: {
        "00123456": {"homepage": "https://www.testcompany.com"},
    })

    async def fake(_client, task, system, user):
        seen.update(task=task, system=system, user=user)
        return WebResult(data, "m", 100, 20, searches, frozenset(cited))

    monkeypatch.setattr(W, "call_web_json", fake)
    outcome = asyncio.run(W.find_business_info(None, REPORT, ("region", "channel")))
    return outcome, seen


def test_searches_only_topics_not_already_disclosed():
    assert W.missing_topics({}, {}) == ("region", "channel")
    assert W.missing_topics({}, {"overseas_share": 0.6}) == ("channel",)
    business = {"sales_mix": {"summary": "회사는 직판과 대리점 경로로 제품을 판매합니다.", "quotes": []}}
    assert W.missing_topics(business, {"overseas_share": 0.6}) == ()
    missing = {"sales_mix": {"summary": "지역별 매출액은 제시되지 않았습니다.", "quotes": []}}
    assert W.missing_topics(missing, {}) == ("region", "channel")


def test_keeps_only_cited_dart_or_company_ir_items_for_the_requested_year(monkeypatch):
    other_url = "https://example.com/report"
    data = {"items": [
        {"topic": "region", "year": 2025, "claim": "지역별 매출이 공시되었습니다.", "title": "사업보고서", "url": DART_URL},
        {"topic": "channel", "year": 2024, "claim": "이전 연도", "title": "사업보고서", "url": DART_URL},
        {"topic": "channel", "year": 2025, "claim": "출처가 DART가 아닙니다.", "title": "자료", "url": other_url},
        {"topic": "channel", "year": 2025, "claim": "직판과 대리점 매출을 설명합니다.", "title": "IR 자료", "url": IR_URL},
        {"topic": "price", "year": 2025, "claim": "제품 가격", "title": "사업보고서", "url": DART_URL},
    ]}
    outcome, seen = run(monkeypatch, data, [DART_URL, IR_URL, other_url])
    assert outcome.status == "ok"
    assert outcome.content["items"] == [
        {"topic": "region", "year": 2025, "claim": "지역별 매출이 공시되었습니다.", "title": "사업보고서", "url": DART_URL},
        {"topic": "channel", "year": 2025, "claim": "직판과 대리점 매출을 설명합니다.", "title": "IR 자료", "url": IR_URL},
    ]
    assert outcome.content["searches"] == 2 and len(outcome.warnings) == 2
    assert seen["task"] == "business_web" and "site:dart.fss.or.kr 테스트 2025" in seen["user"]
    assert "testcompany.com" in seen["user"]


def test_fetches_and_caches_official_company_domain_when_not_cached(monkeypatch):
    cache = {}
    calls = []
    monkeypatch.setattr(W.company_cache, "load_cache", lambda: cache)
    monkeypatch.setattr(W.company_cache, "save_cache", lambda value: cache.update(value))

    async def fake_overview(_client, corp_code):
        calls.append(corp_code)
        return {"homepage": "http://www.testcompany.com", "fetched_at": 1}

    monkeypatch.setattr(W.company_cache, "fetch_overview", fake_overview)
    assert asyncio.run(W._official_homepage(None, "00123456")) == ("testcompany.com", None)
    assert calls == ["00123456"] and cache["00123456"]["homepage"] == "http://www.testcompany.com"


def test_company_cache_retains_the_official_homepage(monkeypatch):
    async def fake_company(_client, _corp_code):
        return {"induty_code": "264", "corp_cls": "Y", "corp_name": "테스트", "hm_url": "https://www.testcompany.com"}

    monkeypatch.setattr(W.company_cache, "fetch_company", fake_company)
    entry = asyncio.run(W.company_cache.fetch_overview(None, "00123456"))
    assert entry["homepage"] == "https://www.testcompany.com"


def test_no_official_data_is_empty_and_keeps_search_count(monkeypatch):
    outcome, _ = run(monkeypatch, {"items": []}, [], searches=1)
    assert outcome.status == "empty"
    assert outcome.content == {"items": [], "searches": 1}
    assert "검색 1번" in outcome.message


def test_web_search_disabled_skips_the_call(monkeypatch):
    monkeypatch.setenv("WEB_NEWS", "0")

    async def fail_if_called(*_args):
        raise AssertionError("검색을 호출하면 안 됩니다")

    monkeypatch.setattr(W, "call_web_json", fail_if_called)
    outcome = asyncio.run(W.find_business_info(None, REPORT, ("region", "channel")))
    assert outcome.status == "empty" and "WEB_NEWS=0" in outcome.message
