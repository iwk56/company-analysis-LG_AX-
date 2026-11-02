"""공시 확인·AI 작업(6-A): 가짜 AI 응답(고정 예시 JSON)과 만들어 둔 가짜 공시 원문으로 전체 흐름을 확인한다. 외부 호출 없음."""
import io
import zipfile

import pytest

from app import ai_tasks, enrich, llm, reports_api
from app.employees import summarize
from tests.test_reports import THIS_YEAR, client, create, wait_done  # noqa: F401  (client는 pytest 픽스처)


def row(*cells):
    return "<TR>" + "".join(f"<TD>{c}</TD>" for c in cells) + "</TR>"


def para(t):
    return f"<P>{t}</P>"


UNIT = row("당기", "(단위 : 백만원)")
DOC = (
    "<SECTION-1><TITLE>II. 사업의 내용</TITLE>"
    "<SECTION-2><TITLE>4. 매출 및 수주상황</TITLE>" + para("가. 매출에 관한 사항") + "</SECTION-2>"
    "<SECTION-2><TITLE>6. 주요계약 및 연구개발활동</TITLE>" + para("2. 연구개발비용") + para("(단위: 백만원)")
    + row("연구개발비용 합계", "6,732,527", "4,954,447", "4,188,404", "-") + "</SECTION-2></SECTION-1>"
    "<SECTION-1><TITLE>III. 재무에 관한 사항</TITLE><SECTION-2><TITLE>3. 연결재무제표 주석</TITLE>"
    + para("24. 매출액 (연결)") + UNIT + row("DRAM", "NAND Flash", "기타", "부문 합계")
    + row("수익(매출액)", "74,904,134", "20,690,084", "1,552,457", "97,146,675")
    + row("전기", "(단위 : 백만원)") + row("DRAM", "NAND Flash", "기타", "부문 합계")
    + row("수익(매출액)", "44,731,664", "19,274,112", "2,187,184", "66,192,960")
    + row("수익(매출액)", "1,932,342", "66,885,115", "19,136,237", "7,215,598", "1,977,383", "97,146,675")
    + para("25. 판매비와관리비 (연결)")
    + para("27. 금융수익 및 금융비용 (연결)") + UNIT + row("이자수익", "494,327") + row("이자비용", "923,703")
    + row("금융비용 소계", "12,504,998") + para("28. 기타영업외수익과 기타영업외비용 (연결)")
    + "</SECTION-2></SECTION-1>")


@pytest.fixture
def env(client, monkeypatch):
    """가짜 AI + 가짜 공시 원문 + 가짜 직원 현황. 호출 횟수를 센다."""
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    calls = {"llm": [], "docs": 0, "emp": 0}
    real_fake = llm._fake

    def counting_fake(task):
        calls["llm"].append(task)
        return real_fake(task)

    monkeypatch.setattr(llm, "_fake", counting_fake)

    async def fake_zip(_client, rcept_no, docs_dir=None):
        calls["docs"] += 1
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(f"{rcept_no}.xml", DOC)
        return buf.getvalue()

    async def fake_emp(_client, corp_code, year, raw_dir=None):
        calls["emp"] += 1
        return {"count": 34549, "avg_tenure_years": 13.4, "avg_salary_won": 185004892, "rcept_no": "R1", "settled_on": f"{year}-12-31",
                "year": year, "url": "https://dart.fss.or.kr/x"}

    monkeypatch.setattr(enrich, "load_document_zip", fake_zip)
    monkeypatch.setattr(enrich, "fetch_employees", fake_emp)
    report_id = wait_done(client, create(client)["job_id"])["report_id"]
    return client, report_id, calls


def enrichments(client, report_id):
    return client.get(f"/api/reports/{report_id}").json()["enrichments"]


def test_report_without_ai_results_has_empty_enrichments(env):
    client, report_id, calls = env
    assert enrichments(client, report_id) == {}  # 생성 작업의 AI 단계는 테스트에서 꺼 두었다
    assert calls["llm"] == []


def test_run_ai_extracts_verifies_and_writes(env):
    client, report_id, calls = env
    res = client.post(f"/api/reports/{report_id}/ai")
    assert res.status_code == 200
    e = res.json()["enrichments"]
    assert {k: v["status"] for k, v in e.items()} == {k: "ok" for k in enrich.TASKS}
    seg = e["extract_segments"]["content"]
    assert [p["name"] for p in seg["products"]] == ["DRAM", "NAND Flash", "기타"]
    assert seg["products"][0]["current_won"] == 74_904_134_000_000 and round(seg["products"][0]["share"], 3) == 0.771
    assert round(seg["products"][0]["growth"], 3) == 0.675 and round(seg["overseas_share"], 3) == 0.98
    assert e["extract_rnd"]["content"]["amount_won"] == 6_732_527_000_000
    assert e["extract_finance"]["content"]["interest_expense_won"] == 923_703_000_000
    assert e["employees"]["by"] == "code" and e["employees"]["content"]["count"] == 34549
    ov = e["write_overview"]
    assert ov["content"]["bcg"]["segments"][0]["name"] == "DRAM"  # 비중·증감률은 위에서 코드가 계산한 값과 같은 숫자라 통과
    assert ov["content"]["overview"] is None and any("기업 개요" in w for w in ov["warnings"])  # 예시 문장의 매출액 숫자는 이 가짜 리포트와 달라 버려진다
    assert e["extract_segments"]["by"] == "ai" and e["extract_segments"]["model"] == "fake"
    assert calls["llm"] == ["extract_segments", "extract_rnd", "extract_finance", "write_overview", "write_summaries"]


def test_second_run_does_not_call_ai_again(env):
    client, report_id, calls = env
    client.post(f"/api/reports/{report_id}/ai")
    n_llm, n_docs, n_emp = len(calls["llm"]), calls["docs"], calls["emp"]
    again = client.post(f"/api/reports/{report_id}/ai")
    assert again.status_code == 200
    assert (len(calls["llm"]), calls["docs"], calls["emp"]) == (n_llm, n_docs, n_emp)  # 저장본을 그대로 쓴다


def test_value_not_in_source_is_dropped_not_saved(env, monkeypatch):
    client, report_id, _ = env
    real = llm._fake

    def wrong_amount(task):
        r = real(task)
        if task == "extract_rnd":  # AI가 원문에 없는 값을 옮김
            return llm.LlmResult({**r.data, "amount": "9,999,999", "quote": "연구개발비용 합계 | 9,999,999"}, "fake", 0, 0)
        return r

    monkeypatch.setattr(llm, "_fake", wrong_amount)
    e = client.post(f"/api/reports/{report_id}/ai").json()["enrichments"]
    assert e["extract_rnd"]["status"] == "empty" and e["extract_rnd"]["content"] is None
    assert "대조하지 못해" in e["extract_rnd"]["message"]
    assert e["extract_finance"]["status"] == "ok"  # 다른 작업은 영향 없음


def test_wrong_unit_is_dropped(env, monkeypatch):
    client, report_id, _ = env
    real = llm._fake
    monkeypatch.setattr(llm, "_fake", lambda t: llm.LlmResult({**real(t).data, "unit": "억원"}, "fake", 0, 0) if t == "extract_rnd" else real(t))
    e = client.post(f"/api/reports/{report_id}/ai").json()["enrichments"]
    assert e["extract_rnd"]["status"] == "empty"  # '억원'은 인용한 '(단위: 백만원)'에 없다 → 천 배 틀린 금액을 막는다


def test_sentence_with_unknown_number_is_dropped(env, monkeypatch):
    client, report_id, _ = env
    real = llm._fake

    def tamper(task):
        r = real(task)
        if task == "write_summaries":
            summaries = {"core_cards": "성장과 수익성이 함께 좋아졌습니다.", "trend": "영업이익이 12345.6조 원까지 늘었습니다."}
            return llm.LlmResult({"summaries": summaries, "notes": {}}, "fake", 0, 0)
        return r

    monkeypatch.setattr(llm, "_fake", tamper)
    e = client.post(f"/api/reports/{report_id}/ai").json()["enrichments"]["write_summaries"]
    assert e["status"] == "ok" and "trend" not in e["content"]["summaries"] and "core_cards" in e["content"]["summaries"]
    assert any("12345.6" in w for w in e["warnings"])


def test_failed_extraction_blocks_writes_and_retry_runs_only_failed(env, monkeypatch):
    client, report_id, calls = env
    real = llm._fake
    state = {"fail": True}

    def flaky(task):
        if task == "extract_segments" and state["fail"]:
            raise llm.LlmError("AI 서비스 연결 실패 (ConnectError)")
        return real(task)

    monkeypatch.setattr(llm, "_fake", flaky)
    e = client.post(f"/api/reports/{report_id}/ai").json()["enrichments"]
    assert e["extract_segments"]["status"] == "failed" and "연결 실패" in e["extract_segments"]["message"]
    assert e["write_overview"]["status"] == "failed" and "앞 단계" in e["write_overview"]["message"]
    assert e["extract_rnd"]["status"] == "ok" and e["employees"]["status"] == "ok"
    calls["llm"].clear()
    state["fail"] = False
    e = client.post(f"/api/reports/{report_id}/ai").json()["enrichments"]
    assert all(v["status"] == "ok" for v in e.values())
    assert calls["llm"] == ["extract_segments", "write_overview", "write_summaries"]  # 성공해 둔 추출 2개는 다시 부르지 않는다


def test_openai_blocked_marks_tasks_failed_but_report_still_opens(env, monkeypatch):
    client, report_id, _ = env
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_ALLOW_LIVE", raising=False)
    e = client.post(f"/api/reports/{report_id}/ai").json()["enrichments"]
    assert e["extract_segments"]["status"] == "failed" and "LLM_ALLOW_LIVE" in e["extract_segments"]["message"]
    assert client.get(f"/api/reports/{report_id}").status_code == 200


def test_document_download_failure_fails_extraction_tasks(env, monkeypatch):
    client, report_id, _ = env
    from app.dart import DartError

    async def boom(_client, rcept_no, docs_dir=None):
        raise DartError("network", "DART 연결 실패 (ConnectError)")

    monkeypatch.setattr(enrich, "load_document_zip", boom)
    e = client.post(f"/api/reports/{report_id}/ai").json()["enrichments"]
    assert e["extract_rnd"]["status"] == "failed" and "공시 원문을 받지 못했습니다" in e["extract_rnd"]["message"]
    assert e["employees"]["status"] == "ok"


def test_concurrent_run_for_same_report_is_rejected(env, monkeypatch):
    client, report_id, _ = env
    enrich._running.add(report_id)
    try:
        assert client.post(f"/api/reports/{report_id}/ai").status_code == 409
    finally:
        enrich._running.discard(report_id)


def test_run_ai_on_missing_report_is_404(client):
    assert client.post("/api/reports/9999/ai").status_code == 404


def test_deleting_report_deletes_enrichments(env):
    client, report_id, _ = env
    client.post(f"/api/reports/{report_id}/ai")
    assert client.delete(f"/api/reports/{report_id}").status_code == 200
    from app import db
    from app.report_models import Enrichment
    with db.SessionLocal() as s:
        assert s.query(Enrichment).count() == 0


def test_net_vs_operating_period_prefers_recent_then_annual():
    report = {"base_year": 2025, "recent_results": {"current": {"net_income_parent": 134, "operating_income": 98}, "period_current": "2026.01~06",
                                                    "report_name": "반기", "rcept_no": "I1"},
              "financial_years": [{"year": 2025, "net_income_parent": 50, "operating_income": 40}],
              "sources": [{"kind": "annual_report", "year": 2025, "rcept_no": "A1"}]}
    assert ai_tasks.net_vs_operating_period(report)["kind"] == "interim"
    report["recent_results"]["current"]["net_income_parent"] = 90
    assert ai_tasks.net_vs_operating_period(report)["kind"] == "annual"
    report["financial_years"][0]["net_income_parent"] = 30
    assert ai_tasks.net_vs_operating_period(report) is None
    report["recent_results"] = None
    assert ai_tasks.net_vs_operating_period(report) is None


def test_employee_summary_weights_by_headcount():
    rows = [{"sm": "23,037", "avrg_cnwk_sdytrn": "12.3", "jan_salary_am": "198,000,000", "rcept_no": "R", "stlm_dt": "2025-12-31"},
            {"sm": "11,512", "avrg_cnwk_sdytrn": "15.7", "jan_salary_am": "159,000,000"}]
    s = summarize(rows)
    assert s["count"] == 34549 and s["avg_tenure_years"] == 13.4 and s["avg_salary_won"] == 185_004_892
    assert summarize([{"sm": "-"}]) is None
    assert summarize([{"sm": "10", "avrg_cnwk_sdytrn": "-", "jan_salary_am": "-"}])["avg_tenure_years"] is None
