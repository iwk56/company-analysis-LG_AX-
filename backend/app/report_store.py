"""리포트 저장·조회·삭제. 생성이 끝까지 성공했을 때만 save_report를 부른다(실패한 리포트는 저장하지 않음)."""
from dataclasses import fields
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .calc.models import YearAnalysis, YearFinancials
from .fin_collect import CompanyFinancials
from .recent_results import RecentResults
from .report_build import build_sections, data_as_of, source_rows, won
from .report_models import (
    Article, ArticleSearch, CalcResult, Comment, Company, FinancialYear, MacroSeries, RecentResult, Report, Source,
)

AMOUNT_FIELDS = [f.name for f in fields(YearFinancials) if f.name != "year"]


def save_report(session: Session, company: dict, res: CompanyFinancials, analysis: dict[int, YearAnalysis],
                recent: RecentResults | None, recent_reason: str | None,
                competitors: list[dict] | None = None, comparison: dict | None = None,
                news: dict | None = None, macro: list[dict] | None = None) -> int:
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
    if news is not None:  # {"query", "collected_at", "period_start", "period_end", "articles"}
        report.article_search = ArticleSearch(
            query=news["query"], collected_at=news["collected_at"], period_start=news["period_start"],
            period_end=news["period_end"], articles=[Article(**a) for a in news["articles"]])
    for m in macro or []:
        report.macro_series.append(MacroSeries(
            key=m["key"], label=m["label"], unit=m["unit"], stat_code=m["stat_code"], source_url=m["source_url"],
            period_start=date.fromisoformat(m["start"]), period_end=date.fromisoformat(m["end"]), points=m["points"]))
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
        "articles": _articles_view(r.article_search),
        "macro": [{"key": m.key, "label": m.label, "unit": m.unit, "stat_code": m.stat_code, "source_url": m.source_url,
                   "period_start": m.period_start.isoformat(), "period_end": m.period_end.isoformat(), "points": m.points}
                  for m in r.macro_series] or None,  # None = 수집 기능 이전에 만든 리포트
        "enrichments": {e.key: {"status": e.status, "by": e.by, "model": e.model, "content": e.content, "message": e.message,
                                "warnings": e.warnings, "created_at": e.created_at.isoformat()} for e in r.enrichments},
        "comments": {c.section_key: {"content": c.content, "updated_at": c.updated_at.isoformat()} for c in r.comments},
    }


def _articles_view(search: ArticleSearch | None) -> dict | None:
    """None = 기사 수집 기능 이전에 만든 리포트. 기사가 0건이면 items가 빈 목록."""
    if search is None:
        return None
    return {"query": search.query, "collected_at": search.collected_at.isoformat(),
            "period_start": search.period_start.isoformat(), "period_end": search.period_end.isoformat(),
            "items": [{"title": a.title, "summary": a.summary, "link": a.link, "published_at": a.published_at.isoformat()}
                      for a in search.articles]}


def set_comment(session: Session, report_id: int, section_key: str, content: str) -> dict | None | bool:
    """코멘트를 저장·수정한다. 내용이 비어 있으면(공백만 있어도) 삭제한다. 리포트가 없으면 False.

    저장하면 {"content", "updated_at"}, 삭제하면 None을 돌려준다.
    """
    if session.get(Report, report_id) is None:
        return False
    row = session.scalar(select(Comment).where(Comment.report_id == report_id, Comment.section_key == section_key))
    text = content.strip()
    if not text:
        if row is not None:
            session.delete(row)
            session.commit()
        return None
    now = datetime.now().replace(microsecond=0)
    if row is None:
        row = Comment(report_id=report_id, section_key=section_key, content=text, updated_at=now)
        session.add(row)
    else:
        row.content, row.updated_at = text, now
    session.commit()
    return {"content": row.content, "updated_at": row.updated_at.isoformat()}


def delete_report(session: Session, report_id: int) -> bool:
    r = session.get(Report, report_id)
    if r is None:
        return False
    session.delete(r)  # 재무·계산 결과·출처가 함께 지워진다 (회사 정보는 남는다)
    session.commit()
    return True
