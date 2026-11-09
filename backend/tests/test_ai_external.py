"""Phase 7-B 외부 환경·SWOT·4페이지: 근거 키·숫자·자기소개서 표현 검사와 작업 순서. 외부 호출 없음(가짜 AI 응답)."""
import asyncio
from datetime import datetime

import pytest

from app import ai_external as X
from app import ai_tasks, db, enrich, llm
from app.report_models import Article, ArticleSearch, Enrichment
from tests.test_enrich import DISCLOSURES, env  # noqa: F401  (env는 pytest 픽스처)
from tests.test_reports import client  # noqa: F401

SRCS = {
    "dart:business": X.Src("dart:business", "2025 사업보고서 · 사업의 내용", "반도체는 수출의 24.4%를 차지합니다.", "https://dart/a"),
    "dart:segments": X.Src("dart:segments", "매출 구분", "DRAM 비중 77.1%\n해외 매출 비중(지역별 매출 기준) 98.0%", "https://dart/a"),
    "ecos:fx": X.Src("ecos:fx", "원/달러 환율", "2025-11-03 1,427.4원 → 2026-11-02 1,337.2원 (1년 변화 -6.3%)", "https://ecos"),
}
SENS = {"export_share": 0.98, "fx": {"start_date": "2025-11-03", "start": 1427.4, "end_date": "2026-11-02", "end": 1337.2, "change": -0.063}}
NO_SENS = {"export_share": None, "fx": None}


def answer(monkeypatch, data: dict) -> list[str]:
    """AI가 data를 돌려주게 하고, AI에 보낸 내용(user 메시지)을 모은다."""
    sent: list[str] = []

    async def fake_ask(_client, task, kind, user):
        sent.append(user)
        return llm.LlmResult(data, "fake", 0, 0)

    monkeypatch.setattr(X, "ask", fake_ask)
    return sent


def run(coro):
    return asyncio.run(coro)


# ───────────────────────── 외부 환경 (호출 A)
def test_external_keeps_only_items_with_known_numbers_and_sources(monkeypatch):
    sent = answer(monkeypatch, {
        "pest": {"politics": [{"text": "수출의 24.4%를 차지하는 산업입니다.", "sources": ["dart:business"]},
                              {"text": "수출의 55.5%를 차지합니다.", "sources": ["dart:business"]},  # 넘기지 않은 숫자
                              {"text": "근거 없는 문장입니다.", "sources": []},  # 근거 없음
                              {"text": "지어낸 근거입니다.", "sources": ["news:1"]}]},  # 목록에 없는 키
        "five_forces": {"rivalry": {"strength": "강", "reason": "소수 업체 간 경쟁입니다.", "sources": ["dart:business"]},
                        "buyer_power": {"strength": "매우 강", "reason": "고객이 큽니다.", "sources": ["dart:business"]}},
        "summaries": {"pest": "정책 변화에 민감합니다.", "topics": "비중이 12.3%입니다."},
    })
    o = run(X.write_external(None, SRCS, NO_SENS, None))
    assert o.status == "ok"
    assert [i["text"] for i in o.content["pest"]["politics"]] == ["수출의 24.4%를 차지하는 산업입니다."]
    assert [f["key"] for f in o.content["five_forces"]] == ["rivalry"]  # 강도가 강·중·약이 아니면 버림
    assert o.content["summaries"] == {"pest": "정책 변화에 민감합니다."}
    w = " / ".join(o.warnings)
    assert "55.5" in w and "근거 키" in w and "강·중·약" in w and "12.3" in w
    assert o.content["source_index"] == {"dart:business": {"label": "2025 사업보고서 · 사업의 내용", "url": "https://dart/a"}}  # 화면 근거 이름·링크는 코드가 붙인다
    assert "[근거 키 목록]" in sent[0] and "dart:business: 2025 사업보고서 · 사업의 내용" in sent[0]


def test_topics_use_only_listed_disclosures_with_code_dates_and_links(monkeypatch):
    first, second = DISCLOSURES["items"][0], DISCLOSURES["items"][5]
    answer(monkeypatch, {"topics": [
        {"title": "해명 공시", "summary": "해명 공시가 있었습니다.", "rcept_nos": [first["rcept_no"], "20990101000000", second["rcept_no"]]},
        {"title": "없는 공시", "summary": "지어낸 공시입니다.", "rcept_nos": ["20990101000000"]},
    ]})
    o = run(X.write_external(None, SRCS, NO_SENS, DISCLOSURES))
    [t] = o.content["topics"]
    assert [d["rcept_no"] for d in t["disclosures"]] == [second["rcept_no"], first["rcept_no"]]  # 날짜순, 목록에 없는 번호는 뺌
    assert t["disclosures"][1] == {k: first[k] for k in ("rcept_no", "title", "date", "url")}
    assert any("접수번호" in w for w in o.warnings)


def test_sensitivity_requires_export_share_and_valid_direction(monkeypatch):
    data = {"pest": {"economy": [{"text": "환율이 내렸습니다.", "sources": ["ecos:fx"]}]},
            "sensitivity": {"revenue": {"direction": "긍정", "reason": "해외 매출 비중이 98.0%입니다."},
                            "cost": {"direction": "크게 부정", "reason": "원재료를 수입합니다."}, "sources": ["dart:segments", "ecos:fx"]}}
    sent = answer(monkeypatch, data)
    s = run(X.write_external(None, SRCS, SENS, None)).content["sensitivity"]
    assert s["available"] and s["revenue"]["direction"] == "긍정" and "cost" not in s and s["export_share"] == 0.98
    assert "민감도 작성:" in sent[0]
    sent = answer(monkeypatch, data)
    s = run(X.write_external(None, SRCS, NO_SENS, None)).content["sensitivity"]
    assert s == {"export_share": None, "fx": None, "available": False}  # 수출 비중이 없으면 AI가 써도 쓰지 않는다
    assert "민감도 작성 안 함" in sent[0]


def test_external_with_nothing_usable_fails(monkeypatch):
    answer(monkeypatch, {"pest": {"politics": [{"text": "숫자 99.9%", "sources": ["dart:business"]}]}})
    o = run(X.write_external(None, SRCS, NO_SENS, None))
    assert o.status == "failed" and "99.9" in o.message


# ───────────────────────── SWOT (호출 B)
def test_swot_drops_items_without_sources(monkeypatch):
    answer(monkeypatch, {"verdict": "수익성이 좋아졌습니다.", "swot": {
        "strengths": [{"text": "DRAM 비중이 77.1%입니다.", "sources": ["dart:segments"]}, {"text": "강합니다.", "sources": ["p3:pest"]}],
        "threats": [{"text": "환율이 6.3% 내렸습니다.", "sources": ["ecos:fx"]}]}})
    o = run(X.write_swot(None, SRCS))
    assert o.content["verdict"] == "수익성이 좋아졌습니다."
    assert [i["text"] for i in o.content["swot"]["strengths"]] == ["DRAM 비중이 77.1%입니다."]  # p3:pest는 넘기지 않은 키
    assert o.content["swot"]["threats"][0]["sources"] == ["ecos:fx"] and o.content["swot"]["weaknesses"] == []


# ───────────────────────── 4페이지 (호출 C)
# ───────────────────────── 작업 순서·재시도·기사 제외 (enrich)
def test_naver_articles_never_reach_ai(env, monkeypatch):
    client, report_id, _ = env
    with db.SessionLocal() as s:
        search = s.query(ArticleSearch).filter_by(report_id=report_id).one()
        s.add(Article(search_id=search.id, title="네이버기사제목XYZ", summary="네이버요약ABC", link="http://news/1", published_at=datetime(2026, 11, 1)))
        s.commit()
    sent: list[str] = []
    real = ai_tasks.call_json

    async def capture(client_, task, kind, system, user):
        sent.append(user)
        return await real(client_, task, kind, system, user)

    monkeypatch.setattr(ai_tasks, "call_json", capture)
    e = client.post(f"/api/reports/{report_id}/ai").json()["enrichments"]
    assert e["write_external"]["status"] == "ok" and len(sent) == 18  # 수익성·성장성 AI 해설을 제거해 호출 수 감소 (2026-11-05)
    assert not any("네이버기사제목XYZ" in u or "네이버요약ABC" in u or "http://news/1" in u for u in sent)
    assert any(DISCLOSURES["items"][0]["rcept_no"] in u for u in sent)  # 공시 목록은 넘긴다


def test_external_failure_blocks_swot_then_retry_runs_only_those(env, monkeypatch):
    client, report_id, calls = env
    real = llm._fake
    state = {"fail": True}

    def flaky(task):
        if task == "write_external" and state["fail"]:
            raise llm.LlmError("AI 사용 한도 초과 (HTTP 429)")
        return real(task)  # env의 가짜가 호출을 센다

    monkeypatch.setattr(llm, "_fake", flaky)
    first = client.post(f"/api/reports/{report_id}/ai").json()
    e = first["enrichments"]
    assert set(first["ai_retryable"]) == {"write_external", "write_swot"}
    assert e["write_external"]["status"] == "failed" and "429" in e["write_external"]["message"]
    assert e["write_swot"]["status"] == "failed" and "앞 단계(외부 환경 분석)" in e["write_swot"]["message"]
    assert e["write_summaries"]["status"] == "ok"
    calls["llm"].clear()
    state["fail"] = False
    disclosure_calls = calls["disclosures"]
    second = client.post(f"/api/reports/{report_id}/ai").json()
    e = second["enrichments"]
    assert second["ai_retryable"] == []
    assert calls["llm"] == ["write_external", "write_swot"]  # 성공한 것은 다시 부르지 않는다
    assert calls["disclosures"] == disclosure_calls  # 공시 목록도 저장본을 쓴다
    assert all(v["status"] == "ok" or (k == "business_web" and v["status"] == "empty") for k, v in e.items())


def test_disclosure_failure_blocks_external(env, monkeypatch):
    client, report_id, calls = env
    from app.dart import DartError

    async def boom(_client, corp_code, end):
        raise DartError("network", "DART 연결 실패 (ConnectError)")

    monkeypatch.setattr(enrich, "fetch_disclosures", boom)
    e = client.post(f"/api/reports/{report_id}/ai").json()["enrichments"]
    assert e["disclosures"]["status"] == "failed" and "공시 목록을 받지 못했습니다" in e["disclosures"]["message"]
    assert e["write_external"]["status"] == "failed" and "앞 단계(공시 목록)" in e["write_external"]["message"]
    assert "write_external" not in calls["llm"]


def test_disclosures_use_report_creation_date(env, monkeypatch):
    client, report_id, _ = env
    seen = {}

    async def spy(_client, corp_code, end):
        seen["corp_code"], seen["end"] = corp_code, end
        return {**DISCLOSURES, "items": []}

    monkeypatch.setattr(enrich, "fetch_disclosures", spy)
    e = client.post(f"/api/reports/{report_id}/ai").json()["enrichments"]
    created = client.get(f"/api/reports/{report_id}").json()["created_at"][:10]
    assert seen == {"corp_code": "00164779", "end": datetime.fromisoformat(created).date()}
    assert e["disclosures"]["status"] == "empty" and e["write_external"]["content"]["topics"] == []  # 공시가 없으면 주제도 없음


def test_disclosure_month_math():
    from datetime import date

    from app.disclosures import months_ago
    assert months_ago(date(2026, 11, 3), 3) == date(2026, 8, 3)
    assert months_ago(date(2026, 5, 31), 3) == date(2026, 2, 28)


@pytest.mark.parametrize("text", ["저는 재무 분석을 좋아합니다", "입사 후 기여하겠습니다", "지원 동기는"])
def test_self_intro_pattern(text):
    assert X.SELF_INTRO.search(text)


def test_self_intro_pattern_allows_plain_ideas():
    assert not X.SELF_INTRO.search("정부 지원 정책과 환율 시나리오를 비교해 볼 수 있습니다")


def test_existing_report_lists_pending_ai_tasks(env):
    client, report_id, _ = env
    assert client.get(f"/api/reports/{report_id}").json()["ai_pending"] == list(enrich.TASKS)
    client.post(f"/api/reports/{report_id}/ai")
    assert client.get(f"/api/reports/{report_id}").json()["ai_pending"] == []
    with db.SessionLocal() as s:  # 7-B가 생기기 전에 AI 해석을 만든 리포트처럼 7-B 결과만 지운다
        s.query(Enrichment).filter(Enrichment.key.in_(enrich.EXTERNAL_TASKS)).delete()
        s.commit()
    assert client.get(f"/api/reports/{report_id}").json()["ai_pending"] == list(enrich.EXTERNAL_TASKS)
