"""Phase 8-D: PDF 글 고르기(A안), 인용 검증·쪽 번호, PDF 서술 추출 3개, 4장 체크리스트 판정, 실행 흐름 (가짜 응답, 외부 호출 없음)."""
import asyncio

import pytest
from sqlalchemy import delete

from app import ai_pdf as D
from app import checklist as C
from app import db, llm
from app.ai_facts import Facts
from app.pdf_reader import PdfDoc, split_sections
from app.pdf_select import Rule, is_table_line, pick, pick_many, split_blocks
from app.report_models import ReportPdf
from tests.pdf_docs import sk_like_doc, sk_like_interim_doc
from tests.test_enrich import env  # noqa: F401  (pytest 픽스처)
from tests.test_reports import client  # noqa: F401

FACTS = Facts({"header": "기준 사업연도 2025"}, {"2025"})


def run(coro):
    return asyncio.run(coro)


def section(key: str, pages: list[tuple[int, str]], label: str = "섹션") -> dict:
    return {"key": key, "label": label, "found": True, "pages": [{"page": p, "text": t} for p, t in pages]}


def make_docs(annual: PdfDoc | None = None, interim: PdfDoc | None = None) -> dict[str, D.Doc]:
    out = {}
    for slot, doc, kind, year in (("annual", annual, "annual", 2025), ("interim", interim, "half", 2026)):
        if doc is not None:
            _, secs = split_sections(doc)
            out[slot] = D.Doc(slot, kind, year, f"{year} {D.KIND_NAMES[kind]}", "https://dart.fss.or.kr/x",
                              {s["key"]: s for s in secs if s["found"]})
    return out


def answer(monkeypatch, data: dict) -> list[str]:
    """ai_pdf의 AI 호출을 고정 응답으로 바꾸고, 보낸 요청을 모은다."""
    sent = []

    async def fake_ask(_client, task, kind, user):
        sent.append(user)
        return llm.LlmResult(data, "fake", 0, 0)

    monkeypatch.setattr(D, "ask", fake_ask)
    return sent


# ───────── A안: 소제목으로 고르기
MDA_TEXT = ("IV. 이사의 경영진단 및 분석의견\n1. 예측정보에 대한 주의사항\n" + "예측정보 문장입니다.\n" * 20
            + "2. 개요\n" + "경영진은 수요가 늘었다고 설명합니다.\n" * 10
            + "3. 재무상태 및 영업실적\n" + "매출이 증가하였습니다.\n" * 1_200 + "1,234 5,678 9,999\n" * 50
            + "4. 유동성 및 자금조달과 지출\n" + "차입금을 줄였습니다.\n" * 30
            + "5. 부외거래\n해당 없습니다.\n6. 그 밖에 투자의사결정에 필요한 사항\n" + "투자 계획이 있습니다.\n" * 20)


def test_section_under_limit_is_passed_whole():
    sec = section("other_info", [(10, "7. 기타 참고사항\n가. 업계의 현황\n시장이 큽니다.\n나. 회사의 현황\n점유율 1위입니다.")])
    p = pick(sec, Rule(), 12_000)
    assert not p.partial and p.used == ["가. 업계의 현황", "나. 회사의 현황"] and "점유율 1위" in p.text


def test_mda_priority_excludes_boilerplate_and_keeps_later_priority_blocks():
    sec = section("mda", [(300, MDA_TEXT)])
    p = pick(sec, D.MDA_RULE, 12_000)
    assert len(p.text) <= 12_000 and p.partial
    assert p.excluded == ["1. 예측정보에 대한 주의사항", "5. 부외거래"]
    assert p.used[0] == "2. 개요" and "3. 재무상태 및 영업실적 (일부)" in p.used
    assert "4. 유동성 및 자금조달과 지출" in p.used and "6. 그 밖에 투자의사결정에 필요한 사항" in p.used  # 큰 3항이 밀어내지 않음
    assert "예측정보 문장" not in p.text and "1,234 5,678" not in p.text  # 숫자 표 줄은 뺀다


def test_wrapped_sentence_end_is_not_a_sub_heading():
    sec = section("other_info", [(1, "7. 기타 참고사항\n가. 업계의 현황\n수요가 늘고 있습니\n다. 한편, 최근 제품 수요가 늘\n"
                                     "나. 회사의 현황\n점유율\n다. 고객관리 정책\n정책입니다.")])
    assert [b.title for b in split_blocks(sec)] == ["가. 업계의 현황", "나. 회사의 현황", "다. 고객관리 정책"]


def test_share_rows_near_keyword_are_kept_when_tables_are_dropped():
    body = ("마. 사업부문별 시장여건\n" + "시장 수요가 회복되고 있습니다.\n" * 300
            + "<주요제품 시장점유율 추이>\n제품 2025년 2024년 2023년 비고\nTV 세계시장점유율\n15.3% 16.1% 16.3%\n"
            + "1,111 2,222 3,333\n" * 40)
    sec = section("other_info", [(60, "7. 기타 참고사항\n" + body)])
    p = pick(sec, D.POSITION_RULES[0][1], 6_000)
    assert "15.3% 16.1% 16.3%" in p.text and p.text.count("1,111 2,222") <= 3  # 키워드 뒤 3줄까지만 표 줄을 남긴다
    assert is_table_line("15.3% 16.1% 16.3%") and not is_table_line("시장 수요가 회복되고 있습니다.")


def test_share_table_split_over_lines_is_kept_until_percent_rows_end():
    # DART 원문은 표 한 행이 "DRAM | 34.3%" / "39.1% | 36.3% …"처럼 여러 줄로 나뉜다 (2026-11-04 실제 리포트 21에서 뒤 칸이 잘렸음)
    body = ("나. 회사의 현황\n" + "회사는 메모리 반도체를 만들어 팝니다.\n" * 400 + "(2) 시장점유율\n(최근 3사업연도 기준)\n"
            "구분 | 2025년 3분기 | 2025년 2분기 | 2024년\nDRAM | 34.3%\n39.1% | 33.4%\nNAND Flash | 19.7%\n22.0% | 21.6%\n"
            + "1,111 | 2,222\n" * 30)
    p = pick(section("other_info", [(60, "7. 기타 참고사항\n" + body)]), D.POSITION_RULES[0][1], 6_000)
    assert "39.1% | 33.4%" in p.text and "22.0% | 21.6%" in p.text and p.text.count("1,111 | 2,222") == 0


def test_call_limit_spreads_over_sections_in_order():
    a = section("other_info", [(1, "7. 기타\n" + "가" * 9_000)])
    b = section("sales_orders", [(2, "4. 매출\n" + "나" * 9_000)])
    picks = pick_many([(a, Rule()), (b, Rule())], call_limit=12_000)
    assert [p.key for p in picks] == ["other_info", "sales_orders"] and sum(len(p.text) for p in picks) <= 12_000


# ───────── 인용 확인과 쪽 번호
def test_quote_found_across_line_breaks_with_start_page():
    doc = D.Doc("annual", "annual", 2025, "2025 사업보고서", "https://x", {})
    sec = section("risk_derivatives", [(26, "5. 위험관리\n연결회사는 환율변동위험에"), (27, "노출되어 있습니다.\n다음 문장입니다.")])
    corpus = D.Corpus([(doc, sec)])
    q = corpus.find("연결회사는 환율변동 위험에 노출되어 있습니다.")
    assert q and q["page"] == 26 and q["cite"] == "2025 사업보고서 p.26" and q["url"] == "https://x"
    assert corpus.find("노출되어 있습니다. 다음 문장입니다.")["page"] == 27
    assert corpus.find("다음 문장입니다.") is None  # 15자 미만은 인용으로 받지 않는다
    assert corpus.find("원문에 없는 문장을 지어낸 인용입니다.") is None


# ───────── PDF 서술 추출 3개
def test_position_keeps_only_verified_quotes_market_shares_and_customer_scope(monkeypatch):
    docs = make_docs(sk_like_doc())
    fx = D_fixture("extract_position")
    fx["position"]["quotes"].append("원문에 없는 지어낸 점유율 문장입니다 1위입니다.")
    fx["position"]["market_shares"].append({"product": "HBM", "periods": ["2025년"], "values": ["60%"], "quote": fx["position"]["quotes"][0], "source": None})  # 값이 인용 안에 없음
    fx["customers"] = [
        {"quote": fx["risks"][0]["quote"], "share": "35%", "scope": "single"},  # 비중 표기가 인용 안에 없음
        {"quote": "당사는 주요 고객사들과 공급 물량 및 가격을 결정하고 있습니다.", "share": None, "scope": "single"}]
    answer(monkeypatch, fx)
    o = run(D.extract_position(None, docs))
    assert o.status == "ok"
    pos = o.content["position"]
    assert len(pos["quotes"]) == 3 and pos["quotes"][0]["page"] == 5 and "competitors" not in pos
    ms = pos["market_shares"]
    assert [m["product"] for m in ms] == ["DRAM", "NAND Flash"] and abs(ms[0]["share"] - 0.343) < 1e-9 and ms[0]["periods"][0] == "2025년 3분기"
    assert ms[0]["source"] is None  # 출처 문구가 원문에 없으면 버린다
    assert any("지어낸" not in w and "찾지 못함" in w for w in o.warnings) and any("시장점유율 3" in w for w in o.warnings)
    assert [c["share"] for c in o.content["customers"]] == [None, None]
    assert len(o.content["risks"]) == 3 and o.content["risks"][0]["quote"]["cite"].startswith("2025 사업보고서 p.")
    assert o.content["inputs"][0]["label"] == "II-7 기타 참고사항"


def test_customer_aggregate_share_is_never_single():
    assert D.customer_scope("2025년 주요 10대 매출처에 대한 매출 비중은 연결회사 매출액의 31.5% 수준입니다.", "single") == "aggregate"
    assert D.customer_scope("최대 고객 A사의 매출 비중은 35%입니다.", "single") == "single"
    assert D.customer_scope("상위 5개 고객 비중은 40%입니다.", None) == "aggregate"


def test_all_quotes_invented_gives_empty_not_ok(monkeypatch):
    answer(monkeypatch, {"position": {"summary": "1위", "quotes": ["지어낸 문장 하나입니다 길게 씁니다."]}, "customers": [], "risks": []})
    o = run(D.extract_position(None, make_docs(sk_like_doc())))
    assert o.status == "empty" and o.content["position"] is None


def test_mda_drops_only_sentences_with_unknown_numbers(monkeypatch):
    fx = D_fixture("extract_mda")
    fx["summary"] = fx["summary"] + " 2027년에는 매출이 150조원을 넘을 것입니다."
    answer(monkeypatch, fx)
    o = run(D.extract_mda(None, make_docs(sk_like_doc()), FACTS))
    assert o.status == "ok" and "150" not in o.content["summary"] and "30.2조원" in o.content["summary"]
    assert any("150" in w for w in o.warnings) and [q["page"] for q in o.content["quotes"]] == [7, 7, 7]


def test_no_pdf_or_unfiled_mda_makes_no_ai_call(monkeypatch):
    sent = answer(monkeypatch, {})
    for fn in (D.extract_position(None, {}), D.extract_mda(None, {}, FACTS), D.extract_focus(None, {}, FACTS)):
        o = run(fn)
        assert o.status == "empty" and o.message == D.NO_PDF
    half = PdfDoc(["목 차", "표지 사업연도", "II. 사업의 내용\n1. 사업의 개요\n개요",
                   "IV. 이사의 경영진단 및 분석의견\n1. 예측정보에 대한 주의사항\n※ 기업공시서식 작성기준에 따라 반기보고서에는 본 항목을 기재하지 아니하였습니다."], [])
    assert run(D.extract_mda(None, make_docs(half), FACTS)).status == "empty"
    assert sent == []


def test_focus_changes_must_quote_the_recent_report(monkeypatch):
    fx = D_fixture("extract_focus")
    fx["changes"]["investment"] = {"text": "투자를 늘렸습니다.", "quotes": [fx["investment"]["quotes"][0]]}  # 사업보고서 문장 → 버림
    sent = answer(monkeypatch, fx)
    o = run(D.extract_focus(None, make_docs(sk_like_doc(), sk_like_interim_doc()), FACTS))
    assert o.status == "ok" and o.content["interim_label"] == "2026 반기보고서"
    assert list(o.content["changes"]) == ["rnd"] and o.content["changes"]["rnd"]["quotes"][0]["doc"] == "2026 반기보고서"
    assert all(o.content[k] for k in ("rnd", "investment", "new_business"))
    assert "최근 보고서 있음" in sent[0] and "최근 보고서 · 2026 반기보고서" in sent[0]


def D_fixture(task: str) -> dict:
    import json
    return json.loads((llm.FIXTURE_DIR / f"{task}.json").read_text(encoding="utf-8"))


# ───────── 4장 체크리스트 판정 (경계값과 이유 문장 틀)
def report(**over) -> dict:
    fy = {"year": 2025, "revenue": 100e12, "operating_income": 47.2e12, "net_income_parent": 42.9e12, "net_income": 42.9e12,
          "cfo": 53.4e12}
    fy.update(over.pop("fy", {}))
    ratios = {"2025": {"debt_ratio": {"value": over.pop("debt", 0.46)}, "interest_coverage": {"value": over.pop("cov", 51.1)}},
              "2024": {"debt_ratio": {"value": over.pop("debt_prev", 0.4)}}}
    return {"base_year": 2025, "financial_years": [fy], "results": {"ratios": ratios}, "recent_results": over.pop("recent", None),
            "interest_basis": over.pop("basis", "이자비용"), **over}


def test_one_off_templates_and_boundary():
    assert C.one_off(report())["text"] == "이상 없음: 2025년 순이익 42.9조 원 ≤ 영업이익 47.2조 원"
    same = C.one_off(report(fy={"net_income_parent": 47.2e12}))
    assert same["status"] == C.CLEAR
    rr = {"period_current": "2026.01~06", "current": {"net_income_parent": 134.2e12, "operating_income": 98.2e12}}
    o = C.one_off(report(recent=rr))
    assert o["status"] == C.CHECK and o["text"] == "확인 필요: 영업 밖에서 생긴 이익이 큼(2026년 1~6월 순이익 134.2조 원 > 영업이익 98.2조 원)"
    loss = C.one_off(report(fy={"operating_income": -7.7e12, "net_income_parent": 2.1e12}))
    assert loss["text"] == "확인 필요: 영업은 적자인데 순이익은 흑자(2025년 영업이익 −7.7조 원, 순이익 2.1조 원)"
    both = C.one_off(report(fy={"net_income_parent": 50e12}, recent=rr))
    assert len(both["reasons"]) == 2  # 걸린 기간 모두
    assert C.one_off(report(fy={"operating_income": None}))["status"] == C.UNKNOWN


def test_cashflow_templates():
    assert C.cashflow(report())["text"] == "이상 없음: 영업현금흐름 53.4조 원 ≥ 순이익 42.9조 원"
    assert C.cashflow(report(fy={"cfo": 42.9e12}))["status"] == C.CLEAR
    assert C.cashflow(report(fy={"cfo": -1.2e12}))["text"] == "확인 필요: 영업으로 현금이 빠져나감(영업현금흐름 −1.2조 원)"
    assert C.cashflow(report(fy={"cfo": 10.1e12, "net_income": 12.3e12}))["text"] == \
        "확인 필요: 이익만큼 현금이 들어오지 않음(영업현금흐름 10.1조 원 < 순이익 12.3조 원)"
    assert C.cashflow(report(fy={"cfo": None}))["text"] == "확인 불가: 현금흐름 자료 없음"


def test_debt_boundaries_and_coverage_basis():
    assert C.debt(report(debt=2.0, debt_prev=1.6), None)["status"] == C.CLEAR  # 200%·+40%p는 걸리지 않음
    assert C.debt(report(debt=2.153, debt_prev=2.0), None)["text"] == "확인 필요: 빌린 돈이 자기 돈의 2배 넘음(부채비율 215.3%)"
    assert C.debt(report(debt=1.0, debt_prev=0.5), None)["status"] == C.CLEAR  # +50%p 딱 맞으면 넘지 않음
    jump = C.debt(report(debt=1.952, debt_prev=1.4), None)
    assert jump["text"] == "확인 필요: 부채비율이 1년 새 크게 오름(140.0% → 195.2%, +55.2%p)"
    assert C.debt(report(cov=1.0), None)["status"] == C.CLEAR
    low = C.debt(report(cov=0.8, basis="금융비용"), None)
    assert low["text"] == "확인 필요: 영업이익으로 이자를 다 못 냄(이자보상배율 0.8배, 금융비용 기준)"
    actual = C.debt(report(cov=0.8), {"coverage_actual": 51.1})  # 원문 대조를 통과한 실제 이자비용 기준을 먼저 쓴다
    assert actual["status"] == C.CLEAR and "51.1배(실제 이자비용 기준)" in actual["text"]
    assert C.debt(report(debt=None), None)["text"] == "확인 불가: 부채비율 자료 없음"


def cust(text: str, share: float | None, scope: str, share_text: str | None = None) -> dict:
    return {"quote": {"text": text, "cite": "2025 사업보고서 p.42"}, "share": share, "share_text": share_text, "scope": scope}


SEG = {"products": [{"name": "DRAM", "share": 0.771}, {"name": "NAND Flash", "share": 0.213}]}


def test_dependence_concentration_single_customer_and_aggregate_reference():
    d = C.dependence(SEG, {"customers": []}, "ok")
    assert d["text"] == "확인 필요: 한 사업에 집중됨(DRAM 77.1%)" and d["concentration"] and d["customer_note"] == "한 고객의 매출 비중 언급 없음"
    half = C.dependence({"products": [{"name": "A", "share": 0.5}]}, None, None)
    assert half["status"] == C.CHECK  # 50% 이상
    ok = C.dependence({"products": [{"name": "A", "share": 0.499}]}, {"customers": [cust("최대 고객 A사 비중은 29.9%입니다", 0.299, "single", "29.9%")]}, "ok")
    assert ok["status"] == C.CLEAR and ok["text"] == "이상 없음: 최대 부문 A 49.9%, 회사가 밝힌 최대 고객 비중 29.9%"
    single = C.dependence({"products": [{"name": "A", "share": 0.4}]}, {"customers": [cust("최대 고객 A사 비중은 35%입니다", 0.35, "single", "35%")]}, "ok")
    assert single["text"] == "확인 필요: 매출이 특정 고객에 몰림(회사가 밝힌 최대 고객 비중 35%, 2025 사업보고서 p.42)"
    agg = C.dependence({"products": [{"name": "A", "share": 0.4}]},
                       {"customers": [cust("주요 10대 매출처에 대한 매출 비중은 31.5% 수준입니다", 0.315, "aggregate", "31.5%")]}, "ok")
    assert agg["status"] == C.CLEAR and agg["references"][0]["share_text"] == "31.5%"  # 합계는 판정하지 않고 참고로만
    assert C.dependence(None, None, None)["text"] == "확인 불가: 사업부문 비중을 원문과 대조하지 못함"
    assert C.dependence(None, None, None)["customer_note"].startswith("고객 비중 확인 안 함")


def test_accounting_combination():
    ok = {k: ("ok", {"verdict": "clear"}) for k, _ in C.ACCOUNTING_ITEMS}
    assert C.accounting(ok)["text"] == "이상 없음: 4개 항목 모두 이상 없음"
    corr = {**ok, "corrections": ("ok", {"verdict": "check", "count": 2})}
    assert C.accounting(corr)["text"] == "확인 필요: 정정공시 2건"
    miss = {**ok, "extract_related_party": ("failed", None)}
    assert C.accounting(miss)["text"] == "확인 불가: 특수관계자 거래 확인 못 함"
    assert C.accounting({**corr, "extract_related_party": ("failed", None)})["status"] == C.CHECK  # 확인 필요가 먼저


# ───────── 실행 흐름 (enrich)
def statuses(client, rid):
    return {k: v for k, v in client.get(f"/api/reports/{rid}").json()["enrichments"].items()}


def capture(monkeypatch) -> list[tuple[str, str]]:
    """실제 고정 응답은 그대로 쓰면서 각 호출의 요청 글을 모은다."""
    from app import ai_tasks
    sent, real = [], ai_tasks.call_json

    async def spy(client, task, kind, system, user):
        sent.append((task, user))
        return await real(client, task, kind, system, user)

    monkeypatch.setattr(ai_tasks, "call_json", spy)
    return sent


def test_flow_saves_pdf_extractions_checklist_and_passes_them_to_swot_and_tasks(env, monkeypatch):
    client, rid, calls = env
    captured = capture(monkeypatch)
    client.post(f"/api/reports/{rid}/ai")
    sent = dict(captured)
    e = statuses(client, rid)
    assert {k: e[k]["status"] for k in ("extract_position", "extract_mda", "extract_focus", "checklist")} == dict.fromkeys(
        ("extract_position", "extract_mda", "extract_focus", "checklist"), "ok")
    assert e["checklist"]["by"] == "code" and e["extract_mda"]["by"] == "ai"
    items = {i["key"]: i for i in e["checklist"]["content"]["items"]}
    assert list(items) == ["one_off", "cashflow", "debt", "dependence", "risks", "accounting"]
    assert items["dependence"]["text"] == "확인 필요: 한 사업에 집중됨(DRAM 77.1%)" and items["risks"]["status"] == "info"
    swot_prompt = sent["write_swot"]
    assert "pdf:mda" in swot_prompt and "check:dependence" in swot_prompt and "pdf:position" in swot_prompt
    ext = sent["write_external"]
    assert "pdf:business" in ext and "dart:business" not in ext and "calc:competitors" not in ext
    assert "사업의 개요·주요 제품 및 서비스" in sent["write_overview"]
    assert e["write_overview"]["content"]["inputs"][0]["label"] == "II-1 사업의 개요"


def test_report_without_pdf_skips_ai_for_pdf_tasks_and_still_writes_swot(env):
    client, rid, calls = env
    with db.SessionLocal() as s:  # PDF 기능 이전에 만든 리포트처럼
        s.execute(delete(ReportPdf).where(ReportPdf.report_id == rid))
        s.commit()
    client.post(f"/api/reports/{rid}/ai")
    e = statuses(client, rid)
    for k in ("extract_position", "extract_mda", "extract_focus"):
        assert e[k]["status"] == "empty" and e[k]["message"] == D.NO_PDF and e[k]["by"] == "code"
    assert not any(t in calls["llm"] for t in ("extract_position", "extract_mda", "extract_focus"))
    dep = next(i for i in e["checklist"]["content"]["items"] if i["key"] == "dependence")
    assert dep["customer_note"].startswith("고객 비중 확인 안 함") and dep["status"] == "check"
    assert e["write_swot"]["status"] == "ok"


def test_pdf_extraction_failure_blocks_swot_and_tasks_then_retry_runs_only_failed(env, monkeypatch):
    client, rid, calls = env
    real = llm._fake

    def flaky(task):
        if task == "extract_mda":
            raise llm.LlmError("AI 사용 한도 초과 (HTTP 429)")
        return real(task)  # real은 env가 호출을 세는 가짜

    monkeypatch.setattr(llm, "_fake", flaky)
    client.post(f"/api/reports/{rid}/ai")
    e = statuses(client, rid)
    assert e["extract_mda"]["status"] == "failed" and e["write_external"]["status"] == "ok"
    assert e["write_swot"]["status"] == "failed" and "앞 단계(PDF 서술 추출)" in e["write_swot"]["message"]
    monkeypatch.setattr(llm, "_fake", real)
    calls["llm"].clear()
    client.post(f"/api/reports/{rid}/ai")
    assert calls["llm"] == ["extract_mda", "write_swot"]  # 성공한 것은 다시 부르지 않는다
    assert all(v["status"] == "ok" or (k == "business_web" and v["status"] == "empty")
               for k, v in statuses(client, rid).items())


def test_checklist_is_recomputed_on_every_run_without_ai(env):
    client, rid, calls = env
    client.post(f"/api/reports/{rid}/ai")
    n = len(calls["llm"])
    with db.SessionLocal() as s:
        from app.report_models import Enrichment
        row = s.query(Enrichment).filter_by(report_id=rid, key="checklist").one()
        row.content = {"items": []}
        s.commit()
    client.post(f"/api/reports/{rid}/ai")
    assert len(calls["llm"]) == n
    assert len(statuses(client, rid)["checklist"]["content"]["items"]) == 6


def test_pending_list_includes_new_tasks_for_old_reports(env):
    client, rid, _ = env
    pending = client.get(f"/api/reports/{rid}").json()["ai_pending"]
    assert {"extract_position", "extract_mda", "extract_focus", "checklist"} <= set(pending)


@pytest.mark.parametrize("bad", [None, "", "짧은 인용"])
def test_bad_quote_values_are_ignored(bad):
    assert D.Corpus([]).find(bad) is None


def test_quote_from_dart_original_cites_section_name_not_page():
    """2026-11-04: DART 원문으로 만든 섹션은 쪽 번호가 없어 '2025 사업보고서 II-7 기타 참고사항'으로 출처를 단다."""
    from app.ai_pdf import Corpus, Doc
    sec = {"key": "other_info", "label": "II-7 기타 참고사항", "pages": [{"page": None, "text": "DRAM | 34.3% | 39.1%\n시장 점유율이 높습니다."}]}
    doc = Doc("annual", "annual", 2025, "2025 사업보고서", "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=1", {"other_info": sec})
    found = Corpus([(doc, sec)]).find("DRAM 34.3% 39.1% 시장 점유율이 높습니다")
    assert found and found["page"] is None and found["cite"] == "2025 사업보고서 II-7 기타 참고사항" and found["url"].endswith("rcpNo=1")
