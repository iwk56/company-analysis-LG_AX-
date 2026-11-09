"""손익계산서 주석 내역 (2026-11-04, 실적 탭 '왜 이렇게 됐나'). AI 없이 코드로 읽는다.

사업보고서 원문(document.xml)의 연결재무제표 주석 중 세 개:
- 판매비와관리비 내역 (급여·지급수수료·감가상각비·경상개발비 …)
- 금융수익 및 금융비용 (이자·배당·외환차이·금융상품평가손익·파생상품손익 …)
- 기타수익·기타비용(기타영업외수익과 비용) (유형자산처분손익·손상차손·기부금 …)
DART XBRL 주석은 "당기 | (단위 : 백만원)" 다음에 "항목 | 금액" 줄이 오고, 이어서 "전기 | (단위 : …)" 블록이 온다.
소계·합계 줄에서 묶음(예: 금융수익 / 금융비용)을 나눈다. 같은 이름(외환차이, 기타)이 묶음마다 있어 묶음 이름을 붙여 구분한다.
"""
import re

from .dart_docs import financial_notes, note_text

UNITS = {"원": 1, "천원": 1_000, "백만원": 1_000_000, "십억원": 1_000_000_000, "억원": 100_000_000}
NOTES = (  # (키, 제목 키워드들 — 앞에서부터 찾는다)
    ("sga", ("판매비와관리비", "판매비와일반관리비")),
    ("finance", ("금융수익및금융비용", "금융수익과금융비용", "금융손익", "금융수익", "금융원가")),
    ("other", ("기타영업외수익", "기타수익및기타비용", "기타수익과기타비용", "기타손익", "기타수익")),
)
_PERIOD = re.compile(r"^(당기|전기)\s*\|\s*\(단위\s*:\s*([^)]+)\)")
_ROW = re.compile(r"^([^|]+?)\s*\|\s*(\(?-?[\d,]+\)?|-)\s*$")
_TOTAL = re.compile(r"(소계|합계|총계)$")
# 소계 뒤에 오는 합계 성격 줄(예: 판매비와관리비 = 소계 + 경상개발비, 순금융손익)과 참고 줄(연구개발비 총지출액·개발비 자산화)
_GRAND = re.compile(r"^(판매비와관리비|판매비와일반관리비|순금융손익|순금융수익|순금융원가|금융손익)$")
_MEMO = re.compile(r"(총지출액|자산화|환율변동효과)")


def _amount(text: str, unit: int) -> int | None:
    t = text.strip()
    if t in ("-", ""):
        return 0
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").replace(",", "")
    try:
        v = int(t)
    except ValueError:
        return None
    return (-v if neg else v) * unit


def parse_note(text: str) -> dict | None:
    """주석 하나 → {"current": [(묶음, 항목, 원)], "prior": [...]}. 당기 블록을 못 찾으면 None."""
    out: dict[str, list] = {"current": [], "prior": []}
    period, unit, group = None, 1, None
    for raw in text.splitlines():
        line = raw.strip()
        m = _PERIOD.match(line)
        if m:
            period = "current" if m.group(1) == "당기" else "prior"
            unit = UNITS.get(re.sub(r"\s", "", m.group(2)), 1)
            group = None
            continue
        if period is None:
            continue
        r = _ROW.match(line)
        if not r:
            continue
        label, value = re.sub(r"\s+", " ", r.group(1)).strip(), _amount(r.group(2), unit)
        if value is None:
            continue
        name = re.sub(r"\s", "", label)
        if _TOTAL.search(name):
            g = _TOTAL.sub("", name) or "합계"
            # 소계 줄 앞의 묶음 이름 없는 항목에 묶음 이름을 붙인다
            for i, (grp, lab, v) in enumerate(out[period]):
                if grp is None:
                    out[period][i] = (g, lab, v)
            out[period].append((g, label, value))
            group = None
            continue
        out[period].append((group, label, value))
    if not out["current"]:
        return None
    return out


def changes(parsed: dict) -> list[dict]:
    """당기·전기를 (묶음, 항목)으로 맞춰 증감. 소계·합계 줄은 is_total로 표시한다."""
    prior = {(g, lab): v for g, lab, v in parsed["prior"]}
    rows = []
    for g, lab, v in parsed["current"]:
        p = prior.get((g, lab))
        name = re.sub(r"\s", "", lab)
        if _MEMO.search(name):
            continue  # 판관비에 더해지지 않는 참고 줄은 증감 표에 넣지 않는다
        rows.append({"group": g, "item": lab, "current": v, "prior": p, "change": None if p is None else v - p,
                     "is_total": bool(_TOTAL.search(name) or _GRAND.match(name))})
    return rows


def collect(xml: str | None) -> dict:
    """{키: {"title", "rows"}} — 찾은 주석만. 하나도 없으면 빈 dict."""
    notes = financial_notes(xml or "") if xml else None
    if not notes:
        return {}
    out = {}
    for key, words in NOTES:
        text = next((t for w in words if (t := note_text(notes, w))), None)
        parsed = parse_note(text) if text else None
        if parsed:
            out[key] = {"title": text.splitlines()[0].strip(), "rows": changes(parsed)}
    return out
