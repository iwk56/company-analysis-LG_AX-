"""경쟁사와 비교한 해석 (2026-11-04, 산업·경쟁 탭): 잘하는 점·유리한 점·약점·기회.

비교표 숫자는 comparison.py가 코드로 계산한 것이고, AI는 그 숫자를 보고 해석만 한다.
문장 속 숫자가 비교표에 없으면 그 항목을 버리고, 근거 지표 키가 비교표에 없어도 버린다.
"""
import httpx

from . import ai_prompts as P
from .ai_tasks import Outcome, _failed, _usage, ask
from .ai_verify import numbers_in, unknown_numbers
from .llm import LlmError

GROUPS = (("strengths", "잘하는 점"), ("advantages", "유리한 점"), ("weaknesses", "약점"), ("opportunities", "기회"))
MAX_ITEMS = 3


def _fmt(value: float | None, fmt: str) -> str | None:
    if value is None:
        return None
    if fmt == "amount":
        return f"{value / 1e12:,.1f}조 원" if abs(value) >= 1e12 else f"{value / 1e8:,.0f}억 원"
    if fmt == "percent":
        return f"{value * 100:.1f}%"
    if fmt == "change":
        return f"{value * 100:+.1f}%"
    if fmt == "multiple":
        return f"{value:.1f}배"
    return str(value)


def comparison_text(comparison: dict) -> tuple[str, set[str], set[str]]:
    """(비교표 글, 허용 숫자, 지표 키). 기업마다 한 줄, 끝에 평균."""
    cols = comparison["columns"]
    keys = {c["key"] for c in cols}
    lines = [f"[지표 키] " + ", ".join(f"{c['key']}={c['label']}" + (" (낮을수록 좋음)" if c["higher_is_better"] is False else "") for c in cols)]
    for row in comparison["rows"]:
        parts = []
        for c in cols:
            v = row["values"][c["key"]]
            text = _fmt(v["value"], c["format"]) or (v.get("na_reason") or "자료 없음")
            rank = f" ({v['rank']}위)" if v.get("rank") else ""
            parts.append(f"{c['label']} {text}{rank}")
        who = "분석 기업" if row["is_target"] else "경쟁사"
        lines.append(f"- {row['corp_name']} [{who}, {row['basis']}]: " + ", ".join(parts))
    avg = [f"{c['label']} {_fmt(comparison['averages'].get(c['key']), c['format'])}" for c in cols
           if comparison["averages"].get(c["key"]) is not None]
    lines.append("- 평균(분석 기업 포함): " + ", ".join(avg))
    text = f"{comparison['base_year']} 사업연도 기준\n" + "\n".join(lines)
    return text, numbers_in(text), keys


async def write_peers(client: httpx.AsyncClient, report: dict) -> Outcome:
    comparison = (report.get("results") or {}).get("comparison")
    if not comparison or sum(1 for r in comparison["rows"] if not r["is_target"]) == 0:
        return Outcome("empty", message="비교할 경쟁사가 없습니다")
    text, allowed, keys = comparison_text(comparison)
    try:
        r = await ask(client, "write_peers", "write", P.user_message(P.WRITE_PEERS, {"비교표": text}))
    except LlmError as e:
        return _failed(e)
    d, dropped = r.data if isinstance(r.data, dict) else {}, []
    out: dict = {}
    for key, name in GROUPS:
        kept = []
        for i, it in enumerate(d.get(key) or []):
            if not isinstance(it, dict) or not isinstance(it.get("text"), str) or len(kept) >= MAX_ITEMS:
                continue
            bad = unknown_numbers(it["text"], allowed)
            basis = [b for b in it.get("basis") or [] if b in keys]
            if bad:
                dropped.append(f"{name} {i + 1}: 비교표에 없는 숫자 {', '.join(sorted(bad))}")
            elif not basis:
                dropped.append(f"{name} {i + 1}: 근거 지표가 없음")
            else:
                kept.append({"text": it["text"].strip(), "basis": basis})
        out[key] = kept
    summary = d.get("summary") if isinstance(d.get("summary"), str) else None
    if summary and unknown_numbers(summary, allowed):
        dropped.append("결론 한 문장: 비교표에 없는 숫자")
        summary = None
    out["summary"] = summary
    out["peers"] = [r["corp_name"] for r in comparison["rows"] if not r["is_target"]]
    has_any = any(out[k] for k, _ in GROUPS)
    status = "ok" if has_any else "empty"
    return _usage(Outcome(status, out, message=None if has_any else "비교 해석이 검사를 통과하지 못했습니다", warnings=dropped), r)
