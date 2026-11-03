"""공시 확인·AI 작업 실행과 저장 (Phase 6-A, 6-B, 7-B).

6-A 작업 6개와 6-B 회계 이슈 작업 5개(감사의견·정정공시는 코드, 계속기업·특수관계자는 AI 추출, 요약·주석은 AI 해석)를 순서대로 한 번씩 실행하고 결과를 작업별로 저장한다. 이미 성공(ok)했거나 원문에 자료가 없다고 확인한(empty) 작업은
다시 실행하지 않는다(같은 리포트의 해석은 다시 만들지 않음, spec 0장 9번). 실패(failed)한 작업만 다시 시도한다.
추출이 하나라도 실패하면 그 결과를 쓰는 해석 2개는 만들지 않고 '앞 단계 실패'로 두었다가 같이 다시 시도한다.
7-B는 공시 목록(코드) → 외부 환경(AI) → SWOT·종합 평가(AI) → 4페이지(AI) 순서이고, 앞 단계가 실패하면 뒤는 '앞 단계 실패'로 둔다.
"""
import logging
from datetime import date, datetime

import httpx

from . import ai_accounting as A
from . import ai_external as X
from . import ai_tasks as T
from . import db
from .accounting import fetch_audit, fetch_corrections, judge_audit, judge_corrections
from .ai_facts import build_facts
from .dart import DartError
from .dart_docs import load_document_zip, main_document
from .disclosures import fetch_disclosures
from .employees import fetch_employees
from .report_models import Enrichment
from .report_store import get_report

log = logging.getLogger("uvicorn.error")

EXTRACT_TASKS = ("employees", "extract_segments", "extract_rnd", "extract_finance")
WRITE_TASKS = ("write_overview", "write_summaries")
ACCOUNTING_CODE = ("audit_opinion", "corrections")
ACCOUNTING_EXTRACT = ("extract_going_concern", "extract_related_party")
ACCOUNTING_TASKS = ACCOUNTING_CODE + ACCOUNTING_EXTRACT
EXTERNAL_TASKS = ("disclosures", "write_external", "write_swot", "write_page4")
TASKS = EXTRACT_TASKS + WRITE_TASKS + ACCOUNTING_TASKS + ("write_accounting",) + EXTERNAL_TASKS
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
    todo = [k for k in TASKS if status.get(k) not in ("ok", "empty")]
    if not todo:
        return
    base_year = report["base_year"]
    fy = next((f for f in report["financial_years"] if f["year"] == base_year), {})
    annual = next((x for x in report["sources"] if x["kind"] == "annual_report" and x["year"] == base_year), None)
    period = T.net_vs_operating_period(report)

    async with httpx.AsyncClient() as client:
        annual_xml, doc_error, interim_xml = None, None, None
        if any(k in todo for k in EXTRACT_TASKS[1:] + ACCOUNTING_EXTRACT + ("write_external",)):
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

        if "employees" in todo:
            try:
                async with dart_lock:
                    emp = await fetch_employees(client, report["company"]["corp_code"], base_year)
                out = T.Outcome("ok", emp) if emp else T.Outcome("empty", message="직원 현황 자료가 없습니다")
            except (DartError, RuntimeError) as e:
                out = T.Outcome("failed", message=f"직원 현황을 받지 못했습니다: {e}")
            _save(report_id, "employees", out, "code")

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
        if any(rows.get(k, ("failed",))[0] == "failed" for k in EXTRACT_TASKS):
            for key in WRITE_TASKS + EXTERNAL_TASKS[1:]:
                if key in todo:
                    _save(report_id, key, T.Outcome("failed", message="앞 단계(공시 확인·추출)가 실패해 만들지 못했습니다. 다시 시도해 주세요"), "ai")
            await _disclosures(client, report, todo, dart_lock)
            return
        extracted = {k: c for k, (st, c) in rows.items() if k in EXTRACT_TASKS and st == "ok" and c}
        facts = build_facts(report, extracted)
        if "write_overview" in todo:
            _save(report_id, "write_overview", await T.write_overview(client, facts), "ai")
        if "write_summaries" in todo:
            with_net = bool((extracted.get("extract_finance") or {}).get("net_vs_operating"))
            _save(report_id, "write_summaries", await T.write_summaries(client, facts, with_net), "ai")
        await _external(client, report, todo, facts, annual_xml, need_doc, dart_lock)


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


async def _external(client, report: dict, todo: list[str], facts, annual_xml: str | None, need_doc, dart_lock) -> None:
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
        out = need_doc("write_external")
        if out is None:
            share = (_stored(report_id, "extract_segments") or {}).get("overseas_share")
            srcs, sens = X.external_sources(report, facts, X.business_text(annual_xml), disc.content, share)
            out = await X.write_external(client, srcs, sens, disc.content)
        _save(report_id, "write_external", out, "ai")
    ext = _stored(report_id, "write_external")
    if ext is None:
        blocked(EXTERNAL_TASKS[2:], "외부 환경 분석")
        return

    if "write_swot" in todo:
        with db.SessionLocal() as s:
            acc = {e.key: e.content for e in s.query(Enrichment).filter_by(report_id=report_id) if e.key in ACCOUNTING_TASKS and e.status == "ok"}
        acc_text = A.accounting_facts({k: acc.get(k) for k in ACCOUNTING_TASKS})[0]
        _save(report_id, "write_swot", await X.write_swot(client, X.swot_sources(report, facts, ext, acc_text)), "ai")
    swot = _stored(report_id, "write_swot")
    if swot is None:
        blocked(EXTERNAL_TASKS[3:], "SWOT")
        return

    if "write_page4" in todo:
        _save(report_id, "write_page4", await X.write_page4(client, X.page4_basis(facts, ext, swot)), "ai")
