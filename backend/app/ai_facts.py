"""AI에게 넘길 자료: 코드가 계산한 숫자를 문장 형태로 정리한다 (AI는 이 안의 숫자만 인용할 수 있다).

표시 규칙은 화면(frontend/src/format/number.ts)과 같다: 금액은 조 원·억 원, 비율은 소수 첫째 자리 %, 회전율·배수는 '배'.
"""
from dataclasses import dataclass

from .ai_verify import numbers_in

JO, EOK = 1e12, 1e8


def won(v: float | int | None) -> str:
    if v is None:
        return "자료 없음"
    if abs(v) < 0.1 * JO:
        return f"{v / EOK:,.0f}억 원"
    return f"{v / JO:,.1f}조 원"


def pct(v: float | None, signed: bool = False) -> str:
    if v is None:
        return "자료 없음"
    return f"{v * 100:+.1f}%" if signed else f"{v * 100:.1f}%"


def pp(v: float | None) -> str:
    return "자료 없음" if v is None else f"{v * 100:+.1f}%p"


def mult(v: float | None) -> str:
    return "자료 없음" if v is None else f"{v:.1f}배"


@dataclass
class Facts:
    blocks: dict[str, str]  # 섹션 키 → 자료 문단
    allowed: set[str]  # 자료에 나온 숫자 토큰 (AI 문장 검증용)


def _metric_text(m: dict | None, kind: str) -> str:
    if not m:
        return "자료 없음"
    if m.get("value") is None:
        return m.get("na_reason") or "자료 없음"
    v = m["value"]
    return {"percent": pct(v), "change": pct(v, True), "multiple": mult(v), "pp": pp(v)}[kind]


RATIO_KINDS = [("operating_margin", "영업이익률", "percent"), ("net_margin", "순이익률", "percent"), ("roe", "ROE", "percent"),
               ("roa", "ROA", "percent"), ("debt_ratio", "부채비율", "percent"), ("current_ratio", "유동비율", "percent"),
               ("interest_coverage", "이자보상배율", "multiple"), ("asset_turnover", "총자산회전율", "multiple"),
               ("receivable_turnover", "매출채권회전율", "multiple"), ("inventory_turnover", "재고자산회전율", "multiple"),
               ("revenue_growth", "매출액증가율", "change"), ("operating_income_growth", "영업이익증가율", "change"),
               ("asset_growth", "총자산증가율", "change")]


def build_facts(report: dict, extracted: dict[str, dict]) -> Facts:
    """report: get_report() 결과. extracted: 성공한 추출 작업 키 → 내용(segments, rnd, finance, employees)."""
    y = report["base_year"]
    fys = {fy["year"]: fy for fy in report["financial_years"]}
    res = report["results"]
    ratio = lambda year, key: (res["ratios"].get(str(year)) or {}).get(key)  # noqa: E731
    cur = fys.get(y, {})
    blocks: dict[str, str] = {}

    head = f"{report['company']['corp_name']} / 업종: {report['company'].get('industry_name') or '자료 없음'} / 기준 사업연도 {y} / {report['basis']}재무제표"
    blocks["header"] = head

    sig = res["signals"].get(str(y)) or {}
    sigtext = lambda k: (f"{sig[k]['level']}: {sig[k]['reason']}" if sig.get(k) else "판정 없음")  # noqa: E731
    cfo_prev = fys.get(y - 1, {}).get("cfo")
    blocks["core_cards"] = "\n".join([
        f"매출 성장률 {_metric_text(ratio(y, 'revenue_growth'), 'change')} (신호등 {sigtext('revenue_growth')})",
        f"영업이익률 {_metric_text(ratio(y, 'operating_margin'), 'percent')}, 전년 {_metric_text(ratio(y - 1, 'operating_margin'), 'percent')} (신호등 {sigtext('operating_margin')})",
        f"부채비율 {_metric_text(ratio(y, 'debt_ratio'), 'percent')}, 전년 {_metric_text(ratio(y - 1, 'debt_ratio'), 'percent')} (신호등 {sigtext('debt_ratio')})",
        f"영업현금흐름 {won(cur.get('cfo'))}, 전년 {won(cfo_prev)} (신호등 {sigtext('operating_cashflow')})",
    ])

    years = sorted(fys)
    blocks["trend"] = "\n".join(
        f"{yr}년: 매출액 {won(fys[yr].get('revenue'))}, 영업이익 {won(fys[yr].get('operating_income'))}, 영업이익률 {_metric_text(ratio(yr, 'operating_margin'), 'percent')}"
        for yr in years)

    lines = []
    for key, label, kind in RATIO_KINDS:
        lines.append(f"{label}: " + ", ".join(f"{yr}년 {_metric_text(ratio(yr, key), kind)}" for yr in years[-3:]))
    if report.get("interest_basis") == "금융비용":
        lines.append("이자보상배율은 이자비용 대신 금융비용으로 계산한 값(외환·파생상품 손실 포함 가능)")
    blocks["ratios"] = "\n".join(lines)

    dp = res["dupont"].get(str(y)) or {}
    dm = dp.get("metrics") or {}
    drv = dp.get("driver")
    blocks["dupont"] = "\n".join([
        f"{y}년 순이익률 {_metric_text(dm.get('net_margin'), 'percent')}, 총자산회전율 {_metric_text(dm.get('asset_turnover'), 'multiple')}, "
        f"재무레버리지 {_metric_text(dm.get('leverage'), 'multiple')}, ROE {_metric_text(dm.get('roe'), 'percent')}",
        f"ROE가 변한 주된 요인: {drv['factor']} (전년 대비 {pct(drv['changes'][drv['factor']], True)})" if drv else f"ROE 변화 요인: {dp.get('driver_na') or '자료 없음'}",
    ])

    blocks["cashflow"] = "\n".join(
        f"{yr}년: 영업 {won(fys[yr].get('cfo'))}, 투자 {won(fys[yr].get('cfi'))}, 재무 {won(fys[yr].get('cff'))}, 패턴 {(res['cashflow'].get(str(yr)) or {}).get('pattern') or '판정 없음'}"
        for yr in years)

    rr = report.get("recent_results")
    if rr:
        ch = (res.get("recent_changes") or {})
        c = ch.get("changes", {})
        blocks["recent_results"] = "\n".join([
            f"{rr['period_current']} 누적 vs {rr['period_prior']} ({rr['report_name']}보고서, {rr['basis']})",
            f"매출액 {won(rr['current'].get('revenue'))} (전년 동기 {won(rr['prior'].get('revenue'))}, {_metric_text(c.get('revenue'), 'change')})",
            f"영업이익 {won(rr['current'].get('operating_income'))} (전년 동기 {won(rr['prior'].get('operating_income'))}, {_metric_text(c.get('operating_income'), 'change')})",
            f"영업이익률 {_metric_text(ch.get('operating_margin_current'), 'percent')} (전년 동기 {_metric_text(ch.get('operating_margin_prior'), 'percent')})",
            f"지배주주 순이익 {won(rr['current'].get('net_income_parent'))} (전년 동기 {won(rr['prior'].get('net_income_parent'))}, {_metric_text(c.get('net_income_parent'), 'change')})",
        ])

    comp = res.get("comparison")
    if comp:
        lines = [f"위치 요약: {comp['position']['text']}"]
        for row in comp["rows"]:
            cells = ", ".join(f"{col['label']} {_cell(col, row['values'][col['key']])}" for col in comp["columns"])
            lines.append(f"{row['corp_name']}{'(분석 기업)' if row['is_target'] else ''}: {cells}")
        blocks["competitors"] = "\n".join(lines)

    seg = extracted.get("extract_segments")
    if seg:
        blocks["segments"] = _segments_text(seg)
    rnd = extracted.get("extract_rnd")
    emp = extracted.get("employees")
    extra = []
    if emp:
        extra.append(f"직원 현황({emp['year']}년 사업보고서): 직원 수 {emp['count']:,}명, 평균 근속연수 {emp['avg_tenure_years']}년, 1인 평균 급여 {round(emp['avg_salary_won'] / 1e4):,}만 원"
                     if emp.get("avg_tenure_years") is not None and emp.get("avg_salary_won") is not None else f"직원 현황: 직원 수 {emp['count']:,}명")
    if rnd:
        extra.append(f"연구개발비 {won(rnd['amount_won'])}, 매출 대비 {pct(rnd['ratio_to_revenue'])}")
    fin = extracted.get("extract_finance")
    if fin and fin.get("interest_expense_won") is not None:
        extra.append(f"실제 이자비용(주석) {won(fin['interest_expense_won'])}, 실제 이자비용 기준 이자보상배율 {mult(fin.get('coverage_actual'))}")
    if fin and fin.get("net_vs_operating"):
        n = fin["net_vs_operating"]
        items = ", ".join(f"{i['label']} {won(i['amount_won'])}" for i in n["items"])
        extra.append(f"{n['period_label']} 지배주주 순이익({won(n['net_income_parent'])})이 영업이익({won(n['operating_income'])})보다 큼. "
                     + (f"주석의 금융수익 항목: {items}" if items else "주석의 금융수익 항목은 확인하지 못함"))
    blocks["overview"] = "\n".join([head, f"{y}년 매출액 {won(cur.get('revenue'))}, 영업이익 {won(cur.get('operating_income'))}", *extra])
    if extra:
        blocks["extra"] = "\n".join(extra)

    allowed = set()
    for text in blocks.values():
        allowed |= numbers_in(text)
    return Facts(blocks=blocks, allowed=allowed)


def _cell(col: dict, cell: dict) -> str:
    v = cell.get("value")
    if v is None:
        return cell.get("na_reason") or "자료 없음"
    text = won(v) if col["format"] == "amount" else pct(v, col["format"] == "change")
    return text + (f"({cell['rank']}위)" if cell.get("rank") else "")


def _segments_text(seg: dict) -> str:
    lines = [f"사업부문(품목)별 매출 ({seg['year']}년, 전년 대비 증감률은 코드가 계산)"]
    for p in seg["products"]:
        lines.append(f"{p['name']}: {won(p['current_won'])}, 비중 {pct(p['share'])}"
                     + (f", 전년 대비 {pct(p['growth'], True)}" if p.get("growth") is not None else ""))
    if seg.get("overseas_share") is not None:
        lines.append(f"해외 매출 비중(지역별 매출 기준) {pct(seg['overseas_share'])}")
    return "\n".join(lines)
