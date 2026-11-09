"""한 기업의 5개 사업연도 재무제표를 모아 calc 모듈의 입력(YearFinancials)으로 만든다.

결정 사항(2026-11-02)
- 연결/별도는 기업 단위로 하나로 통일: 최신 사업연도에 연결이 있으면 모든 연도를 연결로, 없으면 별도로(섞지 않는다)
- 재작성된 과거 수치: 연도마다 그 연도가 들어 있는 가장 최신 보고서의 값을 쓴다
  보고서 1건에 당기·전기·전전기 3개 연도가 있어 N, N-1, N-2 보고서 3건이면 N-4~N 5개 연도가 모인다
  (N~N-2 ← N 보고서, N-3 ← N-1 보고서의 전전기, N-4 ← N-2 보고서의 전전기). 호출 수는 기업당 3건
- 첫 연도(N-4)의 기초(N-5) 값은 쓰지 않는다(spec: 첫 연도는 기말 값만)
- 별도 기준이면 DART에 지배주주 항목이 없어 지배주주 순이익=당기순이익, 지배주주 자본=자본총계로 대신하고 표시한다
"""
from dataclasses import dataclass, field
from datetime import date

from .calc.models import YearFinancials
from .calc.balance import snapshot as balance_snapshot
from .fin_fetch import FinancialsFetcher
from .calc.cash import detail as cash_detail
from .fin_mapping import COLUMNS, RULES, RULES_BY_FIELD, extract, parse_amount, unmatched_candidates

DART_VIEWER = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"
CORE_FIELDS = ("revenue", "total_assets")  # 둘 다 없으면 그 연도는 자료가 없는 것으로 본다


class NoFinancialsError(Exception):
    pass


@dataclass
class CompanyFinancials:
    corp_code: str
    basis: str  # "연결" | "별도"
    latest_year: int
    fs_div: str = "CFS"  # DART 구분: CFS 연결, OFS 별도
    years: dict[int, YearFinancials] = field(default_factory=dict)
    receipts: dict[int, str] = field(default_factory=dict)  # 연도 → 접수번호(rcept_no)
    used: dict[tuple[int, str], dict] = field(default_factory=dict)  # (연도, 필드) → 쓴 계정
    missing: dict[int, list[str]] = field(default_factory=dict)  # 연도 → 매칭 못 한 표준 항목
    candidates: dict[str, list[str]] = field(default_factory=dict)  # 항목 → 후보 계정(최신 보고서 기준)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cf_detail: dict | None = None  # 최신 보고서 현금흐름표 전체 행 (2026-11-04 현금흐름 분석)
    balance_details: dict[int, dict] = field(default_factory=dict)  # 5개년 재무상태표 계정·현금흐름표 세부 행

    @property
    def year_count(self) -> int:
        return len(self.years)

    def interest_basis(self) -> str | None:
        """이자보상배율의 분모가 실제 이자비용인지, 대체한 금융비용인지 (최신 연도 기준)."""
        u = self.used.get((self.latest_year, "interest_expense"))
        if not u:
            return None
        return "금융비용" if u["account_id"] == "ifrs-full_FinanceCosts" or u["account_nm"].replace(" ", "") in ("금융비용", "금융원가") else "이자비용"

    def source_link(self, year: int) -> str | None:
        return DART_VIEWER.format(self.receipts[year]) if year in self.receipts else None


async def _find_latest(fetcher: FinancialsFetcher, corp_code: str, today: date):
    for year in (today.year - 1, today.year - 2):
        for fs_div, basis in (("CFS", "연결"), ("OFS", "별도")):
            data = await fetcher.fetch(corp_code, year, fs_div)
            if data["status"] == "000":
                return year, fs_div, basis, data
    raise NoFinancialsError("최근 2개 사업연도의 사업보고서 재무제표를 찾지 못했습니다")


def _add_filing(result: CompanyFinancials, data: dict, filing_year: int, columns: tuple[str, ...]):
    """보고서 한 건의 열(당기/전기/전전기)로 연도를 채운다. 더 최신 보고서가 이미 채운 연도와 5년 범위 밖 연도는 건너뛴다."""
    rows = [r for r in data["list"] if r.get("sj_div") in ("BS", "IS", "CIS", "CF")]
    values, matched = extract(rows)
    rcept = rows[0]["rcept_no"] if rows else ""
    for col in columns:
        year = filing_year - COLUMNS.index(col)
        if year in result.years or year < result.latest_year - 4:
            continue
        vals = dict(values[col])
        if all(vals.get(f) is None for f in CORE_FIELDS):
            continue  # 상장 전이라 비어 있는 열
        if result.basis == "별도":  # 별도에는 지배주주 항목이 없다
            vals["net_income_parent"] = vals.get("net_income")
            vals["equity_parent"] = vals.get("total_equity")
        result.years[year] = YearFinancials(year=year, **{f: vals.get(f) for f in RULES_BY_FIELD})
        result.receipts[year] = rcept
        result.balance_details[year] = balance_snapshot(rows, f"{col}_amount", parse_amount)
        for f, m in matched.items():
            result.used[(year, f)] = {"account_id": m.row["account_id"], "account_nm": m.row["account_nm"],
                                      "sj_div": m.row["sj_div"], "by": m.by}
        result.missing[year] = [f for f in RULES_BY_FIELD if vals.get(f) is None]
    for f, m in matched.items():
        note = f"{RULES_BY_FIELD[f].label}: {m.note}" if m.note else None
        if note and note not in result.notes:
            result.notes.append(note)
    return rows, matched


async def collect_company(fetcher: FinancialsFetcher, corp_code: str, today: date | None = None) -> CompanyFinancials:
    today = today or date.today()
    latest_year, fs_div, basis, data = await _find_latest(fetcher, corp_code, today)
    result = CompanyFinancials(corp_code=corp_code, basis=basis, latest_year=latest_year, fs_div=fs_div)
    rows, _ = _add_filing(result, data, latest_year, COLUMNS)  # N, N-1, N-2

    for older_year in (latest_year - 1, latest_year - 2):  # N-3, N-4는 이 보고서들의 전전기 열 (같은 연결/별도 기준으로만)
        older = await fetcher.fetch(corp_code, older_year, fs_div)
        if older["status"] == "000":
            _add_filing(result, older, older_year, COLUMNS)

    if basis == "별도":
        result.notes.append("별도재무제표 기준: 지배주주 순이익·자본은 당기순이익·자본총계로 대신함")
    if not any(r.get("account_id") in ("ifrs-full_CurrentAssets", "ifrs-full_CurrentLiabilities") or
               r.get("account_nm") in ("유동자산", "유동부채") for r in rows if r.get("sj_div") == "BS"):
        result.warnings.append("재무상태표에 유동/비유동 구분이 없습니다 — 금융업일 수 있음")
    result.cf_detail = cash_detail(rows, parse_amount)
    latest_missing = result.missing.get(latest_year, [])
    result.candidates = unmatched_candidates(rows, latest_missing)
    return result


def to_year_list(result: CompanyFinancials) -> list[YearFinancials]:
    return [result.years[y] for y in sorted(result.years)]


ITEM_LABELS = {r.field: r.label for r in RULES}
