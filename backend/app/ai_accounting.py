"""회계 이슈 체크의 AI 작업 세 개 (Phase 6-B): 계속기업 불확실성·특수관계자 거래 추출, 한 줄 요약과 주석 해석.

6-A와 같은 원칙: AI는 원문 인용(quote)과 값을 돌려주고, 인용이 원문에 있는지·값이 인용 안에 있는지·단위가 맞는지·표의 칸 위치가 맞는지는
코드가 확인한다. 확인하지 못한 값은 저장하지 않고 '확인 불가'로 둔다. 비중·합계 판정은 코드가 계산한다.
"""
import re

import httpx

from . import ai_prompts as P
from .ai_facts import pct, won
from .ai_tasks import Outcome, _clean_text, _failed, _usage, ask
from .ai_verify import _squash, numbers_in, parse_amount, quote_in_source, unit_in_quote, value_in_quote
from .dart_docs import find_section, financial_notes, note_text
from .llm import LlmError

RELATED_PARTY_THRESHOLD = 0.30  # 이 도구의 참고 기준 (법적 기준 아님). 매출 또는 매입 합계 ÷ 연결 매출액
VERDICT_TEXT = {"clear": "이상 없음", "check": "확인 필요", "unknown": "확인 불가"}
MAX_TOP, MAX_ITEMS = 3, 5


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.split("|")]


# ───────────────────────── 계속기업 불확실성
def audit_table_source(xml: str) -> str | None:
    sec = find_section(xml, "외부감사에관한사항")
    return sec.split("\n나. 감사용역")[0][:2500] if sec else None


def going_concern_sources(xml: str) -> dict[str, str]:
    table = audit_table_source(xml)
    if not table:
        return {}
    out = {"회계감사인의 감사의견 등 > 외부감사에 관한 사항": table}
    lines = [ln[:400] for ln in (financial_notes(xml) or "").splitlines() if "계속기업" in ln and ("불확실" in ln or "의문" in ln)]
    if lines:
        out["재무제표 주석 중 계속기업 관련 문장"] = "\n".join(lines[:5])
    return out


async def extract_going_concern(client: httpx.AsyncClient, xml: str, audit: dict | None) -> Outcome:
    emphasis = [t for t in (audit or {}).get("emphasis", []) if "계속기업" in t]
    if emphasis:  # 감사보고서 강조사항에 계속기업이 올라 있으면 AI 없이 바로 확인 필요
        return Outcome("ok", {"verdict": "check", "basis": "emphasis", "quote": emphasis[0]})
    sources = going_concern_sources(xml)
    if not sources:
        return Outcome("empty", message="사업보고서에서 회계감사인의 감사의견 표를 찾지 못했습니다")
    joined = "\n".join(sources.values())
    try:
        r = await ask(client, "extract_going_concern", "extract", P.user_message(P.EXTRACT_GOING_CONCERN, sources))
    except LlmError as e:
        return audit_fallback(audit) or _failed(e)
    d = r.data
    flag, quote = d.get("has_material_uncertainty"), d.get("quote")
    if not isinstance(flag, bool):
        return audit_fallback(audit) or Outcome("empty", message="계속기업 불확실성을 자료만으로 판단하지 못했습니다")
    if not quote_in_source(quote, joined):
        return audit_fallback(audit) or Outcome("empty", message="계속기업 불확실성 판단의 근거 문장을 원문과 대조하지 못해 사용하지 않았습니다")
    return _usage(Outcome("ok", {"verdict": "check" if flag else "clear", "basis": "ai", "quote": quote}), r)


def audit_fallback(audit: dict | None) -> Outcome | None:
    """AI 근거를 원문과 맞추지 못했을 때(2026-11-04 실제 리포트 17·20에서 두 번 '확인 불가'): 감사의견이 모두 '적정의견'이고
    강조사항에 계속기업 언급이 없으면 코드가 '이상 없음'으로 판정한다. 그 밖에는 None(확인 불가 유지)."""
    if not audit or audit.get("verdict") != "clear" or any("계속기업" in t for t in audit.get("emphasis", [])):
        return None
    return Outcome("ok", {"verdict": "clear", "basis": "audit", "quote": None, "opinion": audit.get("opinion")})


# ───────────────────────── 특수관계자 거래
def related_party_source(xml: str) -> str | None:
    text = note_text(financial_notes(xml) or "", "특수관계자")
    return text[:15000] if text else None


def is_current_period(quote: str, source: str) -> bool:
    """인용이 전기 표가 아니라 당기 표에 있는지(원문에서 '전기 (단위' 머리말보다 앞인지). 머리말이 없으면 판단하지 않고 통과."""
    s, q = _squash(source), _squash(quote)
    prior = s.find("전기(단위")
    at = s.find(q)
    return prior == -1 or (at != -1 and at < prior)


def verified_total(item: dict | None, word: str, unit: str | None, source: str) -> int | None:
    """합계 행: 인용이 원문 당기 표에 있고, 행 이름에 word(매출·매입)가 있고, 값이 행의 맨 오른쪽 값 칸일 때만 원 단위 금액."""
    if not isinstance(item, dict):
        return None
    quote, value = item.get("quote"), (item.get("value") or "").strip()
    if not quote_in_source(quote, source) or not value_in_quote(value, quote) or not is_current_period(quote, source):
        return None
    cells = _cells(quote)
    filled = [c for c in cells[1:] if c]
    if word not in cells[0] or not filled or filled[-1] != value:
        return None
    return parse_amount(value, unit)


def aligned_to_party(party: str, value: str, quote: str, source: str) -> bool:
    """회사별 거래 값이 정말 그 회사 칸의 값인지: 행이 그 회사 한 곳의 것이거나, 표 머리글 줄에서 회사명의 칸 위치와 값의 칸 위치가 같을 때."""
    row = _cells(quote)
    if value not in row[1:]:
        return False
    if row[0] == party:
        return True
    for line in source.splitlines():
        head = _cells(line)
        if party in head and (i := head.index(party)) + 1 < len(row) and row[i + 1] == value:
            return True
    return False


def verified_top(items, unit: str | None, source: str) -> list[dict]:
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        party, kind, value, quote = (it.get(k) for k in ("party", "kind", "value", "quote"))
        if not (party and kind and value and quote_in_source(quote, source) and value_in_quote(value, quote) and is_current_period(quote, source)):
            continue
        if _squash(kind) != _squash(_cells(quote)[0]) or not aligned_to_party(party.strip(), value.strip(), quote, source):
            continue
        amount = parse_amount(value, unit)
        if amount and amount > 0:
            out.append({"party": party.strip(), "kind": kind.strip(), "amount_won": amount})
    out.sort(key=lambda x: -x["amount_won"])
    return out[:MAX_TOP]


def verified_text_amounts(items, source: str) -> dict:
    """대여금·지급보증: 금액은 원문에 적힌 표기 그대로(통화 환산 없음). 인용이 원문에 있고 금액 표기가 인용 안에 있어야 한다.

    state: none(AI가 없다고 함) | found | unverified(AI가 찾았지만 원문과 대조하지 못함)
    """
    asked = [it for it in items or [] if isinstance(it, dict)]
    if not asked:
        return {"state": "none", "items": []}
    out = []
    for it in asked:
        amount, quote, party = (it.get(k) for k in ("amount_text", "quote", "party"))
        if not amount or not quote_in_source(quote, source) or not value_in_quote(amount.strip(), quote):
            continue
        digits = re.sub(r"\D", "", amount)
        if digits and not digits.strip("0"):
            continue  # 0원은 '없음'과 같다
        out.append({"party": party.strip() if party and _squash(party) in _squash(source) else None, "amount_text": amount.strip()})
    return {"state": "found" if out else "unverified", "items": out[:MAX_ITEMS]}


def judge_related_party(sales_ratio: float | None, purchases_ratio: float | None) -> str:
    ratios = [r for r in (sales_ratio, purchases_ratio) if r is not None]
    if any(r >= RELATED_PARTY_THRESHOLD for r in ratios):
        return "check"
    return "clear" if len(ratios) == 2 else "unknown"


async def extract_related_party(client: httpx.AsyncClient, xml: str, revenue_won: int | None) -> Outcome:
    src = related_party_source(xml)
    if not src:
        return Outcome("empty", message="주석에서 특수관계자 거래 항목을 찾지 못했습니다")
    try:
        r = await ask(client, "extract_related_party", "extract", P.user_message(P.EXTRACT_RELATED_PARTY, {"재무제표 주석 > 특수관계자": src}))
    except LlmError as e:
        return _failed(e)
    d = r.data
    ok_unit = unit_in_quote(d.get("unit"), d.get("unit_quote")) and quote_in_source(d.get("unit_quote"), src)
    unit = d.get("unit") if ok_unit else None
    sales = verified_total(d.get("sales_total"), "매출", unit, src)
    purchases = verified_total(d.get("purchases_total"), "매입", unit, src)
    ratio = lambda v: v / revenue_won if v is not None and revenue_won and revenue_won > 0 else None  # noqa: E731
    sales_ratio, purchases_ratio = ratio(sales), ratio(purchases)
    content = {"verdict": judge_related_party(sales_ratio, purchases_ratio), "threshold": RELATED_PARTY_THRESHOLD, "revenue_won": revenue_won,
               "sales_total_won": sales, "sales_ratio": sales_ratio, "purchases_total_won": purchases, "purchases_ratio": purchases_ratio,
               "top": verified_top(d.get("top_transactions"), unit, src) if ok_unit else [],
               "loans": verified_text_amounts(d.get("loans"), src), "guarantees": verified_text_amounts(d.get("guarantees"), src)}
    return _usage(Outcome("ok", content), r)


# ───────────────────────── 해석: 한 줄 요약 + 주석 ⓘ 4개
def accounting_facts(results: dict[str, dict | None]) -> tuple[str, set[str]]:
    """AI에게 넘길 자료 문단(코드가 정한 판정과 숫자)과 그 안의 숫자 토큰. results: 항목 키 → 저장된 내용(없으면 None=확인 불가)."""
    lines = []
    a = results.get("audit_opinion")
    lines.append("감사의견: " + (f"{VERDICT_TEXT[a['verdict']]} — {a['opinion']} (감사인 {a['auditor'] or '자료 없음'}), 핵심감사사항 {len(a['key_audit_matters'])}건, "
                                 f"강조사항 {'있음' if a['emphasis'] else '없음'}" if a else "확인 불가"))
    g = results.get("extract_going_concern")
    lines.append("계속기업 불확실성: " + (VERDICT_TEXT[g["verdict"]] + (" (감사보고서 강조사항에 계속기업 언급)" if g["basis"] == "emphasis" else "") if g else "확인 불가"))
    c = results.get("corrections")
    lines.append("정정공시: " + (f"{VERDICT_TEXT[c['verdict']]} — {c['period_start']}~{c['period_end']} 정기공시 정정 {c['count']}건" if c else "확인 불가"))
    p = results.get("extract_related_party")
    if p:
        parts = [VERDICT_TEXT[p["verdict"]]]
        if p["sales_total_won"] is not None:
            parts.append(f"특수관계자 매출 등 {won(p['sales_total_won'])}(연결 매출액의 {pct(p['sales_ratio'])})")
        if p["purchases_total_won"] is not None:
            parts.append(f"매입 등 {won(p['purchases_total_won'])}(매출액의 {pct(p['purchases_ratio'])})")
        parts.append(f"참고 기준 {round(p['threshold'] * 100)}%")
        parts.append("대여금 " + {"none": "해당 없음", "found": "있음", "unverified": "확인 불가"}[p["loans"]["state"]])
        parts.append("지급보증 " + {"none": "해당 없음", "found": "있음", "unverified": "확인 불가"}[p["guarantees"]["state"]])
        lines.append("특수관계자 거래: " + ", ".join(parts))
    else:
        lines.append("특수관계자 거래: 확인 불가")
    text = "\n".join(lines)
    return text, numbers_in(text)


async def write_accounting(client: httpx.AsyncClient, text: str, allowed: set[str]) -> Outcome:
    request = "notes 키: " + ", ".join(f"{k}({t})" for k, t in P.ACCOUNTING_NOTE_KEYS)
    try:
        r = await ask(client, "write_accounting", "write", P.user_message(P.WRITE_ACCOUNTING, {"회계 이슈 체크 결과 (코드가 판정)": text}, request))
    except LlmError as e:
        return _failed(e)
    d, dropped = r.data, []
    summary = _clean_text(d.get("summary"), allowed, "회계 이슈 요약", dropped)
    notes = {}
    for k, _ in P.ACCOUNTING_NOTE_KEYS:
        n = (d.get("notes") or {}).get(k)
        if not isinstance(n, dict):
            continue
        meaning = _clean_text(n.get("meaning"), allowed, f"주석 {k} 의미", dropped)
        why = _clean_text(n.get("why"), allowed, f"주석 {k} 중요성", dropped)
        if meaning or why:
            notes[k] = {"meaning": meaning, "why": why}
    if not summary and not notes:
        return Outcome("failed", message="AI 문장이 자료에 없는 숫자를 포함하거나 비어 있어 사용하지 않았습니다: " + "; ".join(dropped), warnings=dropped)
    return _usage(Outcome("ok", {"summary": summary, "notes": notes}, warnings=dropped), r)
