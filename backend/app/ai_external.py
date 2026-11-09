"""Phase 7-B AI 해석: 외부 환경(PEST·5 Forces·공시 주제·민감도·지켜볼 점) → SWOT·종합 평가 → 4페이지 과제·기여.

규칙 (docs/spec.md 0장, 3장 "경제 환경 민감도", F4 3·4페이지)
- AI에게는 코드가 정리한 자료만 넘긴다. 네이버 기사는 넘기지 않는다(0장 규칙 10).
- 넘긴 자료마다 근거 키를 붙이고, AI는 항목마다 근거 키를 돌려준다. 목록에 없는 키는 버리고, 근거가 하나도 남지 않은 항목은 버린다.
- 넘기지 않은 숫자가 든 문장은 버린다(6-A와 같음). 버린 이유는 warnings에 남긴다.
- 화면에 보이는 근거 이름·링크, 공시 날짜·링크, 4페이지 근거 섹션 이름은 코드가 붙인다(AI가 쓰지 않는다).
"""
import re
from dataclasses import dataclass

import httpx

from . import ai_prompts as P
from .ai_facts import Facts, pct
from .ai_tasks import Outcome, _clean_text, _failed, _usage, ask
from .ai_verify import numbers_in
from .dart_docs import find_section
from .llm import LlmError

# 사업보고서 "II. 사업의 내용"에서 넘길 절과 최대 글자 수 (산업 특성·시장 여건·경쟁은 '기타 참고사항 > 업계의 현황'에 있다)
BUSINESS_PARTS = (("사업의개요", "사업의 개요", 1500), ("원재료및생산설비", "원재료 및 생산설비", 2000), ("기타참고사항", "기타 참고사항 (업계의 현황 등)", 8000))
PEST_KEYS = ("politics", "economy", "society", "technology")
FORCE_KEYS = (("rivalry", "기존 경쟁"), ("new_entrants", "신규 진입 위협"), ("substitutes", "대체재 위협"),
              ("supplier_power", "공급자 교섭력"), ("buyer_power", "구매자 교섭력"))
STRENGTHS = ("강", "중", "약")
DIRECTIONS = ("긍정", "부정", "혼재", "자료 없음")
EXTERNAL_SUMMARY_KEYS = ("pest", "five_forces", "topics", "macro")  # watch(면접 질문)는 2026-11-04 삭제
SWOT_KEYS = ("strengths", "weaknesses", "opportunities", "threats")
ROLE_KEYS = ("fpa", "accounting", "treasury", "research")
MAX_TOPICS = 3
MAX_TASKS = 3
# 자기소개서식 표현 (spec F4 4페이지: 자기소개서 문장은 쓰지 않는다). 걸리면 그 줄을 버린다.
SELF_INTRO = re.compile(r"저는|제가|저의|저만의|입사|지원\s*동기|지원하|기여하겠|하겠습니다|열정|포부|제 역량|저희")


@dataclass
class Src:
    """AI에게 넘기는 자료 한 덩어리. key는 AI가 근거로 고르는 이름, label·url은 화면에 코드가 붙인다."""
    key: str
    label: str
    text: str
    url: str | None = None


def business_text(xml: str | None) -> str | None:
    if not xml:
        return None
    parts = []
    for keyword, label, limit in BUSINESS_PARTS:
        text = find_section(xml, keyword)
        if text:
            parts.append(f"<{label}>\n{text[:limit]}")
    return "\n\n".join(parts) or None


def _fx_text(series: dict, digits: int, unit: str) -> tuple[str, float | None]:
    pts = series.get("points") or []
    if len(pts) < 2:
        return f"{series['label']}: 자료 없음", None
    a, b = pts[0], pts[-1]
    change = b["value"] / a["value"] - 1 if a["value"] else None
    fmt = lambda v: f"{v:,.{digits}f}{unit}"  # noqa: E731
    text = f"{series['label']}: {a['date']} {fmt(a['value'])} → {b['date']} {fmt(b['value'])}"
    if unit == "원" and change is not None:
        text += f" (1년 변화 {pct(change, True)})"
    return text, change


def external_sources(report: dict, facts: Facts, business: str | None, disclosures: dict | None,
                     export_share: float | None = None, pdf_business: str | None = None) -> tuple[dict[str, Src], dict]:
    """외부 환경 호출에 넘길 자료와 민감도 표에 쓸 코드 값. (근거 키 → 자료, {"export_share", "fx"})
    export_share: 6-A 사업부문 추출의 해외 매출 비중(코드 계산). 없으면 민감도는 '자료 없음'.
    pdf_business: 올린 사업보고서 PDF에서 고른 사업의 내용(8-D). 있으면 DART 원문(business) 대신 쓴다.
    경쟁사 비교 결과(calc:competitors)는 넘기지 않는다(2026-11-03 방향 조정, spec F4)."""
    annual = next((s for s in report["sources"] if s["kind"] == "annual_report" and s["year"] == report["base_year"]), None)
    aurl, y = (annual or {}).get("url"), report["base_year"]
    srcs: dict[str, Src] = {}

    def add(key: str, label: str, text: str | None, url: str | None = aurl) -> None:
        if text:
            srcs[key] = Src(key, label, text, url)

    add("pdf:business", f"{y} 사업보고서 · 사업의 내용", pdf_business)
    add("dart:business", f"{y} 사업보고서 · 사업의 내용", business)
    add("dart:segments", f"{y} 사업보고서 · 매출 구분 (AI 추출, 비중은 코드 계산)", facts.blocks.get("segments"))
    add("calc:core", "1페이지 핵심 지표·신호등 (코드 계산)", facts.blocks.get("core_cards"))
    add("calc:trend", "2페이지 실적 추이 (코드 계산)", facts.blocks.get("trend"))
    add("calc:ratios", "2페이지 재무비율 (코드 계산)", facts.blocks.get("ratios"))
    add("calc:cashflow", "2페이지 현금흐름 패턴 (코드 계산)", facts.blocks.get("cashflow"))
    sens = {"export_share": export_share, "fx": None}
    for m in report.get("macro") or []:
        if m["key"] == "usd_krw":
            text, change = _fx_text(m, 1, "원")
            add("ecos:fx", "한국은행 ECOS · 원/달러 환율 (최근 1년)", text, m["source_url"])
            pts = m.get("points") or []
            if change is not None:
                sens["fx"] = {"start_date": pts[0]["date"], "start": pts[0]["value"], "end_date": pts[-1]["date"], "end": pts[-1]["value"], "change": change}
        elif m["key"] == "base_rate":
            add("ecos:rate", "한국은행 ECOS · 기준금리 (최근 1년)", _fx_text(m, 2, "%")[0], m["source_url"])
    if disclosures and disclosures["items"]:
        lines = [f"기간 {disclosures['period_start']} ~ {disclosures['period_end']} (접수번호 | 접수일 | 제출인 | 보고서명)"]
        lines += [f"{d['rcept_no']} | {d['date']} | {d['filer']} | {d['title']}" for d in disclosures["items"]]
        add("dart:disclosures", f"DART 최근 3개월 공시 목록 ({disclosures['period_start']} ~ {disclosures['period_end']})", "\n".join(lines),
            "https://dart.fss.or.kr")
    return srcs, sens


def _allowed(srcs: dict[str, Src]) -> set[str]:
    out: set[str] = set()
    for s in srcs.values():
        out |= numbers_in(s.text)
    return out


def _request_message(task_text: str, srcs: dict[str, Src], request: str = "") -> str:
    """[근거 키 목록] + 근거 키를 붙인 자료."""
    keys = P.source_list({k: s.label for k, s in srcs.items()})
    body = {f"{s.label} (근거 키 {k})": s.text for k, s in srcs.items()}
    return P.user_message(task_text, {"근거 키 목록": keys, **body}, request)


def _keys(raw, valid) -> list[str]:
    return list(dict.fromkeys(k for k in (raw if isinstance(raw, list) else []) if isinstance(k, str) and k in valid))


def _item(raw, srcs: dict[str, Src], allowed: set[str], where: str, dropped: list[str]) -> dict | None:
    """{"text", "sources"} 한 항목 검증. 문장이 비었거나, 없는 숫자가 있거나, 근거 키가 없으면 None."""
    if not isinstance(raw, dict):
        return None
    text = _clean_text(raw.get("text"), allowed, where, dropped)
    if not text:
        return None
    keys = _keys(raw.get("sources"), srcs)
    if not keys:
        dropped.append(f"{where}: 근거 키가 없거나 목록에 없음")
        return None
    return {"text": text, "sources": keys}


def _items(raw, limit: int, srcs, allowed, where, dropped) -> list[dict]:
    out = [it for i, r in enumerate(raw if isinstance(raw, list) else []) if (it := _item(r, srcs, allowed, f"{where} {i + 1}", dropped))]
    return out[:limit]


def source_index(srcs: dict[str, Src], used: set[str]) -> dict[str, dict]:
    """화면용 근거 이름·링크 (코드가 붙인다)."""
    return {k: {"label": srcs[k].label, "url": srcs[k].url} for k in srcs if k in used}


def _used_keys(obj) -> set[str]:
    if isinstance(obj, dict):
        out = set(obj.get("sources") or []) if isinstance(obj.get("sources"), list) else set()
        for k, v in obj.items():
            if k != "sources":
                out |= _used_keys(v)
        return out
    if isinstance(obj, list):
        return set().union(*(_used_keys(v) for v in obj)) if obj else set()
    return set()


# ───────────────────────── 호출 A: 외부 환경
async def write_external(client: httpx.AsyncClient, srcs: dict[str, Src], sens: dict, disclosures: dict | None) -> Outcome:
    allowed = _allowed(srcs)
    with_sens = sens["export_share"] is not None and sens["fx"] is not None
    request = ("민감도 작성: 수출(해외 매출) 비중과 환율 자료가 있으니 sensitivity를 작성하세요." if with_sens
               else "민감도 작성 안 함: 수출 비중 또는 환율 자료가 없으니 sensitivity는 null로 두세요.")
    try:
        r = await ask(client, "write_external", "write", _request_message(P.WRITE_EXTERNAL, srcs, request))
    except LlmError as e:
        return _failed(e)
    d, dropped = r.data, []

    pest_raw = d.get("pest") if isinstance(d.get("pest"), dict) else {}
    pest = {k: _items(pest_raw.get(k), 3, srcs, allowed, f"PEST {k}", dropped) for k in PEST_KEYS}  # 2026-11-04: 항목마다 3개

    forces = []
    ff_raw = d.get("five_forces") if isinstance(d.get("five_forces"), dict) else {}
    for key, name in FORCE_KEYS:
        f = ff_raw.get(key)
        if not isinstance(f, dict):
            continue
        if f.get("strength") not in STRENGTHS:
            dropped.append(f"5 Forces {name}: 강도가 강·중·약이 아님")
            continue
        item = _item({"text": f.get("reason"), "sources": f.get("sources")}, srcs, allowed, f"5 Forces {name}", dropped)
        if item:
            forces.append({"key": key, "name": name, "strength": f["strength"], "reason": item["text"], "sources": item["sources"]})

    by_rcept = {x["rcept_no"]: x for x in (disclosures or {}).get("items", [])}
    topics = []
    for i, t in enumerate(d.get("topics") if isinstance(d.get("topics"), list) else []):
        if not isinstance(t, dict) or len(topics) >= MAX_TOPICS:
            continue
        found = [by_rcept[n] for n in dict.fromkeys(t.get("rcept_nos") or []) if isinstance(n, str) and n in by_rcept]
        title = _clean_text(t.get("title"), allowed, f"공시 주제 {i + 1} 이름", dropped)
        summary = _clean_text(t.get("summary"), allowed, f"공시 주제 {i + 1} 요약", dropped)
        if not found:
            dropped.append(f"공시 주제 {i + 1}: 목록에 있는 공시 접수번호가 없음")
        elif title and summary:
            found.sort(key=lambda x: x["date"])
            topics.append({"title": title, "summary": summary,
                           "disclosures": [{k: x[k] for k in ("rcept_no", "title", "date", "url")} for x in found]})

    sensitivity = None
    if with_sens and isinstance(d.get("sensitivity"), dict):
        s = d["sensitivity"]
        keys = _keys(s.get("sources"), srcs)
        sides = {}
        for side, label in (("revenue", "매출"), ("cost", "원가")):
            v = s.get(side) if isinstance(s.get(side), dict) else {}
            reason = _clean_text(v.get("reason"), allowed, f"민감도 {label}", dropped)
            if v.get("direction") in DIRECTIONS and reason:
                sides[side] = {"direction": v["direction"], "reason": reason}
            elif v and v.get("direction") not in DIRECTIONS:
                dropped.append(f"민감도 {label}: 방향이 긍정·부정·혼재·자료 없음 중 하나가 아님")
        if not keys:
            dropped.append("민감도: 근거 키가 없거나 목록에 없음")
        elif sides:
            sensitivity = {**sides, "sources": keys}
    sens_out = {"export_share": sens["export_share"], "fx": sens["fx"], "available": with_sens, **(sensitivity or {})}

    summaries = {}
    for k in EXTERNAL_SUMMARY_KEYS:
        text = _clean_text((d.get("summaries") or {}).get(k), allowed, f"요약 {k}", dropped)
        if text:
            summaries[k] = text

    content = {"pest": pest, "five_forces": forces, "topics": topics, "sensitivity": sens_out, "summaries": summaries,
               "disclosure_period": {k: (disclosures or {}).get(k) for k in ("period_start", "period_end", "total")}}
    if not any(pest.values()) and not forces and not topics:
        return Outcome("failed", message="AI 문장이 근거가 없거나 자료에 없는 숫자를 포함해 사용하지 않았습니다: " + "; ".join(dropped[:5]),
                       warnings=dropped)
    content["source_index"] = source_index(srcs, _used_keys(content))
    return _usage(Outcome("ok", content, warnings=dropped), r)


def external_text(ext: dict) -> dict[str, str]:
    """외부 환경 결과 → SWOT·4페이지 호출에 넘길 문단 (근거 키 → 문단). 이미 검증된 문장만 들어 있다."""
    out = {}
    names = {"politics": "정책", "economy": "경제", "society": "사회", "technology": "기술"}
    pest = [f"{names[k]}: {it['text']}" for k in PEST_KEYS for it in ext["pest"].get(k, [])]
    if pest:
        out["p3:pest"] = "\n".join(pest)
    if ext["five_forces"]:
        out["p3:five_forces"] = "\n".join(f"{f['name']} {f['strength']}: {f['reason']}" for f in ext["five_forces"])
    for i, t in enumerate(ext["topics"], 1):
        dates = ", ".join(sorted({x["date"] for x in t["disclosures"]}))
        out[f"p3:topic{i}"] = f"{t['title']} (공시일 {dates}): {t['summary']}"
    s = ext["sensitivity"]
    if s.get("available"):
        lines = [f"수출(해외 매출) 비중 {pct(s['export_share'])}, 원/달러 환율 1년 변화 {pct(s['fx']['change'], True)}"]
        for side, label in (("revenue", "매출"), ("cost", "원가")):
            if s.get(side):
                lines.append(f"환율 10% 상승 시 {label}: {s[side]['direction']} — {s[side]['reason']}")
        out["p3:sensitivity"] = "\n".join(lines)
    return out


# ───────────────────────── 호출 B: SWOT + 종합 한 줄 평가
def swot_sources(report: dict, facts: Facts, ext: dict, accounting_text: str | None,
                 extra: dict[str, tuple[str, str]] | None = None) -> dict[str, Src]:
    """extra: 8-D 근거 (pdf:position·pdf:mda·pdf:focus·pdf:risks, check:* 체크리스트) — 근거 키 → (이름, 문단)."""
    srcs, _ = external_sources(report, facts, None, None)  # 사업의 내용·공시 목록은 빼고 1~2페이지 결과와 지표만
    aurl = srcs["calc:core"].url if "calc:core" in srcs else None
    if facts.blocks.get("recent_results"):
        srcs["calc:recent"] = Src("calc:recent", "2페이지 최근 실적 (코드 계산)", facts.blocks["recent_results"], aurl)
    if accounting_text:
        srcs["calc:accounting"] = Src("calc:accounting", "2페이지 회계 이슈 체크 (코드 판정)", accounting_text, aurl)
    labels = {"p3:pest": "3페이지 PEST", "p3:five_forces": "3페이지 5 Forces", "p3:sensitivity": "3페이지 경제 환경 민감도"}
    for k, text in external_text(ext).items():
        label = labels.get(k) or f"3페이지 공시 주제 {k[-1]}"
        srcs[k] = Src(k, label, text, None)
    for k, (label, text) in (extra or {}).items():
        if text:
            srcs[k] = Src(k, label, text, aurl)
    return srcs


async def write_swot(client: httpx.AsyncClient, srcs: dict[str, Src]) -> Outcome:
    allowed = _allowed(srcs)
    try:
        r = await ask(client, "write_swot", "write", _request_message(P.WRITE_SWOT, srcs))
    except LlmError as e:
        return _failed(e)
    d, dropped = r.data, []
    raw = d.get("swot") if isinstance(d.get("swot"), dict) else {}
    names = {"strengths": "강점", "weaknesses": "약점", "opportunities": "기회", "threats": "위협"}
    swot = {k: _items(raw.get(k), 3, srcs, allowed, f"SWOT {names[k]}", dropped) for k in SWOT_KEYS}
    verdict = _clean_text(d.get("verdict"), allowed, "종합 평가", dropped)
    if not verdict and not any(swot.values()):
        return Outcome("failed", message="AI 문장이 근거가 없거나 자료에 없는 숫자를 포함해 사용하지 않았습니다: " + "; ".join(dropped[:5]),
                       warnings=dropped)
    content = {"verdict": verdict, "swot": swot}
    content["source_index"] = source_index(srcs, _used_keys(content))
    return _usage(Outcome("ok", content, warnings=dropped), r)


# ───────────────────────── 호출 C: 4페이지 과제·역량·직무별 기여
