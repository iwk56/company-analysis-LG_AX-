"""AI에게 넘길 자료: 코드가 계산한 숫자를 문장 형태로 정리한다 (AI는 이 안의 숫자만 인용할 수 있다).

표시 규칙은 화면(frontend/src/format/number.ts)과 같다: 금액은 조 원·억 원, 비율은 소수 첫째 자리 %, 회전율·배수는 '배'.
"""
import re
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

RATIO_FACTORS = {
    "operating_margin": ("revenue", "operating_income"),
    "net_margin": ("revenue", "net_income"),
    "roe": ("net_income_parent", "equity_parent"),
    "roa": ("net_income", "total_assets"),
    "debt_ratio": ("total_liabilities", "total_equity"),
    "current_ratio": ("current_assets", "current_liabilities"),
    "interest_coverage": ("operating_income", "interest_expense"),
    "asset_turnover": ("revenue", "total_assets"),
    "receivable_turnover": ("revenue", "receivables"),
    "inventory_turnover": ("cost_of_sales", "inventory"),
    "revenue_growth": ("revenue",),
    "operating_income_growth": ("operating_income",),
    "asset_growth": ("total_assets",),
}
FACTOR_LABELS = {
    "revenue": "매출액",
    "operating_income": "영업이익",
    "net_income": "당기순이익",
    "net_income_parent": "지배주주 순이익",
    "total_assets": "자산총계",
    "total_liabilities": "부채총계",
    "total_equity": "자본총계",
    "equity_parent": "지배주주 자본",
    "current_assets": "유동자산",
    "current_liabilities": "유동부채",
    "receivables": "매출채권",
    "inventory": "재고자산",
    "cost_of_sales": "매출원가",
    "interest_expense": "이자비용·금융비용",
}
RATIO_AVERAGES = {
    "equity_parent": "평균 지배주주 자본 (ROE 분모)",
    "total_assets": "평균 자산총계 (ROA·총자산회전율 분모)",
    "receivables": "평균 매출채권 (매출채권회전율 분모)",
    "inventory": "평균 재고자산 (재고자산회전율 분모)",
}


def ratio_group_text(report: dict, keys: list[str]) -> str:
    """비율 해석(explain_ratios)용: 지정한 비율 키들의 전체 연도 흐름을 한 줄씩. ratios 블록(최근 3년)과 달리 전체 연도를 준다."""
    fys = {fy["year"]: fy for fy in report["financial_years"]}
    years = sorted(fys)
    res = report["results"]
    ratio = lambda year, key: (res["ratios"].get(str(year)) or {}).get(key)  # noqa: E731
    label_kind = {k: (label, kind) for k, label, kind in RATIO_KINDS}
    lines = []
    for key in keys:
        label, kind = label_kind[key]
        points = []
        for year in years:
            current = ratio(year, key)
            text = f"{year}년 {_metric_text(current, kind)}"
            previous = ratio(year - 1, key)
            if current and previous and current.get("value") is not None and previous.get("value") is not None:
                delta = current["value"] - previous["value"]
                change = pp(delta) if kind in ("percent", "change", "pp") else mult(delta)
                text += f" (전년 대비 {change})"
            points.append(text)
        lines.append(f"{label}: " + ", ".join(points))
    return "\n".join(lines)


def ratio_driver_text(report: dict, keys: list[str]) -> str:
    """비율의 분자·분모가 된 재무제표 항목과 연도별 증감을 코드로 계산해 해석 근거로 전달한다."""
    fys = {fy["year"]: fy for fy in report["financial_years"]}
    fields = list(dict.fromkeys(field for key in keys for field in RATIO_FACTORS[key]))
    lines = []
    for field in fields:
        label = FACTOR_LABELS[field]
        points = []
        for year in sorted(fys):
            value = fys[year].get(field)
            if value is None:
                points.append(f"{year}년 자료 없음")
                continue
            previous = fys.get(year - 1, {}).get(field)
            change = None if previous is None else value - previous
            change_text = "" if change is None else f" (전년 대비 {'+' if change >= 0 else ''}{won(change)})"
            points.append(f"{year}년 {won(value)}{change_text}")
        lines.append(f"{label}: " + ", ".join(points))
    average_fields = [field for field in fields if field in RATIO_AVERAGES]
    for field in average_fields:
        points = []
        for year in sorted(fys):
            current = fys[year].get(field)
            previous = fys.get(year - 1, {}).get(field)
            average_value = None if current is None else current if previous is None else (current + previous) / 2
            if average_value is None:
                points.append(f"{year}년 자료 없음")
                continue
            suffix = " (전기 자료 없어 기말 값)" if previous is None else ""
            points.append(f"{year}년 {won(average_value)}{suffix}")
        lines.append(f"{RATIO_AVERAGES[field]}: " + ", ".join(points))
    if "interest_coverage" in keys and report.get("interest_basis") == "금융비용":
        lines.append("이자보상배율 분모는 이자비용만이 아니라 금융비용입니다 (외환·파생상품 손실 등이 포함될 수 있음)")
    return "\n".join(lines)


def balance_change_text(report: dict, top: int = 2) -> str:
    """연도별 주요 재무상태표 계정 변동을 같은 해 현금흐름표 세부 항목과 함께 정리한다."""
    details = report.get("results", {}).get("balance_details") or {}
    years = sorted(int(year) for year in details)
    if len(years) < 2:
        return "연도별 세부 재무상태표 계정과 현금흐름표 거래가 저장되어 있지 않습니다."

    labels = {"assets": "자산", "liabilities": "부채"}
    match_terms = (
        (("매출채권", "기타채권"), ("매출채권",)),
        (("재고", "상품"), ("재고",)),
        (("유형자산", "건설중", "설비"), ("유형자산", "건설중", "설비")),
        (("무형자산",), ("무형자산",)),
        (("금융상품", "금융자산"), ("금융상품", "금융자산")),
        (("차입",), ("차입",)),
        (("사채",), ("사채",)),
        (("리스",), ("리스",)),
        (("매입채무", "미지급금"), ("매입채무", "미지급금")),
        (("계약부채", "선수금"), ("계약부채", "선수금")),
    )

    def account_events(name: str, events: list[dict]) -> list[dict]:
        normalized = re.sub(r"\s+", "", name)
        terms = next((cash_terms for account_terms, cash_terms in match_terms
                      if any(term in normalized for term in account_terms)), ())
        return [event for event in events if any(term in re.sub(r"\s+", "", event["name"]) for term in terms)]

    lines = [
        "각 기간의 자산·부채에서 전년 말 대비 금액이 크게 바뀐 세부 계정과 같은 사업연도 현금흐름표의 관련 항목입니다."
    ]
    for year in years:
        previous_year = year - 1
        if str(previous_year) not in details and previous_year not in details:
            continue
        current = details.get(str(year), details.get(year, {}))
        previous = details.get(str(previous_year), details.get(previous_year, {}))
        current_accounts = current.get("accounts") or {}
        previous_accounts = previous.get("accounts") or {}
        events = current.get("cashflow") or []
        for group, label in labels.items():
            before = {item["key"]: item for item in previous_accounts.get(group, [])}
            changes = []
            for item in current_accounts.get(group, []):
                old = before.get(item["key"])
                if old is None or old.get("value") is None or item.get("value") is None:
                    continue
                delta = item["value"] - old["value"]
                if delta:
                    changes.append((abs(delta), item, old, delta))
            changes.sort(key=lambda change: change[0], reverse=True)
            for _, item, old, delta in changes[:top]:
                change_text = f"{'+' if delta > 0 else ''}{won(delta)}"
                line = (f"{previous_year}→{year}년 {label}: {item['name']} "
                        f"{won(old['value'])}→{won(item['value'])} (증감 {change_text})")
                matches = account_events(item["name"], events)
                if matches:
                    event = max(matches, key=lambda match: abs(match.get("value") or 0))
                    event_value = event["value"]
                    event_text = f"{'+' if event_value > 0 else ''}{won(event_value)}"
                    line += f"; 같은 해 현금흐름표에 관련 항목 {event['name']} {event_text}"
                else:
                    line += "; 같은 해 현금흐름표에서 직접 연결되는 세부 거래는 확인되지 않음"
                lines.append(line)
    return "\n".join(lines)


def build_facts(report: dict, extracted: dict[str, dict]) -> Facts:
    """report: get_report() 결과. extracted: 성공한 추출 작업 키 → 내용(segments, rnd, finance)."""
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

    inc = res.get("income") or {}
    if inc.get(str(y)):
        lines = []
        for yr in (y - 1, y):
            st = inc.get(str(yr))
            if not st:
                continue
            r, m = st["rows"], st["margins"]
            lines.append(f"{yr}년: 매출액 {won(r['revenue'])}, 매출원가율 {pct(m.get('cost_of_sales'))}, 매출총이익 {won(r['gross_profit'])}(매출총이익률 {pct(m.get('gross_profit'))}), "
                         f"판관비 {won(r['sga'])}(판관비율 {pct(m.get('sga'))}), 영업이익 {won(r['operating_income'])}(영업이익률 {pct(m.get('operating_income'))}), "
                         f"영업외손익 {won(r['non_operating'])}(그중 금융손익 {won(r['finance_net'])}, 기타 {won(r['other_non_operating'])}), "
                         f"법인세비용차감전순이익 {won(r['pretax_income'])}, 법인세 {won(r['income_tax'])}(유효세율 {pct(st.get('effective_tax_rate'))}), "
                         f"당기순이익 {won(r['net_income'])}(순이익률 {pct(m.get('net_income'))})")
        b = inc[str(y)].get("bridge")
        if b:
            lines.append(f"{y}년 영업이익 변화 {won(b['total'])} = 매출 증가 효과 {won(b['volume'])} + 매출총이익률 변화 효과 {won(b['margin'])} "
                         f"+ 판관비 증감 효과 {won(b['sga'])} + 기타 {won(b['other'])} (코드 계산)")
        blocks["income"] = "\n".join(lines)

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
    extra = []
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
    text = won(v) if col["format"] == "amount" else mult(v) if col["format"] == "multiple" else pct(v, col["format"] == "change")
    return text + (f"({cell['rank']}위)" if cell.get("rank") else "")


def _segments_text(seg: dict) -> str:
    lines = [f"사업부문(품목)별 매출 ({seg['year']}년, 전년 대비 증감률은 코드가 계산)"]
    for p in seg["products"]:
        lines.append(f"{p['name']}: {won(p['current_won'])}, 비중 {pct(p['share'])}"
                     + (f", 전년 대비 {pct(p['growth'], True)}" if p.get("growth") is not None else ""))
    if seg.get("overseas_share") is not None:
        lines.append(f"해외 매출 비중(지역별 매출 기준) {pct(seg['overseas_share'])}")
    return "\n".join(lines)
