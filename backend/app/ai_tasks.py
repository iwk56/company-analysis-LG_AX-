"""AI 작업 다섯 개의 입력 만들기·호출·검증. 추출 3개(사업부문·비중, 연구개발비, 금융비용 주석)와 해석 2개(개요·BCG, 요약·주석).

숫자는 코드가 정한다: AI가 인용한 원문 문장과 값을 코드가 원문과 대조하고, 단위 환산·비중·증감률·이자보상배율은 코드가 계산한다.
검증을 통과하지 못한 값은 버린다(잘못된 값을 저장하지 않음).
"""
from dataclasses import dataclass, field

import httpx

from . import ai_prompts as P
from .ai_facts import Facts
from .ai_verify import numbers_in, quote_in_source, unit_in_quote, unknown_numbers, verified_amount
from .dart_docs import find_section, financial_notes, note_text
from .llm import LlmError, LlmResult, call_json

FINANCE_NOTE_KEYWORDS = ("금융수익 및 금융비용", "금융수익과 금융비용", "금융수익 및 금융원가", "금융수익과 금융원가", "금융손익")
SEGMENT_NOTE_KEYWORDS = (("영업부문", "부문정보", "보고부문"), ("매출액", "수익"))


@dataclass
class Outcome:
    status: str  # ok | empty(원문에 자료 없음) | failed
    content: dict | None = None
    message: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    warnings: list[str] = field(default_factory=list)


def _usage(o: Outcome, r: LlmResult) -> Outcome:
    o.model, o.input_tokens, o.output_tokens = r.model, r.input_tokens, r.output_tokens
    return o


async def ask(client: httpx.AsyncClient, task: str, kind: str, user: str) -> LlmResult:
    """AI 호출. 응답 형식이 틀리면(retryable) 한 번만 다시 보낸다."""
    try:
        return await call_json(client, task, kind, P.RULES, user)
    except LlmError as e:
        if not e.retryable:
            raise
        first = e
    r = await call_json(client, task, kind, P.RULES, user)  # 두 번째도 실패하면 그 오류가 올라간다
    return LlmResult(r.data, r.model, r.input_tokens + first.input_tokens, r.output_tokens + first.output_tokens)


def _failed(e: LlmError) -> Outcome:
    return Outcome("failed", message=e.message)


def _cap(text: str | None, n: int) -> str:
    return (text or "")[:n]


# ───────────────────────── 추출 1: 사업부문(품목)·해외 비중
def segment_sources(xml: str) -> dict[str, str]:
    notes = financial_notes(xml) or ""
    out = {}
    sales = find_section(xml, "매출및수주상황")
    if sales:
        out["사업의 내용 > 매출 및 수주상황"] = _cap(sales, 2500)
    for i, kws in enumerate(SEGMENT_NOTE_KEYWORDS):
        text = next((t for kw in kws if (t := note_text(notes, kw))), None)
        if text:
            out[f"재무제표 주석 > {text.splitlines()[0]}"] = _cap(text, 5000)
    return out


async def extract_segments(client: httpx.AsyncClient, xml: str, revenue_won: int | None, base_year: int) -> Outcome:
    sources = segment_sources(xml)
    if not sources:
        return Outcome("empty", message="사업보고서에서 매출 구분 자료를 찾지 못했습니다")
    joined = "\n".join(sources.values())
    try:
        r = await ask(client, "extract_segments", "extract", P.user_message(P.EXTRACT_SEGMENTS, sources))
    except LlmError as e:
        return _failed(e)
    d, o = r.data, Outcome("ok")
    unit = d.get("unit")
    ok_unit = unit_in_quote(unit, d.get("unit_quote")) and quote_in_source(d.get("unit_quote"), joined)
    products = []
    for p in d.get("products") or []:
        cur = verified_amount(p.get("current"), unit, d.get("products_quote_current"), joined) if ok_unit else None
        if cur is None or not p.get("name") or p["name"].replace(" ", "") not in (d.get("products_quote_current") or "").replace(" ", ""):
            continue
        prior = verified_amount(p.get("prior"), unit, d.get("products_quote_prior"), joined) if ok_unit else None
        products.append({"name": p["name"], "current_won": cur, "prior_won": prior})
    content = {"year": base_year, "products": [], "overseas_share": None, "source_unit": unit,
               "quotes": {"products": d.get("products_quote_current"), "region": (d.get("region") or {}).get("quote")}}
    if products:
        total = sum(p["current_won"] for p in products)
        for p in products:
            p["share"] = p["current_won"] / total if total > 0 else None
            p["growth"] = (p["current_won"] / p["prior_won"] - 1) if p["prior_won"] and p["prior_won"] > 0 else None
        content["products"] = products
        if revenue_won and abs(total - revenue_won) / revenue_won > 0.01:
            o.warnings.append("나열된 항목의 합계가 연결 매출액과 1% 넘게 달라 비중은 나열된 항목의 합계 기준입니다")
    reg = d.get("region") or {}
    dom = verified_amount(reg.get("domestic"), unit, reg.get("quote"), joined) if ok_unit else None
    tot = verified_amount(reg.get("total"), unit, reg.get("quote"), joined) if ok_unit else None
    if dom is not None and tot and 0 <= dom <= tot:
        content["overseas_share"] = (tot - dom) / tot
    if not content["products"] and content["overseas_share"] is None:
        return Outcome("empty", message="사업부문·지역별 매출을 원문과 대조하지 못해 사용하지 않았습니다 (원문에 없거나 AI가 옮긴 값이 원문과 달랐습니다)")
    return _usage(Outcome("ok", content, warnings=o.warnings), r)


# ───────────────────────── 추출 2: 연구개발비
def rnd_source(xml: str) -> str | None:
    sec = find_section(xml, "연구개발")
    if not sec or "연구개발비용" not in sec:
        return None
    i = sec.find("연구개발비용")
    return sec[max(0, i - 300): i + 2500]


async def extract_rnd(client: httpx.AsyncClient, xml: str, revenue_won: int | None) -> Outcome:
    src = rnd_source(xml)
    if not src:
        return Outcome("empty", message="사업보고서에서 연구개발비 항목을 찾지 못했습니다")
    try:
        r = await ask(client, "extract_rnd", "extract", P.user_message(P.EXTRACT_RND, {"사업의 내용 > 연구개발활동": src}))
    except LlmError as e:
        return _failed(e)
    d = r.data
    amount = None
    if unit_in_quote(d.get("unit"), d.get("unit_quote")) and quote_in_source(d.get("unit_quote"), src):
        amount = verified_amount(d.get("amount"), d.get("unit"), d.get("quote"), src)
    if amount is None:
        return Outcome("empty", message="연구개발비를 원문과 대조하지 못해 사용하지 않았습니다 (원문에 없거나 AI가 옮긴 값이 원문과 달랐습니다)")
    ratio = amount / revenue_won if revenue_won and revenue_won > 0 else None
    return _usage(Outcome("ok", {"amount_won": amount, "ratio_to_revenue": ratio, "quote": d.get("quote")}), r)


# ───────────────────────── 추출 3: 금융비용 주석 (실제 이자비용, 순이익 > 영업이익 원인)
def finance_note(xml: str) -> str | None:
    notes = financial_notes(xml) or ""
    return next((t for kw in FINANCE_NOTE_KEYWORDS if (t := note_text(notes, kw))), None)


def net_vs_operating_period(report: dict) -> dict | None:
    """순이익(지배주주)이 영업이익보다 큰 기간. 최근 반기·3분기 누적을 먼저 보고, 없으면 기준 사업연도. 해당 없으면 None."""
    rr = report.get("recent_results")
    if rr:
        net, op = rr["current"].get("net_income_parent"), rr["current"].get("operating_income")
        if net is not None and op is not None and net > op:
            return {"kind": "interim", "label": f"{rr['period_current']} 누적 ({rr['report_name']}보고서)", "rcept_no": rr["rcept_no"],
                    "net_income_parent": net, "operating_income": op}
    fy = next((f for f in report["financial_years"] if f["year"] == report["base_year"]), None)
    if fy and fy.get("net_income_parent") is not None and fy.get("operating_income") is not None \
            and fy["net_income_parent"] > fy["operating_income"]:
        src = next((s for s in report["sources"] if s["kind"] == "annual_report" and s["year"] == report["base_year"]), None)
        return {"kind": "annual", "label": f"{report['base_year']}년", "rcept_no": src["rcept_no"] if src else None,
                "net_income_parent": fy["net_income_parent"], "operating_income": fy["operating_income"]}
    return None


async def extract_finance(client: httpx.AsyncClient, annual_xml: str, interim_xml: str | None, report: dict,
                          period: dict | None) -> Outcome:
    annual = finance_note(annual_xml)
    sources = {"연간 주석": _cap(annual, 4000)} if annual else {}
    want_items = period is not None
    items_xml_text = annual if period and period["kind"] == "annual" else (finance_note(interim_xml) if interim_xml else None)
    if want_items and period["kind"] == "interim":
        if items_xml_text:
            sources["반기·분기 주석 (누적 열을 사용)"] = _cap(items_xml_text, 4000)
        else:
            want_items = False
    if not sources:
        return Outcome("empty", message="사업보고서에서 금융수익·금융비용 주석을 찾지 못했습니다")
    request = "finance_income_items를 채워 주세요 (아래 자료의 누적 금융수익 항목)." if want_items else "finance_income_items는 빈 목록으로 두세요."
    try:
        r = await ask(client, "extract_finance", "extract", P.user_message(P.EXTRACT_FINANCE, sources, request))
    except LlmError as e:
        return _failed(e)
    d = r.data
    base_fy = next((f for f in report["financial_years"] if f["year"] == report["base_year"]), {})

    def amount(item: dict | None, source_text: str | None) -> int | None:
        if not item or not source_text or not unit_in_quote(item.get("unit"), item.get("unit_quote")) \
                or not quote_in_source(item.get("unit_quote"), source_text):
            return None
        return verified_amount(item.get("value"), item.get("unit"), item.get("quote"), source_text)

    interest = amount(d.get("interest_expense"), annual)
    content: dict = {"interest_expense_won": interest, "interest_quote": (d.get("interest_expense") or {}).get("quote") if interest is not None else None,
                     "coverage_actual": None, "net_vs_operating": None}
    op = base_fy.get("operating_income")
    if interest and interest > 0 and op is not None:
        content["coverage_actual"] = op / interest
    if period is not None:
        items = []
        for it in d.get("finance_income_items") or []:
            a = amount(it, items_xml_text)
            if a is not None and it.get("label") and a > 0:
                items.append({"label": it["label"], "amount_won": a, "quote": it.get("quote")})
        items.sort(key=lambda x: -x["amount_won"])
        content["net_vs_operating"] = {"period_label": period["label"], "kind": period["kind"], "rcept_no": period["rcept_no"],
                                       "net_income_parent": period["net_income_parent"], "operating_income": period["operating_income"],
                                       "items": items[:5]}
    if interest is None and not (content["net_vs_operating"] or {}).get("items"):
        return Outcome("empty", message="주석의 이자비용·금융수익 항목을 원문과 대조하지 못해 사용하지 않았습니다 (원문에 없거나 AI가 옮긴 값이 원문과 달랐습니다)")
    return _usage(Outcome("ok", content), r)


# ───────────────────────── 해석 1: 기업 개요 + BCG
def _clean_text(value, allowed: set[str], where: str, dropped: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    bad = unknown_numbers(value, allowed)
    if bad:
        dropped.append(f"{where}: 자료에 없는 숫자 {', '.join(sorted(bad))}")
        return None
    return value.strip()


async def write_overview(client: httpx.AsyncClient, facts: Facts, pdf: tuple[str | None, list[dict]] | None = None) -> Outcome:
    """pdf: 올린 사업보고서의 II-1 사업의 개요·II-2 주요 제품 및 서비스에서 고른 글과 사용 범위 (8-D, 1장 주력 사업). 없으면 코드 자료만."""
    sources = {"기업 정보": facts.blocks["overview"]}
    if "segments" in facts.blocks:
        sources["사업부문별 매출 (코드가 계산한 비중·증감률)"] = facts.blocks["segments"]
    pdf_text, pdf_inputs = pdf or (None, [])
    allowed = set(facts.allowed)
    if pdf_text:
        sources["사업보고서 · 사업의 개요·주요 제품 및 서비스"] = pdf_text
        allowed |= numbers_in(pdf_text)
    try:
        r = await ask(client, "write_overview", "write", P.user_message(P.WRITE_OVERVIEW, sources))
    except LlmError as e:
        return _failed(e)
    d, dropped = r.data, []
    overview = _clean_text(d.get("overview"), allowed, "기업 개요", dropped)
    bcg = None  # BCG 해석은 2026-11-04 삭제(점유율 없이 비중만 봐서 얕음). 저장 형식은 그대로 둔다
    if overview is None and bcg is None:
        return Outcome("failed", message="AI 문장이 자료에 없는 숫자를 포함하거나 비어 있어 사용하지 않았습니다: " + "; ".join(dropped), warnings=dropped)
    return _usage(Outcome("ok", {"overview": overview, "bcg": bcg, "inputs": pdf_inputs}, warnings=dropped), r)


# ───────────────────────── 해석 2: 한 줄 요약 + 주석 ⓘ
async def write_summaries(client: httpx.AsyncClient, facts: Facts, with_net_note: bool) -> Outcome:
    summary_keys = [(k, t) for k, t in P.SUMMARY_KEYS if k in facts.blocks]
    note_keys = list(P.NOTE_KEYS) + ([P.NET_VS_OPERATING_NOTE] if with_net_note else [])
    sources = {t: facts.blocks[k] for k, t in summary_keys}
    if "extra" in facts.blocks:
        sources["주석에서 추출한 값"] = facts.blocks["extra"]
    request = ("summaries 키: " + ", ".join(f"{k}({t})" for k, t in summary_keys) + "\nnotes 키: " + ", ".join(f"{k}({t})" for k, t in note_keys))
    try:
        r = await ask(client, "write_summaries", "write", P.user_message(P.WRITE_SUMMARIES, sources, request))
    except LlmError as e:
        return _failed(e)
    d, dropped = r.data, []
    summaries = {}
    for k, _ in summary_keys:
        text = _clean_text((d.get("summaries") or {}).get(k), facts.allowed, f"요약 {k}", dropped)
        if text:
            summaries[k] = text
    notes = {}
    for k, _ in note_keys:
        n = (d.get("notes") or {}).get(k)
        if not isinstance(n, dict):
            continue
        meaning = _clean_text(n.get("meaning"), facts.allowed, f"주석 {k} 의미", dropped)
        why = _clean_text(n.get("why"), facts.allowed, f"주석 {k} 중요성", dropped)
        if meaning or why:
            notes[k] = {"meaning": meaning, "why": why}
    if not summaries and not notes:
        return Outcome("failed", message="AI 문장이 자료에 없는 숫자를 포함하거나 비어 있어 사용하지 않았습니다: " + "; ".join(dropped), warnings=dropped)
    return _usage(Outcome("ok", {"summaries": summaries, "notes": notes}, warnings=dropped), r)
