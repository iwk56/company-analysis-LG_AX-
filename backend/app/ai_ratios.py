"""비율 지표 해석 (2026-11-05). AI 한 번(write) — 실적 탭(수익성·성장성)과 재무상태 탭(안정성·활동성)에 따로 호출한다.

AI에게 넘기는 자료 (모두 코드 계산, 화면과 같은 표시 규칙 — ai_facts.py):
- ratios: 그 묶음에 속한 비율들의 전체 연도 흐름 (ratio_group_text)
- dupont: ROE 분해와 주된 변화 요인 (수익성 묶음을 해석할 때만 함께 준다)
AI는 묶음(수익성·성장성·안정성·활동성)마다 비율들이 같은 방향으로 움직이는지, 엇갈리면 숫자 관계로 무엇을 짚을 수 있는지를
2~4문장으로 쓴다. 비즈니스상 외부 원인은 쓰지 않는다(그건 실적·현금흐름의 "왜 이렇게 됐나"가 담당). 자료에 없는 숫자가 든
문장은 문장 단위로 버린다.
"""
import httpx

from . import ai_prompts as P
from .balance_notes import balance_note_text
from .ai_facts import Facts, balance_change_text, ratio_driver_text, ratio_group_text
from .ai_pdf import _sentences
from .ai_tasks import Outcome, _failed, _usage, ask
from .ai_verify import numbers_in
from .llm import LlmError

GROUP_KEYS: dict[str, list[str]] = {
    "수익성": ["operating_margin", "net_margin", "roe", "roa"],
    "성장성": ["revenue_growth", "operating_income_growth", "asset_growth"],
    "안정성": ["debt_ratio", "current_ratio", "interest_coverage"],
    "활동성": ["asset_turnover", "receivable_turnover", "inventory_turnover"],
}
SOURCES = {"ratios": "재무비율 5년 흐름 (코드 계산)", "drivers": "재무제표 항목과 전년 대비 증감 (코드 계산)",
           "balance": "DART 재무상태표 세부 계정·현금흐름표 거래 (코드 정리)",
           "balance_notes": "DART 사업보고서 재무제표 주석 (공시 원문)",
           "dupont": "듀퐁 분석 — ROE 분해 (코드 계산)"}

# 성장성은 코드 계산 표·차트로 보여주고 AI 해설은 만들지 않는다.
PROFIT_GROUPS = ("수익성",)
STABILITY_GROUPS = ("안정성", "활동성")


async def explain_ratios(client: httpx.AsyncClient, task: str, report: dict, facts: Facts,
                         groups: tuple[str, ...], annual_xml: str | None = None) -> Outcome:
    keys = [k for g in groups for k in GROUP_KEYS[g]]
    src = {"ratios": ratio_group_text(report, keys), "drivers": ratio_driver_text(report, keys)}
    if "안정성" in groups:
        src["balance"] = balance_change_text(report)
        notes = balance_note_text(annual_xml, report)
        if notes:
            src["balance_notes"] = notes
    if "수익성" in groups and facts.blocks.get("dupont"):
        src["dupont"] = facts.blocks["dupont"]
    allowed = set(facts.allowed)
    for text in src.values():
        allowed |= numbers_in(text)
    user = P.user_message(P.EXPLAIN_RATIOS, {f"{k} — {SOURCES[k]}": v for k, v in src.items()},
                          "근거 키: " + ", ".join(src) + " / 묶음: " + ", ".join(groups))
    try:
        r = await ask(client, task, "write", user)
    except LlmError as e:
        return _failed(e)
    d, dropped, out = r.data if isinstance(r.data, dict) else {}, [], {}
    for g in groups:
        item = d.get(g)
        if not isinstance(item, dict):
            continue
        text = _sentences(item.get("text"), allowed, f"비율 해석 {g}", dropped)
        if text:
            out[g] = {"text": text, "basis": [b for b in item.get("basis") or [] if b in src]}
    if not out:
        return Outcome("failed", message="AI 해석이 비었거나 자료에 없는 숫자만 있어 쓰지 않았습니다", warnings=dropped)
    return _usage(Outcome("ok", {"groups": out, "sources": {k: SOURCES[k] for k in src}}, warnings=dropped), r)
