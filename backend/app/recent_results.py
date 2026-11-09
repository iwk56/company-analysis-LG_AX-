"""최근 실적 박스: 가장 최근 정기보고서(반기 또는 3분기)의 연결 누적 손익을 전년 같은 기간과 비교한다. docs/spec.md 3장 '최근 실적 박스'.

- 어느 보고서: 5년 추이의 마지막 사업연도(N) 다음 해(N+1)의 3분기, 없으면 반기. 기간이 끝나기 전이거나 제출 전이면 박스를 만들지 않는다
- 누적 기준: 응답 행의 thstrm_add_amount(당기 누적)와 frmtrm_add_amount(전년 동기 누적)를 쓴다. thstrm_amount는 3개월 값이라 쓰지 않는다
- 1년 기준 지표(ROE·회전율 등)는 넣지 않는다
"""
from dataclasses import dataclass, field
from datetime import date

from .calc.models import Metric
from .calc.ratios import divide, profit_growth
from .fin_collect import CompanyFinancials
from .fin_fetch import HALF_REPORT, THIRD_QUARTER_REPORT, FinancialsFetcher
from .fin_mapping import RULES_BY_FIELD, find_row, parse_amount

# (보고서 코드, 이름, 누적 마지막 달) — 3분기가 있으면 3분기를 쓴다
REPORTS = ((THIRD_QUARTER_REPORT, "3분기", 9), (HALF_REPORT, "반기", 6))
ITEMS = ("revenue", "operating_income", "net_income_parent")
NOT_FILED = "아직 제출된 반기·3분기 보고서가 없습니다"


@dataclass
class RecentResults:
    report_name: str  # "반기" | "3분기"
    year: int
    reprt_code: str
    rcept_no: str
    basis: str  # "연결" | "별도"
    period_current: str  # 예: 2026.01~06
    period_prior: str  # 예: 2025.01~06
    current: dict[str, float | None]
    prior: dict[str, float | None]
    operating_margin_current: Metric
    operating_margin_prior: Metric
    changes: dict[str, Metric]  # revenue / operating_income / net_income_parent: 증감률, operating_margin: %p 차이(소수)
    notes: list[str] = field(default_factory=list)


def period_label(year: int, last_month: int) -> str:
    return f"{year}.01~{last_month:02d}"


def build_recent(data: dict, res: CompanyFinancials, year: int, reprt_code: str, name: str, last_month: int) -> RecentResults:
    rows = [r for r in data["list"] if r.get("sj_div") in ("IS", "CIS")]
    current, prior, notes = {}, {}, []
    for f in (*ITEMS, "net_income"):
        m = find_row(rows, RULES_BY_FIELD[f])
        current[f] = parse_amount(m.row.get("thstrm_add_amount")) if m else None
        prior[f] = parse_amount(m.row.get("frmtrm_add_amount")) if m else None
    if res.basis == "별도":  # 별도에는 지배주주 항목이 없다
        current["net_income_parent"], prior["net_income_parent"] = current["net_income"], prior["net_income"]
        notes.append("별도재무제표 기준: 지배주주 순이익은 당기순이익으로 대신함")
    for f in ITEMS:
        if current[f] is None or prior[f] is None:
            notes.append(f"{RULES_BY_FIELD[f].label}: 누적 값을 찾지 못함")

    margin_cur = divide(current["operating_income"], current["revenue"])
    margin_prior = divide(prior["operating_income"], prior["revenue"])
    changes = {f: profit_growth(current[f], prior[f], True) for f in ITEMS}  # 부호가 바뀌면 흑자전환·적자전환
    if margin_cur.value is not None and margin_prior.value is not None:
        changes["operating_margin"] = Metric(margin_cur.value - margin_prior.value)
    else:
        changes["operating_margin"] = Metric(None, margin_cur.na_reason or margin_prior.na_reason)
    return RecentResults(
        report_name=name, year=year, reprt_code=reprt_code, rcept_no=rows[0]["rcept_no"] if rows else "",
        basis=res.basis, period_current=period_label(year, last_month), period_prior=period_label(year - 1, last_month),
        current=current, prior=prior, operating_margin_current=margin_cur, operating_margin_prior=margin_prior,
        changes=changes, notes=notes)


async def collect_recent(fetcher: FinancialsFetcher, res: CompanyFinancials,
                         today: date | None = None) -> tuple[RecentResults | None, str | None]:
    """(최근 실적, 없을 때 사유). 5년 추이와 같은 연결/별도 기준의 보고서만 쓴다."""
    today = today or date.today()
    year = res.latest_year + 1
    for reprt_code, name, last_month in REPORTS:
        if today <= date(year, last_month, 30):  # 그 기간이 아직 끝나지 않았다
            continue
        data = await fetcher.fetch(res.corp_code, year, res.fs_div, reprt_code)
        if data["status"] == "000":
            return build_recent(data, res, year, reprt_code, name, last_month), None
    return None, NOT_FILED
