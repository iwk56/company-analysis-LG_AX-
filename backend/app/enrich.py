"""공시 확인·AI 작업 실행과 저장 (Phase 6-A, 6-B, 7-B).

6-A 작업 6개와 6-B 회계 이슈 작업 5개(감사의견·정정공시는 코드, 계속기업·특수관계자는 AI 추출, 요약·주석은 AI 해석)를 순서대로 한 번씩 실행하고 결과를 작업별로 저장한다. 이미 성공(ok)했거나 원문에 자료가 없다고 확인한(empty) 작업은
다시 실행하지 않는다(같은 리포트의 해석은 다시 만들지 않음, spec 0장 9번). 실패(failed)한 작업만 다시 시도한다.
추출이 하나라도 실패하면 그 결과를 쓰는 해석 2개는 만들지 않고 '앞 단계 실패'로 두었다가 같이 다시 시도한다.
7-B는 공시 목록(코드) → 외부 환경(AI) → SWOT·종합 평가(AI) → 4페이지(AI) 순서이고, 앞 단계가 실패하면 뒤는 '앞 단계 실패'로 둔다.
8-D는 올린 PDF 서술 추출 3개(AI, PDF가 없으면 AI 없이 안내만) → 4장 체크리스트(코드, AI 단계를 돌 때마다 다시 계산)를 회계 이슈 뒤에 두고,
그 결과를 SWOT·과제의 근거로 넘긴다. PDF 서술 추출이 실패하면 SWOT·과제는 '앞 단계 실패'로 둔다.
"""
import logging
from datetime import date, datetime

import httpx

from . import ai_accounting as A
from . import ai_pdf as D
from . import ai_external as X
from . import ai_tasks as T
from . import db
from .accounting import fetch_audit, fetch_corrections, judge_audit, judge_corrections
from .ai_facts import build_facts
from .checklist import build_checklist, checklist_text
from .dart import DartError
from .dart_docs import load_document_zip, main_document
from .disclosures import fetch_disclosures
from .report_models import Enrichment
from .report_store import get_report
from .subsidiaries import fetch_subsidiaries
from .ai_peers import write_peers
from .ai_income import explain_cashflow, explain_income
from .ai_ratios import STABILITY_GROUPS, explain_ratios
from .balance_notes import collect_balance_note_items
from .ai_web_news import find_web_news
from .ai_business_web import find_business_info, missing_topics
from . import income_notes

log = logging.getLogger("uvicorn.error")

EXTRACT_TASKS = ("extract_segments", "extract_rnd", "extract_finance")  # 직원 현황(employees)은 2026-11-04 방향 전환으로 삭제
WRITE_TASKS = ("write_overview", "write_summaries")
ACCOUNTING_CODE = ("audit_opinion", "corrections")
ACCOUNTING_EXTRACT = ("extract_going_concern", "extract_related_party")
ACCOUNTING_TASKS = ACCOUNTING_CODE + ACCOUNTING_EXTRACT
EXTERNAL_TASKS = ("disclosures", "write_external", "write_swot")  # 과제·직무별 기여(write_page4)는 2026-11-04 삭제
PDF_TASKS = ("extract_position", "extract_mda", "extract_focus")
BUSINESS_TASKS = ("extract_business", "business_web", "subsidiaries", "write_peers")  # 사업 구조·산업경쟁 탭 (2026-11-04). 실패해도 다른 작업을 막지 않는다
INCOME_TASKS = ("income_notes", "explain_income", "web_news", "explain_cashflow")  # 실적 탭 손익계산서 '왜 이렇게 됐나' (2026-11-04): 주석 내역(코드) → 원인 설명(AI)
RATIO_TASKS = ("explain_stability_ratios",)  # 수익성·성장성 설명은 표·차트로 충분해 AI 해설을 쓰지 않는다
BALANCE_TASKS = ("balance_notes",)  # 재무상태표 세부 계정과 DART 주석 변동 내역 (2026-11-05)
CHECKLIST = "checklist"
TASKS = (EXTRACT_TASKS + WRITE_TASKS + ACCOUNTING_TASKS + ("write_accounting",) + PDF_TASKS + BUSINESS_TASKS + INCOME_TASKS
         + RATIO_TASKS + BALANCE_TASKS + (CHECKLIST,) + EXTERNAL_TASKS)
_running: set[int] = set()


class AlreadyRunning(Exception):
    pass


def _save(report_id: int, key: str, o: T.Outcome, by: str) -> None:
    with db.SessionLocal() as s:
        row = s.query(Enrichment).filter_by(report_id=report_id, key=key).one_or_none() or Enrichment(report_id=report_id, key=key)
        row.status, row.by, row.model, row.content, row.message = o.status, by, o.model, o.content, o.message
        row.warnings, row.input_tokens, row.output_tokens = o.warnings, o.input_tokens, o.output_tokens
        row.created_at = datetime.now().replace(microsecond=0)
        s.add(row)
        s.commit()


async def _load_xml(client: httpx.AsyncClient, rcept_no: str, dart_lock) -> str:
    async with dart_lock:
        return main_document(await load_document_zip(client, rcept_no), rcept_no)


async def enrich_report(report_id: int, dart_lock) -> None:
    """실행할 작업(없거나 실패한 것)만 실행한다. 작업이 실패해도 예외로 올리지 않고 결과 행에 남긴다."""
    if report_id in _running:
        raise AlreadyRunning()
    _running.add(report_id)
    try:
        await _enrich(report_id, dart_lock)
    finally:
        _running.discard(report_id)


async def _enrich(report_id: int, dart_lock) -> None:
    db.ensure_init()
    with db.SessionLocal() as s:
        report = get_report(s, report_id)
        rows0 = {e.key: (e.status, e.content) for e in s.query(Enrichment).filter_by(report_id=report_id)}
    status = {k: v[0] for k, v in rows0.items()}
    if report is None:
        raise KeyError(report_id)
    todo = [k for k in TASKS if status.get(k) not in ("ok", "empty") or k == CHECKLIST]  # 체크리스트는 코드라 돌 때마다 다시 계산한다
    # 2026-11-04 이전 코드는 기사를 못 찾으면 web_news를 empty로 남겼다. 기사가 0건인 저장본은 다시 찾는다(꺼 둔 경우는 content가 없어 제외)
    if status.get("web_news") == "empty" and isinstance(rows0["web_news"][1], dict) and not rows0["web_news"][1].get("items"):
        todo.append("web_news")
    base_year = report["base_year"]
    fy = next((f for f in report["financial_years"] if f["year"] == base_year), {})
    annual = next((x for x in report["sources"] if x["kind"] == "annual_report" and x["year"] == base_year), None)
    period = T.net_vs_operating_period(report)

    async with httpx.AsyncClient() as client:
        annual_xml, doc_error, interim_xml = None, None, None
        if any(k in todo for k in EXTRACT_TASKS + ACCOUNTING_EXTRACT + ("write_external", "income_notes", "explain_stability_ratios", "balance_notes")):  # annual report-backed extractions
            try:
                if annual is None:
                    raise DartError("document", "기준 사업연도 사업보고서 접수번호가 없습니다")
                annual_xml = await _load_xml(client, annual["rcept_no"], dart_lock)
            except (DartError, RuntimeError) as e:
                doc_error = f"공시 원문을 받지 못했습니다: {e}"
            if annual_xml and "extract_finance" in todo and period and period["kind"] == "interim" and period["rcept_no"]:
                try:
                    interim_xml = await _load_xml(client, period["rcept_no"], dart_lock)
                except (DartError, RuntimeError) as e:
                    log.warning("반기·분기 보고서 원문을 받지 못했습니다: %s", e)

        def need_doc(o_key: str) -> T.Outcome | None:
            return T.Outcome("failed", message=doc_error) if annual_xml is None and o_key in todo else None

        revenue = fy.get("revenue")
        runners = {
            "extract_segments": lambda: T.extract_segments(client, annual_xml, revenue, base_year),
            "extract_rnd": lambda: T.extract_rnd(client, annual_xml, revenue),
            "extract_finance": lambda: T.extract_finance(client, annual_xml, interim_xml, report, period),
        }
        for key, run in runners.items():
            if key in todo:
                _save(report_id, key, need_doc(key) or await run(), "ai")

        await _accounting(client, report, todo, rows0, annual_xml, need_doc, dart_lock)

        with db.SessionLocal() as s:
            rows = {e.key: (e.status, e.content) for e in s.query(Enrichment).filter_by(report_id=report_id)}
        extracted = {k: c for k, (st, c) in rows.items() if k in EXTRACT_TASKS and st == "ok" and c}
        facts = build_facts(report, extracted)
        docs = D.load_docs(report)
        await _pdf(client, report, todo, docs, facts)
        await _business(client, report, todo, docs, facts, dart_lock)
        await _income(client, report, todo, annual_xml, need_doc, facts)
        await _ratios(client, report, todo, facts, annual_xml)
        if "balance_notes" in todo:
            out = need_doc("balance_notes")
            if out is None:
                details = collect_balance_note_items(annual_xml, report)
                out = (T.Outcome("ok", details) if details["items"] else
                       T.Outcome("empty", details, message="전년 대비 주요 세부 계정 변동이 없습니다"))
            _save(report_id, "balance_notes", out, "code")
        _save(report_id, CHECKLIST, T.Outcome("ok", build_checklist(report, _rows(report_id))), "code")

        if any(rows.get(k, ("failed",))[0] == "failed" for k in EXTRACT_TASKS):
            for key in WRITE_TASKS + EXTERNAL_TASKS[1:]:
                if key in todo:
                    _save(report_id, key, T.Outcome("failed", message="앞 단계(공시 확인·추출)가 실패해 만들지 못했습니다. 다시 시도해 주세요"), "ai")
            await _disclosures(client, report, todo, dart_lock)
            return
        if "write_overview" in todo:
            overview_pdf = D.pdf_text(docs, D.OVERVIEW_RULES, 10_000)  # 1장 주력 사업: 올린 PDF II-1·II-2 (없으면 코드 자료만)
            _save(report_id, "write_overview", await T.write_overview(client, facts, overview_pdf), "ai")
        if "write_summaries" in todo:
            with_net = bool((extracted.get("extract_finance") or {}).get("net_vs_operating"))
            _save(report_id, "write_summaries", await T.write_summaries(client, facts, with_net), "ai")
        await _external(client, report, todo, facts, annual_xml, need_doc, dart_lock, docs)


def _rows(report_id: int) -> dict[str, tuple[str, dict | None, str | None]]:
    with db.SessionLocal() as s:
        return {e.key: (e.status, e.content, e.message) for e in s.query(Enrichment).filter_by(report_id=report_id)}


async def _pdf(client, report: dict, todo: list[str], docs: dict, facts) -> None:
    """8-D PDF 서술 추출 3개. PDF가 없거나 섹션을 못 찾으면 AI를 부르지 않고 안내만 저장한다."""
    runners = {
        "extract_position": lambda: D.extract_position(client, docs),
        "extract_mda": lambda: D.extract_mda(client, docs, facts),
        "extract_focus": lambda: D.extract_focus(client, docs, facts),
    }
    for key, run in runners.items():
        if key in todo:
            out = await run()
            _save(report["id"], key, out, "ai" if out.model else "code")


async def _income(client, report: dict, todo: list[str], annual_xml: str | None, need_doc, facts) -> None:
    """실적 탭 손익계산서: 판관비·금융손익·기타영업외 주석 내역(코드) → 단계별 원인 설명(AI). 실패해도 다른 작업을 막지 않는다."""
    if "income_notes" in todo:
        notes = income_notes.collect(annual_xml)
        out = need_doc("income_notes") or (T.Outcome("ok", notes) if notes else
                                           T.Outcome("empty", message="사업보고서 주석에서 판관비·금융손익 내역을 찾지 못했습니다"))
        _save(report["id"], "income_notes", out, "code")
    if "explain_income" in todo:
        rows = _rows(report["id"])
        get = lambda k: rows[k][1] if k in rows and rows[k][0] == "ok" else None  # noqa: E731
        out = await explain_income(client, facts, get("income_notes") or {}, get("extract_mda"))
        _save(report["id"], "explain_income", out, "ai" if out.model else "code")
    if "web_news" in todo:  # 외부 원인(기사): AI 웹 검색, 검색 최대 3번. WEB_NEWS=0이면 건너뛴다
        rows = _rows(report["id"])
        notes = rows["income_notes"][1] if "income_notes" in rows and rows["income_notes"][0] == "ok" else {}
        out = await find_web_news(client, report, facts, notes or {})
        _save(report["id"], "web_news", out, "ai" if out.model else "code")
    if "explain_cashflow" in todo:  # 현금흐름 탭 '왜 이렇게 됐나' (2026-11-04)
        rows = _rows(report["id"])
        get = lambda k: rows[k][1] if k in rows and rows[k][0] == "ok" else None  # noqa: E731
        out = await explain_cashflow(client, report, facts, get("extract_focus"), get("extract_mda"))
        _save(report["id"], "explain_cashflow", out, "ai" if out.model else "code")


async def _ratios(client, report: dict, todo: list[str], facts, annual_xml: str | None = None) -> None:
    """재무상태 탭의 안정성·활동성 비율만 해석한다."""
    if "explain_stability_ratios" in todo:
        out = await explain_ratios(client, "explain_stability_ratios", report, facts, STABILITY_GROUPS, annual_xml)
        _save(report["id"], "explain_stability_ratios", out, "ai" if out.model else "code")


async def _business(client, report: dict, todo: list[str], docs: dict, facts, dart_lock) -> None:
    """사업 구조 탭: 원문에서 제품·매출 구성·생산·원재료·수주·부문 손익(AI 추출), 타법인 출자 현황(코드, OpenDART)."""
    if "extract_business" in todo:
        out = await D.extract_business(client, docs, facts)
        _save(report["id"], "extract_business", out, "ai" if out.model else "code")
    if "business_web" in todo:
        topics = missing_topics(_stored(report["id"], "extract_business"), _stored(report["id"], "extract_segments"))
        out = await find_business_info(client, report, topics) if topics else T.Outcome(
            "empty", {"items": [], "searches": 0}, "PDF·재무제표에서 확인되어 웹 검색을 건너뛰었습니다"
        )
        _save(report["id"], "business_web", out, "ai" if out.model else "code")
    if "subsidiaries" in todo:
        try:
            async with dart_lock:
                subs = await fetch_subsidiaries(client, report["company"]["corp_code"], report["base_year"])
            out = T.Outcome("ok", subs) if subs else T.Outcome("empty", message="타법인 출자 현황이 없습니다")
        except (DartError, RuntimeError) as e:
            out = T.Outcome("failed", message=f"타법인 출자 현황을 받지 못했습니다: {e}")
        _save(report["id"], "subsidiaries", out, "code")
    if "write_peers" in todo:  # 산업·경쟁 탭: 경쟁사와 비교한 잘하는 점·유리한 점·약점·기회 (비교표가 없으면 AI 없이 안내)
        out = await write_peers(client, report)
        _save(report["id"], "write_peers", out, "ai" if out.model else "code")


async def _accounting(client, report: dict, todo: list[str], rows0: dict, annual_xml: str | None, need_doc, dart_lock) -> None:
    """6-B 회계 이슈: 감사의견·정정공시(코드) → 계속기업·특수관계자(AI 추출) → 요약·주석(AI 해석). 하나가 실패해도 나머지는 계속한다."""
    if not any(k in todo for k in ACCOUNTING_TASKS + ("write_accounting",)):
        return
    report_id, corp_code, base_year = report["id"], report["company"]["corp_code"], report["base_year"]
    done = {k: c for k, (st, c) in rows0.items() if st == "ok" and c}  # 이미 성공한 결과

    def finish(key: str, out: T.Outcome, by: str) -> None:
        _save(report_id, key, out, by)
        if out.status == "ok" and out.content:
            done[key] = out.content
        else:
            done.pop(key, None)

    if "audit_opinion" in todo:
        try:
            async with dart_lock:
                rows = await fetch_audit(client, corp_code, base_year)
            audit = judge_audit(rows)
            out = T.Outcome("ok", audit) if audit else T.Outcome("empty", message="DART에서 이 사업연도의 감사의견 자료를 찾지 못했습니다")
        except (DartError, RuntimeError) as e:
            out = T.Outcome("failed", message=f"감사의견을 받지 못했습니다: {e}")
        finish("audit_opinion", out, "code")
    if "corrections" in todo:
        start, end = date(base_year + 1, 1, 1), date.today()
        try:
            async with dart_lock:
                filings = await fetch_corrections(client, corp_code, start, end)
            out = T.Outcome("ok", judge_corrections(filings, start, end))
        except (DartError, RuntimeError) as e:
            out = T.Outcome("failed", message=f"공시 목록을 받지 못했습니다: {e}")
        finish("corrections", out, "code")

    revenue = next((f.get("revenue") for f in report["financial_years"] if f["year"] == base_year), None)
    runners = {
        "extract_going_concern": lambda: A.extract_going_concern(client, annual_xml, done.get("audit_opinion")),
        "extract_related_party": lambda: A.extract_related_party(client, annual_xml, revenue),
    }
    for key, run in runners.items():
        if key in todo:
            finish(key, need_doc(key) or await run(), "ai")

    if "write_accounting" in todo:
        with db.SessionLocal() as s:
            states = {e.key: e.status for e in s.query(Enrichment).filter_by(report_id=report_id)}
        if any(states.get(k) == "failed" or k not in states for k in ACCOUNTING_TASKS):
            finish("write_accounting", T.Outcome("failed", message="앞 단계(감사의견·정정공시·계속기업·특수관계자)가 실패해 만들지 못했습니다. 다시 시도해 주세요"), "ai")
        else:
            text, allowed = A.accounting_facts({k: done.get(k) for k in ACCOUNTING_TASKS})
            finish("write_accounting", await A.write_accounting(client, text, allowed), "ai")


async def _disclosures(client, report: dict, todo: list[str], dart_lock) -> T.Outcome | None:
    """7-B 재료: 리포트 생성일 기준 최근 3개월 공시 목록(코드). 이미 받았으면 저장본을 쓴다."""
    report_id = report["id"]
    if "disclosures" not in todo:
        with db.SessionLocal() as s:
            row = s.query(Enrichment).filter_by(report_id=report_id, key="disclosures").one_or_none()
            return T.Outcome(row.status, row.content, row.message) if row else None
    try:
        async with dart_lock:
            data = await fetch_disclosures(client, report["company"]["corp_code"], date.fromisoformat(report["created_at"][:10]))
        out = T.Outcome("ok", data) if data["items"] else T.Outcome("empty", data, message="최근 3개월 공시가 없습니다")
    except (DartError, RuntimeError) as e:
        out = T.Outcome("failed", message=f"공시 목록을 받지 못했습니다: {e}")
    _save(report_id, "disclosures", out, "code")
    return out


def _stored(report_id: int, key: str) -> dict | None:
    with db.SessionLocal() as s:
        row = s.query(Enrichment).filter_by(report_id=report_id, key=key).one_or_none()
        return row.content if row is not None and row.status == "ok" else None


async def _external(client, report: dict, todo: list[str], facts, annual_xml: str | None, need_doc, dart_lock, docs: dict) -> None:
    """7-B: 공시 목록 → 외부 환경 → SWOT·종합 평가 → 4페이지. 앞 단계가 실패하면 뒤 단계는 '앞 단계 실패'로 둔다."""
    report_id = report["id"]
    disc = await _disclosures(client, report, todo, dart_lock)

    def blocked(keys: tuple[str, ...], why: str) -> None:
        for key in keys:
            if key in todo:
                _save(report_id, key, T.Outcome("failed", message=f"앞 단계({why})가 실패해 만들지 못했습니다. 다시 시도해 주세요"), "ai")

    if "write_external" in todo:
        if disc is None or disc.status == "failed":
            blocked(EXTERNAL_TASKS[1:], "공시 목록")
            return
        pdf_business, _meta = D.pdf_text(docs, D.BUSINESS_RULES, 11_500)  # 사업의 내용: 올린 PDF가 있으면 PDF, 없으면 DART 원문
        out = None if pdf_business else need_doc("write_external")
        if out is None:
            share = (_stored(report_id, "extract_segments") or {}).get("overseas_share")
            srcs, sens = X.external_sources(report, facts, None if pdf_business else X.business_text(annual_xml), disc.content, share,
                                            pdf_business=pdf_business)
            out = await X.write_external(client, srcs, sens, disc.content)
        _save(report_id, "write_external", out, "ai")
    ext = _stored(report_id, "write_external")
    if ext is None:
        blocked(EXTERNAL_TASKS[2:], "외부 환경 분석")
        return

    rows = _rows(report_id)
    if any(rows.get(k, ("failed",))[0] == "failed" for k in PDF_TASKS):
        blocked(EXTERNAL_TASKS[2:], "PDF 서술 추출")
        return
    pdf = lambda k: rows[k][1] if rows.get(k, ("",))[0] == "ok" else None  # noqa: E731
    label = next((d.label for d in docs.values() if d.slot == "annual"), "사업보고서")
    extra = {**D.pdf_basis(pdf("extract_position"), pdf("extract_mda"), pdf("extract_focus"), label),
             **(checklist_text(rows[CHECKLIST][1]) if rows.get(CHECKLIST, ("",))[0] == "ok" else {})}

    if "write_swot" in todo:
        with db.SessionLocal() as s:
            acc = {e.key: e.content for e in s.query(Enrichment).filter_by(report_id=report_id) if e.key in ACCOUNTING_TASKS and e.status == "ok"}
        acc_text = A.accounting_facts({k: acc.get(k) for k in ACCOUNTING_TASKS})[0]
        _save(report_id, "write_swot", await X.write_swot(client, X.swot_sources(report, facts, ext, acc_text, extra)), "ai")
