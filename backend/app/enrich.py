"""공시 확인·AI 작업 실행과 저장 (Phase 6-A).

작업 6개를 순서대로 한 번씩 실행하고 결과를 작업별로 저장한다. 이미 성공(ok)했거나 원문에 자료가 없다고 확인한(empty) 작업은
다시 실행하지 않는다(같은 리포트의 해석은 다시 만들지 않음, spec 0장 9번). 실패(failed)한 작업만 다시 시도한다.
추출이 하나라도 실패하면 그 결과를 쓰는 해석 2개는 만들지 않고 '앞 단계 실패'로 두었다가 같이 다시 시도한다.
"""
import logging
from datetime import datetime

import httpx

from . import ai_tasks as T
from . import db
from .ai_facts import build_facts
from .dart import DartError
from .dart_docs import load_document_zip, main_document
from .employees import fetch_employees
from .report_models import Enrichment
from .report_store import get_report

log = logging.getLogger("uvicorn.error")

EXTRACT_TASKS = ("employees", "extract_segments", "extract_rnd", "extract_finance")
WRITE_TASKS = ("write_overview", "write_summaries")
TASKS = EXTRACT_TASKS + WRITE_TASKS
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
        status = {e.key: e.status for e in s.query(Enrichment).filter_by(report_id=report_id)}
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
        if any(k in todo for k in EXTRACT_TASKS[1:]):
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

        with db.SessionLocal() as s:
            rows = {e.key: (e.status, e.content) for e in s.query(Enrichment).filter_by(report_id=report_id)}
        if any(rows.get(k, ("failed",))[0] == "failed" for k in EXTRACT_TASKS):
            for key in WRITE_TASKS:
                if key in todo:
                    _save(report_id, key, T.Outcome("failed", message="앞 단계(공시 확인·추출)가 실패해 만들지 못했습니다. 다시 시도해 주세요"), "ai")
            return
        extracted = {k: c for k, (st, c) in rows.items() if k in EXTRACT_TASKS and st == "ok" and c}
        facts = build_facts(report, extracted)
        if "write_overview" in todo:
            _save(report_id, "write_overview", await T.write_overview(client, facts), "ai")
        if "write_summaries" in todo:
            with_net = bool((extracted.get("extract_finance") or {}).get("net_vs_operating"))
            _save(report_id, "write_summaries", await T.write_summaries(client, facts, with_net), "ai")
