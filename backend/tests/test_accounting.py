"""회계 이슈 체크(6-B): 감사의견·정정공시(코드)와 계속기업·특수관계자(AI 추출 + 원문 대조) 판정. 외부 호출 없음(가짜 AI·가짜 공시)."""
import asyncio
from datetime import date

import pytest

from app import accounting, ai_accounting as A, enrich, llm
from tests.test_enrich import AUDIT_ROW, DOC, FIX, client, enrichments, env  # noqa: F401  (env·client는 pytest 픽스처)


def set_revenue(report_id, won):
    from app import db
    from app.report_models import FinancialYear, Report
    with db.SessionLocal() as s:
        year = s.get(Report, report_id).base_year
        s.query(FinancialYear).filter_by(report_id=report_id, year=year).one().revenue = won
        s.commit()


def run(env):
    client, report_id, calls = env
    set_revenue(report_id, 97_146_675_000_000)  # SK하이닉스 2025 연결 매출액 (가짜 표의 특수관계자 매출 3.2조 원은 3.3%)
    client.post(f"/api/reports/{report_id}/ai")
    return client, report_id, calls, enrichments(client, report_id)


# ───────────────────────── 감사의견
def test_audit_unqualified_is_clear_and_keeps_details():
    j = accounting.judge_audit([AUDIT_ROW, {**AUDIT_ROW, "bsns_year": "제77기\n(전기)", "adt_opinion": "한정의견"}])
    assert j["verdict"] == "clear" and j["opinion"] == "적정의견" and j["auditor"] == "삼정회계법인"  # 전기 행은 보지 않는다
    assert j["fiscal_term"] == "제78기" and j["emphasis"] == [] and len(j["key_audit_matters"]) == 1
    assert j["url"].endswith("rcpNo=20260317000635")


@pytest.mark.parametrize("opinion", ["한정의견", "부적정의견", "의견거절"])
def test_audit_other_opinions_need_check(opinion):
    assert accounting.judge_audit([{**AUDIT_ROW, "adt_opinion": opinion}])["verdict"] == "check"


def test_audit_mixed_separate_and_consolidated_takes_worse_one():
    j = accounting.judge_audit([AUDIT_ROW, {**AUDIT_ROW, "adt_opinion": "한정의견"}])
    assert j["verdict"] == "check" and "한정의견" in j["opinion"]


def test_audit_without_current_rows_is_none():
    assert accounting.judge_audit(None) is None
    assert accounting.judge_audit([{**AUDIT_ROW, "bsns_year": "제77기\n(전기)"}]) is None


def test_audit_emphasis_is_collected_but_blank_markers_are_not():
    assert accounting.judge_audit([{**AUDIT_ROW, "emphs_matter": "-"}])["emphasis"] == []
    assert accounting.judge_audit([{**AUDIT_ROW, "emphs_matter": "소송 관련 강조"}])["emphasis"] == ["소송 관련 강조"]


def test_fetch_audit_saves_response_and_does_not_call_again(tmp_path, monkeypatch):
    n = {"calls": 0}

    class Resp:
        def json(self):
            return {"status": "000", "list": [AUDIT_ROW]}

    async def fake_get(_c, path, params, retries=3):
        n["calls"] += 1
        assert path == "accnutAdtorNmNdAdtOpinion.json" and params["reprt_code"] == "11011"
        return Resp()

    monkeypatch.setattr(accounting, "_get", fake_get)
    assert asyncio.run(accounting.fetch_audit(None, "00164779", 2025, tmp_path)) == [AUDIT_ROW]
    assert asyncio.run(accounting.fetch_audit(None, "00164779", 2025, tmp_path)) == [AUDIT_ROW]
    assert n["calls"] == 1


def test_fetch_audit_no_data_is_none_and_error_is_raised(tmp_path, monkeypatch):
    class Resp:
        def __init__(self, data): self._d = data
        def json(self): return self._d

    answers = iter([{"status": "013", "message": "조회된 데이타가 없습니다."}, {"status": "020", "message": "한도 초과"}])

    async def fake_get(_c, path, params, retries=3):
        return Resp(next(answers))

    monkeypatch.setattr(accounting, "_get", fake_get)
    assert asyncio.run(accounting.fetch_audit(None, "1", 2025, tmp_path)) is None
    with pytest.raises(accounting.DartError):
        asyncio.run(accounting.fetch_audit(None, "2", 2025, tmp_path))


# ───────────────────────── 정정공시
def test_corrections_none_is_clear_and_some_is_check_sorted_newest_first():
    start, end = date(2026, 1, 1), date(2026, 11, 2)
    assert accounting.judge_corrections([], start, end) == {"verdict": "clear", "count": 0, "items": [], "period_start": "2026-01-01", "period_end": "2026-11-02"}
    filings = [{"report_nm": "[기재정정]사업보고서 (2025.12)", "rcept_dt": "20260401", "rcept_no": "20260401000001"},
               {"report_nm": "[기재정정]반기보고서 (2026.06)", "rcept_dt": "20260901", "rcept_no": "20260901000002"}]
    j = accounting.judge_corrections(filings, start, end)
    assert j["verdict"] == "check" and j["count"] == 2 and j["items"][0]["date"] == "2026-09-01"
    assert j["items"][1]["url"].endswith("rcpNo=20260401000001")


def test_fetch_corrections_keeps_only_correction_filings(monkeypatch):
    class Resp:
        def json(self):
            return {"status": "000", "list": [{"report_nm": "사업보고서 (2025.12)", "rcept_no": "1", "rcept_dt": "20260317"},
                                              {"report_nm": "[기재정정]사업보고서 (2025.12)", "rcept_no": "2", "rcept_dt": "20260401"}]}

    seen = {}

    async def fake_get(_c, path, params, retries=3):
        seen.update(path=path, **params)
        return Resp()

    monkeypatch.setattr(accounting, "_get", fake_get)
    out = asyncio.run(accounting.fetch_corrections(None, "00164779", date(2026, 1, 1), date(2026, 11, 2)))
    assert [f["rcept_no"] for f in out] == ["2"]
    assert seen["pblntf_ty"] == "A" and seen["bgn_de"] == "20260101" and seen["end_de"] == "20261102" and seen["path"] == "list.json"


# ───────────────────────── 전체 흐름 (가짜 AI)
def test_full_flow_saves_four_items_and_summary(env):
    _, _, calls, e = run(env)
    assert e["audit_opinion"]["by"] == "code" and e["audit_opinion"]["content"]["verdict"] == "clear"
    assert e["corrections"]["by"] == "code" and e["corrections"]["content"]["verdict"] == "clear" and e["corrections"]["content"]["count"] == 0
    assert e["extract_going_concern"]["content"]["verdict"] == "clear" and e["extract_going_concern"]["content"]["basis"] == "ai"
    rp = e["extract_related_party"]["content"]
    assert rp["verdict"] == "clear" and rp["threshold"] == 0.30
    assert rp["sales_total_won"] == 3_162_837_000_000 and rp["purchases_total_won"] == 3_786_576_000_000
    assert round(rp["sales_ratio"], 3) == round(3_162_837 / 97_146_675, 3)  # 비중은 코드가 계산한 값
    assert [(t["party"], t["kind"]) for t in rp["top"]][0] == ("ESSENCORE Limited", "매출 등")
    assert rp["loans"] == {"state": "none", "items": []}
    assert rp["guarantees"]["state"] == "found" and rp["guarantees"]["items"][0]["amount_text"] == "RMB 701백만"
    wa = e["write_accounting"]
    assert wa["status"] == "ok" and wa["content"]["summary"] and set(wa["content"]["notes"]) == {"audit_opinion", "going_concern", "corrections", "related_party"}
    assert calls["audit"] == 1 and calls["list"] == 1


def test_non_unqualified_opinion_and_corrections_make_check(env):
    client, report_id, calls = env
    calls["state"]["audit"] = [{**AUDIT_ROW, "adt_opinion": "한정의견"}]
    calls["state"]["filings"] = [{"report_nm": "[기재정정]사업보고서", "rcept_dt": "20260401", "rcept_no": "20260401000001"}]
    client.post(f"/api/reports/{report_id}/ai")
    e = enrichments(client, report_id)
    assert e["audit_opinion"]["content"]["verdict"] == "check" and e["corrections"]["content"]["verdict"] == "check"


def test_going_concern_in_audit_emphasis_is_check_without_calling_ai(env):
    client, report_id, calls = env
    calls["state"]["audit"] = [{**AUDIT_ROW, "emphs_matter": "계속기업 관련 중요한 불확실성이 존재합니다."}]
    client.post(f"/api/reports/{report_id}/ai")
    gc = enrichments(client, report_id)["extract_going_concern"]
    assert gc["status"] == "ok" and gc["content"]["verdict"] == "check" and gc["content"]["basis"] == "emphasis" and gc["model"] is None
    assert "extract_going_concern" not in calls["llm"]


def test_going_concern_ai_says_yes_with_verified_quote_is_check(env, monkeypatch):
    client, report_id, _ = env
    real = llm._fake
    quote = "제78기(당기) | 감사보고서 | 삼정회계법인 | 적정의견 | 해당사항 없음 | 해당사항 없음 | 해당사항 없음"
    monkeypatch.setattr(llm, "_fake", lambda t: llm.LlmResult({"has_material_uncertainty": True, "quote": quote}, "fake", 0, 0) if t == "extract_going_concern" else real(t))
    client.post(f"/api/reports/{report_id}/ai")
    assert enrichments(client, report_id)["extract_going_concern"]["content"]["verdict"] == "check"


def test_going_concern_quote_not_in_source_is_unverifiable(env, monkeypatch):
    client, report_id, _ = env
    real = llm._fake
    monkeypatch.setattr(llm, "_fake", lambda t: llm.LlmResult({"has_material_uncertainty": False, "quote": "계속기업 불확실성 없음이라고 적혀 있음"}, "fake", 0, 0) if t == "extract_going_concern" else real(t))
    client.post(f"/api/reports/{report_id}/ai")
    gc = enrichments(client, report_id)["extract_going_concern"]
    assert gc["status"] == "empty" and gc["content"] is None and "대조하지 못해" in gc["message"]
    assert enrichments(client, report_id)["write_accounting"]["status"] == "ok"  # 확인 불가 항목이 있어도 요약은 만든다


def test_going_concern_unanswered_is_unverifiable(env, monkeypatch):
    client, report_id, _ = env
    real = llm._fake
    monkeypatch.setattr(llm, "_fake", lambda t: llm.LlmResult({"has_material_uncertainty": None, "quote": ""}, "fake", 0, 0) if t == "extract_going_concern" else real(t))
    client.post(f"/api/reports/{report_id}/ai")
    assert enrichments(client, report_id)["extract_going_concern"]["status"] == "empty"


# ───────────────────────── 특수관계자 판정과 원문 대조
def test_related_party_threshold_is_30_percent_of_revenue():
    assert A.judge_related_party(0.299, 0.1) == "clear"
    assert A.judge_related_party(0.30, 0.1) == "check"  # 30% 이상
    assert A.judge_related_party(0.1, 0.45) == "check"
    assert A.judge_related_party(0.1, None) == "unknown"  # 한쪽을 모르면 이상 없음이라 하지 않는다
    assert A.judge_related_party(None, None) == "unknown"
    assert A.judge_related_party(0.5, None) == "check"


def test_related_party_over_threshold_via_flow(env):
    client, report_id, _ = env
    set_revenue(report_id, 10_000_000_000_000)  # 10조 원 → 매출 등 3.16조는 31.6%
    client.post(f"/api/reports/{report_id}/ai")
    rp = enrichments(client, report_id)["extract_related_party"]["content"]
    assert rp["verdict"] == "check" and round(rp["sales_ratio"], 3) == 0.316


def _src():
    return A.related_party_source(DOC)


def test_total_must_be_last_cell_of_current_period_row():
    src = _src()
    assert A.related_party_source(DOC) is not None
    ok = A.verified_total(FIX["sales_total"], "매출", "백만원", src)
    assert ok == 3_162_837_000_000
    not_last = {**FIX["sales_total"], "value": "2,726,387"}  # 합계가 아닌 칸의 값
    assert A.verified_total(not_last, "매출", "백만원", src) is None
    assert A.verified_total(FIX["sales_total"], "매입", "백만원", src) is None  # 행 이름이 다름
    assert A.verified_total(FIX["sales_total"], "매출", None, src) is None  # 단위를 확인하지 못함
    prior = {"value": "9,999", "quote": "매출 등 | " + " | ".join(["1"] * 31) + " | 9,999"}
    assert A.verified_total(prior, "매출", "백만원", src) is None  # 전기 표의 행


def test_top_party_must_sit_in_the_same_column_as_value():
    src = _src()
    good = [{"party": "ESSENCORE Limited", "kind": "매출 등", "value": "2,726,387", "quote": FIX["sales_total"]["quote"]}]
    assert A.verified_top(good, "백만원", src)[0]["amount_won"] == 2_726_387_000_000
    wrong_party = [{**good[0], "party": "회사3"}]  # 값은 ESSENCORE 칸 것인데 다른 회사로 적음
    assert A.verified_top(wrong_party, "백만원", src) == []
    wrong_kind = [{**good[0], "kind": "매입 등"}]
    assert A.verified_top(wrong_kind, "백만원", src) == []
    invented = [{**good[0], "value": "5,000,000"}]
    assert A.verified_top(invented, "백만원", src) == []


def test_top_accepts_row_per_party_layout_and_caps_at_three():
    src = "(단위 : 백만원)\n회사 | 매출 | 매입\nA사 | 100 | 5\nB사 | 300 | 6\nC사 | 200 | 7\nD사 | 50 | 8"
    items = [{"party": p, "kind": "A사 행", "value": v, "quote": f"{p} | {v}"} for p, v in (("A사", "100"), ("B사", "300"), ("C사", "200"), ("D사", "50"))]
    for it in items:
        it["kind"] = it["party"]
    out = A.verified_top(items, "백만원", src)
    assert [o["party"] for o in out] == ["B사", "C사", "A사"]


def test_loans_and_guarantees_states():
    src = _src()
    assert A.verified_text_amounts([], src) == {"state": "none", "items": []}
    found = A.verified_text_amounts(FIX["guarantees"], src)
    assert found["state"] == "found" and found["items"][0]["party"].startswith("Hystars")
    made_up = [{"party": "X", "amount_text": "RMB 999백만", "quote": FIX["guarantees"][0]["quote"]}]
    assert A.verified_text_amounts(made_up, src)["state"] == "unverified"  # 인용에 없는 금액
    fake_quote = [{"party": "X", "amount_text": "5억원", "quote": "특수관계자에게 5억원을 빌려주었습니다"}]
    assert A.verified_text_amounts(fake_quote, src)["state"] == "unverified"  # 원문에 없는 인용
    zero = [{"party": "X", "amount_text": "0", "quote": FIX["sales_total"]["quote"]}]
    assert A.verified_text_amounts(zero, src)["state"] == "unverified"


def test_unverified_loans_show_up_in_flow_not_as_none(env, monkeypatch):
    client, report_id, _ = env
    real = llm._fake

    def fake(t):
        r = real(t)
        if t == "extract_related_party":
            return llm.LlmResult({**r.data, "loans": [{"party": "Y", "amount_text": "7억원", "quote": "Y에 7억원을 대여"}]}, "fake", 0, 0)
        return r

    monkeypatch.setattr(llm, "_fake", fake)
    client.post(f"/api/reports/{report_id}/ai")
    assert enrichments(client, report_id)["extract_related_party"]["content"]["loans"]["state"] == "unverified"


def test_wrong_unit_makes_totals_unverifiable_and_verdict_unknown(env, monkeypatch):
    client, report_id, _ = env
    real = llm._fake
    monkeypatch.setattr(llm, "_fake", lambda t: llm.LlmResult({**real(t).data, "unit": "억원"}, "fake", 0, 0) if t == "extract_related_party" else real(t))
    client.post(f"/api/reports/{report_id}/ai")
    rp = enrichments(client, report_id)["extract_related_party"]["content"]
    assert rp["verdict"] == "unknown" and rp["sales_total_won"] is None and rp["top"] == []


# ───────────────────────── 실패와 해석 검증
def test_audit_fetch_failure_marks_failed_and_blocks_summary_until_retry(env, monkeypatch):
    client, report_id, calls = env
    from app.dart import DartError

    async def boom(_c, corp_code, year, raw_dir=None):
        raise DartError("020", "사용한도를 초과하였습니다")

    good = enrich.fetch_audit
    monkeypatch.setattr(enrich, "fetch_audit", boom)
    e = (client.post(f"/api/reports/{report_id}/ai").json())["enrichments"]
    assert e["audit_opinion"]["status"] == "failed" and "감사의견을 받지 못했습니다" in e["audit_opinion"]["message"]
    assert e["write_accounting"]["status"] == "failed" and "앞 단계" in e["write_accounting"]["message"]
    assert e["corrections"]["status"] == "ok"
    calls["llm"].clear()
    monkeypatch.setattr(enrich, "fetch_audit", good)
    e = client.post(f"/api/reports/{report_id}/ai").json()["enrichments"]
    assert all(v["status"] == "ok" for v in e.values())
    assert [t for t in calls["llm"] if t != "write_overview" and t != "write_summaries"] == ["write_accounting"]  # 성공해 둔 추출은 다시 부르지 않는다
    assert calls["list"] == 1


def test_no_audit_data_is_unverifiable_not_clear(env):
    client, report_id, calls = env
    calls["state"]["audit"] = None
    client.post(f"/api/reports/{report_id}/ai")
    a = enrichments(client, report_id)["audit_opinion"]
    assert a["status"] == "empty" and a["content"] is None


def test_summary_sentence_with_unknown_number_is_dropped(env, monkeypatch):
    client, report_id, _ = env
    real = llm._fake

    def tamper(t):
        if t == "write_accounting":
            return llm.LlmResult({"summary": "특수관계자 거래가 매출액의 77.7%입니다.",
                                  "notes": {"audit_opinion": {"meaning": "감사인의 의견입니다.", "why": "적정의견입니다."}}}, "fake", 0, 0)
        return real(t)

    monkeypatch.setattr(llm, "_fake", tamper)
    client.post(f"/api/reports/{report_id}/ai")
    wa = enrichments(client, report_id)["write_accounting"]
    assert wa["status"] == "ok" and wa["content"]["summary"] is None and "audit_opinion" in wa["content"]["notes"]
    assert any("77.7" in w for w in wa["warnings"])


def test_facts_mark_missing_items_as_unverifiable_and_numbers_match():
    text, allowed = A.accounting_facts({"audit_opinion": None, "corrections": {"verdict": "check", "count": 2, "period_start": "2026-01-01", "period_end": "2026-11-02"}})
    assert "감사의견: 확인 불가" in text and "계속기업 불확실성: 확인 불가" in text and "특수관계자 거래: 확인 불가" in text
    assert "정정공시: 확인 필요" in text and "2" in allowed and "2026" in allowed
