"""실적 변화의 외부 원인(웹 검색) — 링크는 모델이 실제로 검색·인용한 주소만 남긴다 (2026-11-04)."""
import asyncio

from app import ai_web_news as W
from app.ai_facts import Facts
from app.llm import WebResult

REPORT = {"company": {"corp_name": "테스트", "industry_name": "반도체"}, "base_year": 2025}
FACTS = Facts(blocks={"income": "2025년: 매출액 97.1조 원"}, allowed=set())


def run(monkeypatch, data, cited, searches=2):
    async def fake(_client, task, system, user):
        assert task == "web_news" and "2025년: 매출액 97.1조 원" in user and "웹 검색 도구" in system
        return WebResult(data, "m", 100, 20, searches, frozenset(cited))

    monkeypatch.setattr(W, "call_web_json", fake)
    return asyncio.run(W.find_web_news(None, REPORT, FACTS, {}))


def test_keeps_only_cited_urls_and_known_steps(monkeypatch):
    data = {"items": [
        {"step": "revenue", "claim": "메모리 가격이 올랐다는 보도입니다.", "title": "t", "publisher": "p", "date": "2026-01-01", "url": "https://a.com/1?utm_source=openai"},
        {"step": "revenue", "claim": "지어낸 링크", "url": "https://made-up.com/x"},
        {"step": "price_target", "claim": "목표가", "url": "https://a.com/2"}]}
    o = run(monkeypatch, data, ["https://a.com/1", "https://a.com/2"])
    assert o.status == "ok" and [i["url"] for i in o.content["items"]] == ["https://a.com/1"] and o.content["searches"] == 2
    assert len(o.warnings) == 2 and o.input_tokens == 100


def test_switch_off_skips_the_call(monkeypatch):
    monkeypatch.setenv("WEB_NEWS", "0")
    o = asyncio.run(W.find_web_news(None, REPORT, FACTS, {}))
    assert o.status == "empty" and "WEB_NEWS=0" in o.message


def test_no_items_is_failed_so_it_can_be_retried_and_keeps_search_count(monkeypatch):
    o = run(monkeypatch, {"items": []}, [], searches=1)
    assert o.status == "failed" and o.content == {"items": [], "searches": 1} and "검색 1번" in o.message


def test_suggested_queries_use_top_product(monkeypatch):
    seen = {}

    async def fake(_client, task, system, user):
        seen["user"] = user
        return WebResult({"items": []}, "m", 0, 0, 0, frozenset())

    monkeypatch.setattr(W, "call_web_json", fake)
    facts = Facts(blocks={"income": "x", "segments": "사업부문(품목)별 매출 (2025년)\nDRAM: 74.9조 원, 비중 77.1%"}, allowed=set())
    asyncio.run(W.find_web_news(None, REPORT, facts, {}))
    assert "DRAM 가격 2025년" in seen["user"] and "테스트 2025년 실적 영업이익 증가 이유" in seen["user"]
