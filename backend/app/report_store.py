"""리포트 저장·조회·삭제. 생성이 끝까지 성공했을 때만 save_report를 부른다(실패한 리포트는 저장하지 않음)."""
from dataclasses import fields
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .calc.models import YearAnalysis, YearFinancials
from .fin_collect import CompanyFinancials
from .recent_results import RecentResults
from .report_build import build_sections, data_as_of, source_rows, won
from .report_models import CalcResult, Company, FinancialYear, RecentResult, Report, Source

AMOUNT_FIELDS = [f.name for f in fields(YearFinancials) if f.name != "year"]


def save_report(session: Session, company: dict, res: CompanyFinancials, analysis: dict[int, YearAnalysis],
                recent: RecentResults | None, recent_reason: str | None,
                competitors: list[dict] | None = None, comparison: dict | None = None) -> int:
    """한 트랜잭션으로 저장한다. 중간에 실패하면 아무것도 남지 않는다."""
    session.merge(Company(corp_code=company["corp_code"], corp_name=company["corp_name"],
                          stock_code=company["stock_code"], industry_code=company["industry_code"],
                          industry_name=company["industry_name"]))
    warnings = list(res.warnings)
    excluded = {x["corp_code"]: x["reason"] for x in (comparison or {}).get("excluded", [])}
    competitor_rows = [{"corp_code": c["corp_code"], "corp_name": c["corp_name"], "stock_code": c["stock_code"],
                        "industry_name": c.get("industry_name"), "included": c["corp_code"] not in excluded,
                        "excluded_reason": excluded.get(c["corp_code"])} for c in competitors or []]
    if company.get("is_financial") is None:
        warnings.append("업종코드를 확인하지 못해 금융업 여부를 판별하지 못했습니다")
    report = Report(
        corp_code=company["corp_code"], created_at=datetime.now().replace(microsecond=0), base_year=res.latest_year,
        data_as_of=data_as_of(res, recent), basis=res.basis, year_count=res.year_count,
        interest_basis=res.interest_basis(), competitors=competitor_rows, notes=list(res.notes), warnings=warnings,
        recent_reason=None if recent else recent_reason)
    for y in sorted(res.years):
        report.financial_years.append(FinancialYear(
            year=y, rcept_no=res.receipts.get(y), missing_fields=res.missing.get(y, []),
            **{f: won(getattr(res.years[y], f)) for f in AMOUNT_FIELDS}))
    if recent:
        report.recent = RecentResult(
            report_name=recent.report_name, year=recent.year, reprt_code=recent.reprt_code, rcept_no=recent.rcept_no,
            basis=recent.basis, period_current=recent.period_current, period_prior=recent.period_prior,
            current={k: won(v) for k, v in recent.current.items()}, prior={k: won(v) for k, v in recent.prior.items()},
            notes=list(recent.notes))
    sections = build_sections(analysis, recent)
    if comparison:
        sections["comparison"] = comparison
    for name, content in sections.items():
        report.results.append(CalcResult(section=name, content=content))
    for s in source_rows(res, recent):
        report.sources.append(Source(**s))
    session.add(report)
    session.commit()
    return report.id


def list_reports(session: Session, q: str | None = None) -> list[dict]:
    """최신 생성순. q가 있으면 기업명에 포함된 것만."""
    stmt = select(Report, Company).join(Company).order_by(Report.created_at.desc(), Report.id.desc())
    if q and q.strip():
        stmt = stmt.where(Company.corp_name.contains(q.strip(), autoescape=True))
    return [{"id": r.id, "corp_code": c.corp_code, "corp_name": c.corp_name, "created_at": r.created_at.isoformat(),
             "base_year": r.base_year, "competitor_count": len(r.competitors)} for r, c in session.execute(stmt)]


def get_report(session: Session, report_id: int) -> dict | None:
    r = session.get(Report, report_id)
    if r is None:
        return None
    c = r.company
    recent = r.recent
    return {
        "id": r.id,
        "company": {"corp_code": c.corp_code, "corp_name": c.corp_name, "stock_code": c.stock_code,
                    "industry_code": c.industry_code, "industry_name": c.industry_name},
        "created_at": r.created_at.isoformat(), "base_year": r.base_year, "data_as_of": r.data_as_of.isoformat(),
        "basis": r.basis, "year_count": r.year_count, "interest_basis": r.interest_basis,
        "competitors": r.competitors, "notes": r.notes, "warnings": r.warnings,
        "unit": "원",
        "financial_years": [{"year": fy.year, "rcept_no": fy.rcept_no, "missing_fields": fy.missing_fields,
                             **{f: getattr(fy, f) for f in AMOUNT_FIELDS}} for fy in r.financial_years],
        "recent_results": None if recent is None else {
            "report_name": recent.report_name, "year": recent.year, "rcept_no": recent.rcept_no, "basis": recent.basis,
            "period_current": recent.period_current, "period_prior": recent.period_prior,
            "current": recent.current, "prior": recent.prior, "notes": recent.notes},
        "recent_reason": r.recent_reason,
        "results": {cr.section: cr.content for cr in r.results},
        "sources": [{"kind": s.kind, "year": s.year, "label": s.label, "rcept_no": s.rcept_no, "url": s.url}
                    for s in r.sources],
    }


def delete_report(session: Session, report_id: int) -> bool:
    r = session.get(Report, report_id)
    if r is None:
        return False
    session.delete(r)  # 재무·계산 결과·출처가 함께 지워진다 (회사 정보는 남는다)
    session.commit()
    return True
