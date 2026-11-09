"""손익계산서 '왜 이렇게 됐나' (2026-11-04, 실적 탭). AI 한 번(write).

AI에게 넘기는 자료 (모두 코드가 정리하거나 원문과 대조를 마친 것):
- income: 단계별 손익·매출 대비 %·영업이익 변화 분해 (calc/income.py)
- segments: 제품(부문)별 매출과 전년 대비 (extract_segments, 금액은 원문 대조)
- sga_note / finance_note / other_note: 판관비·금융손익·기타영업외손익 주석 내역의 당기·전기·증감 (income_notes.py, 코드)
- mda: 경영진이 설명한 실적 요약과 원문 인용 (extract_mda, 인용은 원문 대조)
AI는 단계마다 '왜'를 2~3문장으로 쓰고, 근거 자료 키를 붙인다. 자료에 없는 숫자가 든 문장은 문장 단위로 버린다.
원인을 자료에서 찾을 수 없으면 지어내지 않고 숫자로 보이는 변화만 쓴다.
"""
import httpx

from . import ai_prompts as P
from .ai_facts import Facts, won
from .ai_pdf import _sentences
from .ai_tasks import Outcome, _failed, _usage, ask
from .ai_verify import numbers_in
from .llm import LlmError

STEPS = ("revenue", "gross", "sga", "non_operating", "tax")
SOURCES = {"income": "손익계산서 단계표 (코드 계산)", "segments": "제품(부문)별 매출", "sga_note": "판매비와관리비 주석",
           "finance_note": "금융수익·금융비용 주석", "other_note": "기타영업외수익·비용 주석", "mda": "경영진이 설명한 실적"}
NOTE_KEYS = {"sga": "sga_note", "finance": "finance_note", "other": "other_note"}
TOP_ITEMS = 8  # 주석마다 증감이 큰 항목 몇 개를 넘길지


def note_lines(note: dict) -> str:
    rows = [r for r in note["rows"] if r["change"] is not None]
    totals = [r for r in rows if r["is_total"]]
    items = sorted([r for r in rows if not r["is_total"]], key=lambda r: -abs(r["change"]))[:TOP_ITEMS]
    fmt = lambda r: f"{(r['group'] + ' · ') if r['group'] and r['group'] != '합계' else ''}{r['item']}: {won(r['current'])} (전년 {won(r['prior'])}, 증감 {won(r['change'])})"  # noqa: E731
    return "\n".join(["[합계]"] + [fmt(r) for r in totals] + ["[증감이 큰 항목]"] + [fmt(r) for r in items])


def sources_for(facts: Facts, notes: dict, mda: dict | None) -> dict[str, str]:
    out = {}
    if "income" in facts.blocks:
        out["income"] = facts.blocks["income"]
    if "segments" in facts.blocks:
        out["segments"] = facts.blocks["segments"]
    for k, key in NOTE_KEYS.items():
        if notes.get(k):
            out[key] = note_lines(notes[k])
    if mda and (mda.get("summary") or mda.get("quotes")):
        out["mda"] = "\n".join([mda.get("summary") or ""] + [f"인용: {q['text']}" for q in mda.get("quotes") or []])
    return out


async def explain_income(client: httpx.AsyncClient, facts: Facts, notes: dict, mda: dict | None) -> Outcome:
    src = sources_for(facts, notes, mda)
    if "income" not in src:
        return Outcome("empty", message="손익계산서 단계 자료가 없어 원인 설명을 만들지 않았습니다")
    allowed = set(facts.allowed)
    for text in src.values():
        allowed |= numbers_in(text)
    user = P.user_message(P.EXPLAIN_INCOME, {f"{k} — {SOURCES[k]}": v for k, v in src.items()},
                          "근거 키: " + ", ".join(src))
    try:
        r = await ask(client, "explain_income", "write", user)
    except LlmError as e:
        return _failed(e)
    d, dropped, steps = r.data if isinstance(r.data, dict) else {}, [], {}
    for k in STEPS:
        item = d.get(k)
        if not isinstance(item, dict):
            continue
        text = _sentences(item.get("text"), allowed, f"원인 설명 {k}", dropped)
        basis = [b for b in item.get("basis") or [] if b in src]
        if text:
            steps[k] = {"text": text, "basis": basis}
    if not steps:
        return Outcome("failed", message="AI 설명이 비었거나 자료에 없는 숫자만 있어 쓰지 않았습니다", warnings=dropped)
    return _usage(Outcome("ok", {"steps": steps, "sources": {k: SOURCES[k] for k in src}}, warnings=dropped), r)


# ───────────────────────── 현금흐름 '왜 이렇게 됐나' (2026-11-04, 현금흐름 탭). AI 한 번(write)
CASH_STEPS = ("operating", "investing", "financing", "fcf")
CASH_SOURCES = {"cash": "현금흐름 분석표 (코드 계산)", "cash_items": "현금흐름표 세부 항목 (DART)", "income": "손익계산서 단계표 (코드 계산)",
                "investment": "회사가 밝힌 투자 현황", "mda": "경영진이 설명한 실적·재무"}
CASH_ROWS = (("cfo", "영업활동 현금흐름"), ("capex", "설비투자(유형·무형자산 취득)"), ("fcf", "잉여현금흐름(영업 − 설비투자)"),
             ("cfi", "투자활동 현금흐름"), ("shareholder_returns", "주주환원(배당+자사주)"), ("dividends", "배당금 지급"),
             ("buyback", "자기주식 취득"), ("net_borrowing", "차입금 순증감(+빌림, −갚음)"), ("cff", "재무활동 현금흐름"),
             ("tax_paid", "법인세 납부"), ("net_income", "당기순이익"), ("cash_end", "기말 현금"))


def cash_text(cash: dict, year: int) -> str:
    from .ai_facts import mult, pct
    ys = cash.get("years") or {}
    lines = []
    for yr in sorted((int(key) for key in ys)):
        m = ys.get(str(yr))
        if m:
            lines.append(f"{yr}년: " + ", ".join(f"{label} {won(m.get(k))}" for k, label in CASH_ROWS if m.get(k) is not None)
                         + f", 영업현금흐름÷순이익 {mult(m.get('cfo_to_net_income'))}, 설비투자÷매출 {pct(m.get('capex_to_revenue'))}")
    b = cash.get("bridge")
    if b:
        lines.append(f"{year}년 현금 다리 (설비투자 외 투자활동 순액은 전체 투자활동 현금흐름에서 유형·무형자산 취득을 제외한 금액): 기초 현금 {won(b['begin'])} → " + " → ".join(f"{s['label']} {won(s['amount'])}" for s in b["steps"])
                     + f" → 기말 현금 {won(b['end'])}")
    return "\n".join(lines)


def cash_items_text(det: dict | None, top: int = 6) -> str:
    items = [i for i in (det or {}).get("items") or []
             if not i["total"] and i["current"] is not None and i["prior"] is not None]
    sec = {"operating": "영업활동", "investing": "투자활동", "financing": "재무활동"}
    lines = []
    for section, label in sec.items():
        section_items = [i for i in items if i["section"] == section]
        section_items.sort(key=lambda i: -abs(i["current"] - i["prior"]))
        lines.extend(
            f"{label} · {i['name']}: {won(i['current'])} (전년 {won(i['prior'])}, 증감 {won(i['current'] - i['prior'])})"
            for i in section_items[:top]
        )
    return "\n".join(lines)


async def explain_cashflow(client: httpx.AsyncClient, report: dict, facts: Facts, focus: dict | None, mda: dict | None) -> Outcome:
    cash = (report.get("results") or {}).get("cash")
    if not cash or not (cash.get("years") or {}).get(str(report["base_year"])):
        return Outcome("empty", message="현금흐름 분석 자료가 없어 원인 설명을 만들지 않았습니다")
    src = {"cash": cash_text(cash, report["base_year"])}
    items = cash_items_text(cash.get("detail"))
    if items:
        src["cash_items"] = items
    if "income" in facts.blocks:
        src["income"] = facts.blocks["income"]
    inv = (focus or {}).get("investment") if focus else None
    if inv and (inv.get("summary") or inv.get("quotes")):
        src["investment"] = "\n".join([inv.get("summary") or ""] + [f"인용: {q['text']}" for q in inv.get("quotes") or []])
    if mda and (mda.get("summary") or mda.get("quotes")):
        src["mda"] = "\n".join([mda.get("summary") or ""] + [f"인용: {q['text']}" for q in mda.get("quotes") or []])
    allowed = set(facts.allowed)
    for text in src.values():
        allowed |= numbers_in(text)
    user = P.user_message(P.EXPLAIN_CASHFLOW, {f"{k} — {CASH_SOURCES[k]}": v for k, v in src.items()}, "근거 키: " + ", ".join(src))
    try:
        r = await ask(client, "explain_cashflow", "write", user)
    except LlmError as e:
        return _failed(e)
    d, dropped, steps = r.data if isinstance(r.data, dict) else {}, [], {}
    for k in CASH_STEPS:
        item = d.get(k)
        if not isinstance(item, dict):
            continue
        text = _sentences(item.get("text"), allowed, f"현금 설명 {k}", dropped)
        if text:
            steps[k] = {"text": text, "basis": [b for b in item.get("basis") or [] if b in src]}
    if not steps:
        return Outcome("failed", message="AI 설명이 비었거나 자료에 없는 숫자만 있어 쓰지 않았습니다", warnings=dropped)
    return _usage(Outcome("ok", {"steps": steps, "sources": {k: CASH_SOURCES[k] for k in src}}, warnings=dropped), r)
