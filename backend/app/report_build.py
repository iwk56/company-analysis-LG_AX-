"""계산 결과를 저장·응답용 사전(JSON)으로 바꾼다. 숫자는 calc 모듈이 이미 계산했고 여기서는 모양만 바꾼다."""
from dataclasses import asdict
from datetime import date

from .calc.models import Metric, YearAnalysis
from .fin_collect import DART_VIEWER, CompanyFinancials
from .recent_results import REPORTS, RecentResults

LAST_DAY = {6: 30, 9: 30}


def metric(m: Metric) -> dict:
    return {"value": m.value, "na_reason": m.na_reason, "year_end_only": m.year_end_only}


def build_sections(analysis: dict[int, YearAnalysis], recent: RecentResults | None) -> dict[str, dict]:
    """섹션 이름 → 저장할 내용. 연도는 문자열 키로 저장된다(JSON)."""
    sections = {
        "ratios": {y: {k: metric(m) for k, m in a.ratios.items()} for y, a in analysis.items()},
        "dupont": {y: {"metrics": {k: metric(m) for k, m in a.dupont.items()},
                       "driver": asdict(a.dupont_driver) if a.dupont_driver else None,
                       "driver_na": a.dupont_driver_na} for y, a in analysis.items()},
        "cashflow": {y: {"pattern": a.cashflow_pattern, "na_reason": a.cashflow_na} for y, a in analysis.items()},
        "signals": {y: {k: asdict(s) if s else None for k, s in a.signals.items()} for y, a in analysis.items()},
    }
    if recent:
        sections["recent_changes"] = {
            "changes": {k: metric(m) for k, m in recent.changes.items()},
            "operating_margin_current": metric(recent.operating_margin_current),
            "operating_margin_prior": metric(recent.operating_margin_prior),
        }
    return sections


def won(v: float | None) -> int | None:
    return None if v is None else round(v)


def data_as_of(res: CompanyFinancials, recent: RecentResults | None) -> date:
    """데이터 기준일: 최근 실적 기간의 끝, 최근 실적이 없으면 기준 사업연도의 12월 31일."""
    if recent is None:
        return date(res.latest_year, 12, 31)
    last_month = next(m for code, _, m in REPORTS if code == recent.reprt_code)
    return date(recent.year, last_month, LAST_DAY[last_month])


def source_rows(res: CompanyFinancials, recent: RecentResults | None) -> list[dict]:
    rows = [{"kind": "annual_report", "year": y, "label": f"{y} 사업보고서 ({res.basis}재무제표)",
             "rcept_no": res.receipts[y], "url": DART_VIEWER.format(res.receipts[y])} for y in sorted(res.receipts)]
    if recent and recent.rcept_no:
        rows.append({"kind": "interim_report", "year": recent.year, "label": f"{recent.year} {recent.report_name}보고서",
                     "rcept_no": recent.rcept_no, "url": DART_VIEWER.format(recent.rcept_no)})
    return rows
