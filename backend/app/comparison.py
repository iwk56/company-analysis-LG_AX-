"""경쟁사 비교표 계산 (docs/spec.md 3장 "경쟁사 비교"). 숫자·순위·평균 대비·위치 문장은 모두 코드로 만든다.

지표는 COLUMN_DEFS 목록 하나로 정의한다. 응답의 columns가 이 목록에서 나오고 화면은 columns를 보고 그리기만 하므로,
Phase 5-B에서 PER·PBR·시가총액을 추가할 때는 이 목록에 정의를 더하고 값을 채우면 열이 늘어난다.
"""
from dataclasses import dataclass

from .calc.models import NO_DATA, Metric, YearAnalysis, YearFinancials
from .fin_collect import CompanyFinancials


@dataclass(frozen=True)
class ColumnDef:
    key: str
    label: str
    format: str  # amount(원, 화면에서 억 원) | percent | change(부호 붙는 증감률)
    higher_is_better: bool | None  # True 높을수록 1위, False 낮을수록 1위(부채비율), None 순위 없음(5-B의 PER·PBR)
    ranked: bool = True  # 순위를 매기는 열인지


COLUMN_DEFS: tuple[ColumnDef, ...] = (
    ColumnDef("revenue", "매출액", "amount", True),
    ColumnDef("revenue_growth", "매출액증가율", "change", True),
    ColumnDef("operating_margin", "영업이익률", "percent", True),
    ColumnDef("roe", "ROE", "percent", True),
    ColumnDef("debt_ratio", "부채비율", "percent", False),  # 낮을수록 1위
)

RANK_RULE = ("순위는 값이 같으면 같은 순위로 매기고, 해당 없음·자료 없음인 기업은 순위와 평균에서 뺍니다. "
             "위의 한 줄은 순위가 아니라 평균(분석 기업 포함) 대비입니다. 우위는 부채비율을 뺀 지표에서는 평균보다 높은 경우, "
             "부채비율에서는 평균보다 낮은 경우이고, 그 반대는 열위, 평균과 같으면 평균 수준입니다.")


@dataclass
class Entry:
    """비교표에 들어가는 기업 한 곳 (기준 사업연도의 값)."""
    corp_code: str
    corp_name: str
    basis: str  # 연결 | 별도
    source_url: str | None
    values: dict[str, Metric]
    is_target: bool = False


@dataclass
class Excluded:
    corp_code: str
    corp_name: str
    reason: str


def build_entry(company: dict, res: CompanyFinancials, analysis: dict[int, YearAnalysis], base_year: int,
                is_target: bool = False) -> Entry | Excluded:
    """기준 사업연도의 값을 뽑는다. 그 연도 자료가 없거나 매출액이 없으면 제외 사유를 돌려준다."""
    fin: YearFinancials | None = res.years.get(base_year)
    if fin is None or base_year not in analysis:
        return Excluded(company["corp_code"], company["corp_name"], f"데이터 부족으로 제외 ({base_year} 사업연도 자료 없음)")
    if fin.revenue is None:
        return Excluded(company["corp_code"], company["corp_name"], f"데이터 부족으로 제외 ({base_year} 매출액 없음)")
    ratios = analysis[base_year].ratios
    values = {"revenue": Metric(fin.revenue)}
    for d in COLUMN_DEFS:
        if d.key not in values:
            values[d.key] = ratios.get(d.key, Metric(None, NO_DATA))
    return Entry(company["corp_code"], company["corp_name"], res.basis, res.source_link(base_year), values, is_target)


def _rank(value: float, all_values: list[float], higher_is_better: bool) -> int:
    """같은 값은 같은 순위, 다음 순위는 건너뛴다 (1, 1, 3). 순위 = 나보다 좋은 기업 수 + 1."""
    better = sum(1 for v in all_values if (v > value if higher_is_better else v < value))
    return better + 1


def _position(target: Entry, vs: dict[str, str | None]) -> dict:
    """업계 내 위치 한 줄: 표의 ▲▼(평균 대비)와 같은 기준. 부채비율은 평균보다 낮아야 '우위'다."""
    better, worse, same, unavailable = [], [], [], []
    for d in COLUMN_DEFS:
        if not d.ranked or d.higher_is_better is None:
            continue
        v = vs[d.key]
        if v is None:
            unavailable.append(d.label)
        elif v == "same":
            same.append(d.label)
        elif (v == "above") == d.higher_is_better:
            better.append(d.label)
        else:
            worse.append(d.label)
    judged = len(better) + len(worse) + len(same)
    if judged == 0:
        text = "비교할 수 있는 지표가 없어 업계 내 위치를 판단하지 못했습니다."
    else:
        parts = []
        if better:
            parts.append(f"{len(better)}개 우위({', '.join(better)})")
        if worse:
            parts.append(f"{len(worse)}개 열위({', '.join(worse)})")
        if same:
            parts.append(f"{len(same)}개 평균 수준({', '.join(same)})")
        text = f"{target.corp_name}: 비교한 {judged}개 지표 중 " + ", ".join(parts) + "."
        if unavailable:
            text += f" ({', '.join(unavailable)}는 비교할 수 없음)"
    return {"better": better, "worse": worse, "same": same, "unavailable": unavailable, "text": text}


def build_comparison(base_year: int, target: Entry, others: list[Entry | Excluded]) -> dict:
    entries = [target] + [o for o in others if isinstance(o, Entry)]
    excluded = [o for o in others if isinstance(o, Excluded)]

    averages: dict[str, float | None] = {}
    counts: dict[str, int] = {}
    ranks: dict[str, dict[str, int | None]] = {e.corp_code: {} for e in entries}
    for d in COLUMN_DEFS:
        usable = [e.values[d.key].value for e in entries if e.values[d.key].value is not None]
        counts[d.key] = len(usable)
        averages[d.key] = sum(usable) / len(usable) if usable else None
        for e in entries:
            v = e.values[d.key].value
            # 비교 대상이 2곳 미만이면 순위·평균 대비는 의미가 없어 비워 둔다
            ranks[e.corp_code][d.key] = (_rank(v, usable, d.higher_is_better)
                                         if v is not None and d.ranked and d.higher_is_better is not None and len(usable) >= 2 else None)

    def vs_average(e: Entry, key: str) -> str | None:
        v, avg = e.values[key].value, averages[key]
        if v is None or avg is None or counts[key] < 2:
            return None
        if abs(v - avg) <= 1e-9 * max(1.0, abs(avg)):  # 평균 계산의 부동소수점 오차는 같은 값으로 본다
            return "same"
        return "above" if v > avg else "below"

    rows = [{"corp_code": e.corp_code, "corp_name": e.corp_name, "is_target": e.is_target, "basis": e.basis,
             "source_url": e.source_url,
             "values": {d.key: {"value": e.values[d.key].value, "na_reason": e.values[d.key].na_reason,
                                "rank": ranks[e.corp_code][d.key], "vs_average": vs_average(e, d.key)}
                        for d in COLUMN_DEFS}} for e in entries]
    scatter = [{"corp_code": e.corp_code, "corp_name": e.corp_name, "is_target": e.is_target,
                "x": e.values["revenue_growth"].value, "y": e.values["operating_margin"].value}
               for e in entries if e.values["revenue_growth"].value is not None and e.values["operating_margin"].value is not None]
    return {
        "base_year": base_year,
        "columns": [{"key": d.key, "label": d.label, "format": d.format, "higher_is_better": d.higher_is_better,
                     "ranked": d.ranked} for d in COLUMN_DEFS],
        "rows": rows,
        "averages": averages,
        "ranked_counts": counts,
        "excluded": [{"corp_code": x.corp_code, "corp_name": x.corp_name, "reason": x.reason} for x in excluded],
        "scatter": scatter,
        "position": _position(target, {d.key: vs_average(target, d.key) for d in COLUMN_DEFS}),
        "rank_rule": RANK_RULE,
    }
