"""4장 체크리스트 판정 (docs/spec.md 3장 "4장 체크리스트 판정"). 모두 코드가 판정하고 AI는 쓰지 않는다.

상태: check(확인 필요) · clear(이상 없음) · unknown(확인 불가) · info(참고, 위험 요인만).
"확인 필요"·"확인 불가"에는 항상 이유를 붙이고, 이유 문장은 아래 틀로 코드가 만든다. 기준이 여러 개 걸리면 모두 쉼표로 잇는다.
기준값은 이 도구의 참고 기준이며 법적·공식 기준이 아니다(화면에 안내).
"""
from .ai_facts import mult, pct, pp, won

CHECK, CLEAR, UNKNOWN, INFO = "check", "clear", "unknown", "info"
PREFIX = {CHECK: "확인 필요", CLEAR: "이상 없음", UNKNOWN: "확인 불가", INFO: "참고"}
DEBT_LIMIT, DEBT_JUMP, COVERAGE_MIN = 2.0, 0.5, 1.0
SEGMENT_LIMIT, CUSTOMER_LIMIT = 0.5, 0.3
NOTE = "참고 기준이며 법적·공식 기준이 아닙니다"
CONCENTRATION_NOTE = "집중 자체가 문제는 아니며, 그 사업의 업황에 실적이 크게 좌우될 수 있다는 뜻입니다"
ACCOUNTING_ITEMS = (("audit_opinion", "감사의견"), ("extract_going_concern", "계속기업 불확실성"), ("corrections", "정정공시"),
                    ("extract_related_party", "특수관계자 거래"))


def _won(v) -> str:
    return won(v).replace("-", "−")


def _item(key: str, label: str, status: str, reasons: list[str], **extra) -> dict:
    return {"key": key, "label": label, "status": status, "reasons": reasons,
            "text": f"{PREFIX[status]}: {', '.join(reasons)}" if reasons else PREFIX[status], **extra}


def _period_label(period: str) -> str:
    """'2026.01~06' → '2026년 1~6월'."""
    try:
        year, months = period.split(".", 1)
        a, b = months.split("~")
        return f"{year}년 {int(a)}~{int(b)}월"
    except ValueError:
        return period


def _fy(report: dict, year: int) -> dict:
    return next((f for f in report["financial_years"] if f["year"] == year), {})


def _ratio(report: dict, year: int, key: str) -> float | None:
    return ((report["results"].get("ratios") or {}).get(str(year)) or {}).get(key, {}).get("value")


def one_off(report: dict) -> dict:
    """기준 사업연도 N과 최근 누적 기간 둘 다 본다. 하나라도 걸리면 확인 필요(걸린 기간 모두 이유에)."""
    y = report["base_year"]
    periods = [(f"{y}년", _fy(report, y).get("net_income_parent"), _fy(report, y).get("operating_income"))]
    rr = report.get("recent_results")
    if rr:
        periods.append((_period_label(rr["period_current"]), rr["current"].get("net_income_parent"), rr["current"].get("operating_income")))
    usable = [(lbl, net, op) for lbl, net, op in periods if net is not None and op is not None]
    reasons = []
    for lbl, net, op in usable:
        if op < 0 < net:
            reasons.append(f"영업은 적자인데 순이익은 흑자({lbl} 영업이익 {_won(op)}, 순이익 {_won(net)})")
        elif net > op:
            reasons.append(f"영업 밖에서 생긴 이익이 큼({lbl} 순이익 {_won(net)} > 영업이익 {_won(op)})")
    if reasons:
        return _item("one_off", "일회성 이익", CHECK, reasons)
    if not usable:
        return _item("one_off", "일회성 이익", UNKNOWN, ["영업이익·순이익 자료 없음"])
    lbl, net, op = usable[0]
    return _item("one_off", "일회성 이익", CLEAR, [f"{lbl} 순이익 {_won(net)} ≤ 영업이익 {_won(op)}"])


def cashflow(report: dict) -> dict:
    y = report["base_year"]
    cfo, ni = _fy(report, y).get("cfo"), _fy(report, y).get("net_income")
    if cfo is None or ni is None:
        return _item("cashflow", "현금흐름", UNKNOWN, ["현금흐름 자료 없음"])
    if cfo < 0:
        return _item("cashflow", "현금흐름", CHECK, [f"영업으로 현금이 빠져나감(영업현금흐름 {_won(cfo)})"])
    if cfo < ni:
        return _item("cashflow", "현금흐름", CHECK, [f"이익만큼 현금이 들어오지 않음(영업현금흐름 {_won(cfo)} < 순이익 {_won(ni)})"])
    return _item("cashflow", "현금흐름", CLEAR, [f"영업현금흐름 {_won(cfo)} ≥ 순이익 {_won(ni)}"])


def debt(report: dict, finance: dict | None) -> dict:
    """이자보상배율은 주석의 실제 이자비용 기준(원문 대조를 통과한 값)을 먼저 쓰고, 없으면 재무비율 값과 그 기준을 쓴다."""
    y = report["base_year"]
    dr, prev = _ratio(report, y, "debt_ratio"), _ratio(report, y - 1, "debt_ratio")
    if dr is None:
        return _item("debt", "부채·이자", UNKNOWN, ["부채비율 자료 없음"])
    if finance and finance.get("coverage_actual") is not None:
        cov, basis = finance["coverage_actual"], "실제 이자비용 기준"
    else:
        cov = _ratio(report, y, "interest_coverage")
        basis = "금융비용 기준" if report.get("interest_basis") == "금융비용" else "이자비용 기준"
    reasons = []
    if dr > DEBT_LIMIT:
        reasons.append(f"빌린 돈이 자기 돈의 2배 넘음(부채비율 {pct(dr)})")
    if prev is not None and dr - prev > DEBT_JUMP:
        reasons.append(f"부채비율이 1년 새 크게 오름({pct(prev)} → {pct(dr)}, {pp(dr - prev)})")
    if cov is not None and cov < COVERAGE_MIN:
        reasons.append(f"영업이익으로 이자를 다 못 냄(이자보상배율 {mult(cov).replace('-', '−')}, {basis})")
    if reasons:
        return _item("debt", "부채·이자", CHECK, reasons, coverage_basis=basis)
    tail = f", 이자보상배율 {mult(cov)}({basis})" if cov is not None else ""
    return _item("debt", "부채·이자", CLEAR, [f"부채비율 {pct(dr)}{tail}"], coverage_basis=basis)


def dependence(segments: dict | None, position: dict | None, position_status: str | None) -> dict:
    """최대 부문 비중(6-A 원문 대조를 통과한 값, 코드 계산)과 회사가 밝힌 한 고객의 비중(검증된 인용 안의 %)으로 판정한다.
    여러 고객을 합친 비중(예: 10대 매출처)은 판정에 쓰지 않고 참고로만 보여준다. 고객 문장이 없으면 부문 비중만으로 판정한다."""
    products = (segments or {}).get("products") or []
    top = max(products, key=lambda p: p.get("share") or 0) if products else None
    customers = (position or {}).get("customers") or []
    singles = [c for c in customers if c["scope"] == "single" and c["share"] is not None]
    refs = [{"share_text": c["share_text"], "quote": c["quote"]}  # 참고: 여러 고객 합계 등 (판정에 쓰지 않음)
            for c in customers if c not in singles and c["share"] is not None]
    reasons = []
    if top and top.get("share") is not None and top["share"] >= SEGMENT_LIMIT:
        reasons.append(f"한 사업에 집중됨({top['name']} {pct(top['share'])})")
    best = max(singles, key=lambda c: c["share"]) if singles else None
    if best and best["share"] >= CUSTOMER_LIMIT:
        reasons.append(f"매출이 특정 고객에 몰림(회사가 밝힌 최대 고객 비중 {best['share_text']}, {best['quote']['cite']})")
    if position_status == "ok" or position:
        customer_note = (f"회사가 밝힌 최대 고객 비중 {best['share_text']}" if best else "한 고객의 매출 비중 언급 없음")
    else:
        customer_note = "고객 비중 확인 안 함(PDF 서술 추출 없음)"
    extra = {"concentration": bool(reasons and reasons[0].startswith("한 사업")), "customer_note": customer_note, "references": refs,
             "top_segment": {"name": top["name"], "share": top.get("share")} if top else None}
    if reasons:
        return _item("dependence", "고객·제품 의존도", CHECK, reasons, **extra)
    if top is None or top.get("share") is None:
        return _item("dependence", "고객·제품 의존도", UNKNOWN, ["사업부문 비중을 원문과 대조하지 못함"], **extra)
    return _item("dependence", "고객·제품 의존도", CLEAR, [f"최대 부문 {top['name']} {pct(top['share'])}", customer_note], **extra)


def risks(position: dict | None, position_status: str | None, position_message: str | None) -> dict:
    items = (position or {}).get("risks") or []
    if items:
        return _item("risks", "회사가 밝힌 위험 요인", INFO, [f"회사가 밝힌 위험 {len(items)}개"])
    return _item("risks", "회사가 밝힌 위험 요인", INFO, [position_message or "위험 요인 문장을 찾지 못함"])


def accounting(rows: dict[str, tuple[str, dict | None]]) -> dict:
    """회계 이슈 4개 항목(6-B) 종합: 하나라도 확인 필요면 확인 필요, 모두 이상 없음이면 이상 없음, 그 밖은 확인 불가."""
    checks, unknowns = [], []
    for key, name in ACCOUNTING_ITEMS:
        status, content = rows.get(key, (None, None))
        verdict = content.get("verdict") if status == "ok" and content else None
        if verdict == "check":
            checks.append(f"정정공시 {content.get('count', 0)}건" if key == "corrections" else name)
        elif verdict != "clear":
            unknowns.append(f"{name} 확인 못 함")
    if checks:
        return _item("accounting", "회계 이슈", CHECK, checks)
    if unknowns:
        return _item("accounting", "회계 이슈", UNKNOWN, unknowns)
    return _item("accounting", "회계 이슈", CLEAR, ["4개 항목 모두 이상 없음"])


def build_checklist(report: dict, rows: dict[str, tuple[str, dict | None, str | None]]) -> dict:
    """rows: 작업 키 → (상태, 내용, 메시지). 앞 작업이 실패·없음이면 그 항목만 확인 불가로 둔다."""
    def content(key):
        st, c, _m = rows.get(key, (None, None, None))
        return c if st == "ok" else None

    pos_status, pos_content, pos_msg = rows.get("extract_position", (None, None, None))
    items = [
        one_off(report),
        cashflow(report),
        debt(report, content("extract_finance")),
        dependence(content("extract_segments"), pos_content if pos_status == "ok" else None, pos_status),
        risks(pos_content if pos_status == "ok" else None, pos_status, pos_msg),
        accounting({k: rows.get(k, (None, None, None))[:2] for k, _ in ACCOUNTING_ITEMS}),
    ]
    return {"base_year": report["base_year"], "items": items, "note": NOTE, "concentration_note": CONCENTRATION_NOTE}


def checklist_text(checklist: dict) -> dict[str, tuple[str, str]]:
    """SWOT·과제 호출 근거 (근거 키 → (이름, 문단)). 위험 요인은 pdf:risks로 따로 넘긴다."""
    return {f"check:{i['key']}": (f"4장 {i['label']} (코드 판정)", i["text"]) for i in checklist["items"] if i["key"] != "risks"}
