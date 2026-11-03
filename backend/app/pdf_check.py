"""올린 PDF 확인 규칙 (docs/spec.md F2 "PDF 확인 규칙"). 코드만 쓰고 AI는 쓰지 않는다.

① 글자를 읽을 수 있는가 ② 보고서 종류 ③ 회사(정식 회사명) ④ 사업연도 기간 — 하나라도 다르면 거절
⑤ 요약재무정보 매출액을 DART 값과 대조 — 다르거나 못 찾으면 경고만

표지는 책갈피 중 제목이 "사업보고서·반기보고서·분기보고서"인 쪽, 책갈피가 없으면 앞 10쪽 중 "사업연도"가 있는 첫 쪽이다
(DART PDF는 1~3쪽이 목차라 표지가 4쪽, 정정 보고서는 목차 4쪽 + "정정신고(보고)" + 확인서 뒤라 7쪽). 비교할 때 공백을 모두 지운다
(표지 제목이 "사 업 보 고 서"처럼 글자 사이가 띄어져 있다). 12월 결산을 가정한다(spec 6장 확인 필요 6).
"""
import re
from dataclasses import dataclass, field
from datetime import date

from .pdf_reader import TOC_LINE, PdfDoc, find_page, norm

COVER_PAGES = 10  # 책갈피가 없을 때 표지를 찾는 범위
HEAD_PAGES = 5
MIN_TEXT_CHARS = 20  # 앞 5쪽의 공백 뺀 글자가 이보다 적으면 스캔본·이미지로 본다

ANNUAL, HALF, Q3, Q1 = "annual", "half", "q3", "q1"
KIND_LABELS = {ANNUAL: "사업보고서", HALF: "반기보고서", Q3: "3분기보고서", Q1: "1분기보고서"}
SLOT_LABELS = {"annual": "사업보고서", "interim": "반기/3분기보고서"}
TITLES = (("사업보고서", ANNUAL), ("반기보고서", HALF), ("분기보고서", "quarter"))

UNREADABLE = "글자를 읽을 수 없는 PDF입니다. DART 공시뷰어에서 받은 PDF를 올려 주세요"
REVENUE_NAMES = ("매출액", "영업수익", "수익(매출액)", "매출")
UNITS = (("백만원", 1_000_000), ("천원", 1_000), ("원", 1))


def strip_company(name: str) -> str:
    """회사명 비교용: 띄어쓰기·"주식회사"·"(주)"·"㈜"를 지운다."""
    s = norm(name)
    for w in ("주식회사", "(주)", "㈜"):
        s = s.replace(w, "")
    return s


@dataclass
class Cover:
    page: int  # 1부터
    kind: str | None  # annual | half | q3 | q1 | None(못 찾음)
    corrected: bool  # 정정 보고서 ([기재정정] 또는 "정정신고(보고)"가 앞에 붙음)
    company: str | None
    start: date | None
    end: date | None


@dataclass
class CheckResult:
    readable: bool
    cover: Cover | None
    checks: list[dict] = field(default_factory=list)  # [{key, label, ok: True | False | None(확인 안 함), message}]

    @property
    def accepted(self) -> bool:
        return bool(self.checks) and all(c["ok"] is True for c in self.checks)

    @property
    def reasons(self) -> list[str]:
        return [c["message"] for c in self.checks if c["ok"] is False]


def _date(y: str, m: str, d: str) -> date | None:
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def _cover_pages(doc: PdfDoc) -> list[int]:
    """표지 후보 쪽(0부터): 책갈피의 보고서 제목 쪽을 먼저, 그다음 앞 10쪽."""
    marked = [p - 1 for _lv, title, p in doc.outline
              if p and 1 <= p <= len(doc.pages) and norm(title).replace("[기재정정]", "") in ("사업보고서", "반기보고서", "분기보고서")]
    return list(dict.fromkeys(marked + list(range(min(COVER_PAGES, len(doc.pages))))))


def _is_corrected(doc: PdfDoc, cover_text: str) -> bool:
    """정정 보고서: 표지 제목의 [기재정정], 또는 책갈피·앞쪽의 "정정신고(보고)" (2026-11-03 LG전자 [정정] 사업보고서에서 확인)."""
    if "기재정정" in cover_text:
        return True
    if any("정정신고" in norm(title) for _lv, title, _p in doc.outline):
        return True
    return any(norm(page).startswith("정정신고") for page in doc.pages[:COVER_PAGES])


def read_cover(doc: PdfDoc) -> Cover | None:
    for i in _cover_pages(doc):
        page = doc.pages[i]
        t = norm(page)
        if "사업연도" not in t:
            continue
        found = [(t.find(title), kind) for title, kind in TITLES if title in t]
        kind = min(found)[1] if found else None
        s = re.search(r"(\d{4})년(\d{1,2})월(\d{1,2})일부터", t)
        e = re.search(r"(\d{4})년(\d{1,2})월(\d{1,2})일까지", t)
        start, end = (_date(*s.groups()) if s else None), (_date(*e.groups()) if e else None)
        if kind == "quarter":  # 분기보고서는 기간 끝 달로 1분기·3분기를 나눈다 (반기는 제목이 따로 있다)
            kind = Q3 if end and end.month == 9 else Q1 if end and end.month == 3 else None
        line = re.search(r"^\s*회\s*사\s*명\s*:\s*(.+?)\s*$", page, re.M)  # 화면에 보여줄 원래 모양
        packed = re.search(r"회사명:(.+?)(대표이사|본점소재지|$)", t)
        company = re.sub(r"\s+", " ", line.group(1)) if line else packed.group(1) if packed else None
        return Cover(page=i + 1, kind=kind, corrected=_is_corrected(doc, t), company=company, start=start, end=end)
    return None


def _expected_period(slot: str, kind: str, base_year: int) -> tuple[date, date] | None:
    if slot == "annual":
        return date(base_year, 1, 1), date(base_year, 12, 31)
    if kind == HALF:
        return date(base_year + 1, 1, 1), date(base_year + 1, 6, 30)
    if kind == Q3:
        return date(base_year + 1, 1, 1), date(base_year + 1, 9, 30)
    return None


def _kind_check(slot: str, kind: str | None) -> dict:
    label = {"key": "kind", "label": "보고서 종류"}
    if kind is None:
        return {**label, "ok": False, "message": "표지에서 보고서 종류(사업보고서·반기보고서·분기보고서)를 찾지 못했습니다"}
    if slot == "annual" and kind != ANNUAL:
        return {**label, "ok": False, "message": f"사업보고서 칸에는 사업보고서를 올려 주세요 (이 PDF는 {KIND_LABELS[kind]}입니다)"}
    if slot == "interim" and kind == ANNUAL:
        return {**label, "ok": False, "message": "반기/3분기 칸에는 반기보고서 또는 3분기보고서를 올려 주세요 (이 PDF는 사업보고서입니다)"}
    if slot == "interim" and kind == Q1:
        return {**label, "ok": False, "message": "1분기보고서는 받지 않습니다. 반기보고서 또는 3분기보고서를 올려 주세요"}
    return {**label, "ok": True, "message": KIND_LABELS[kind]}


def _company_check(cover: Cover, official_name: str) -> dict:
    label = {"key": "company", "label": "회사"}
    if not cover.company:
        return {**label, "ok": False, "message": "표지에서 회사명을 찾지 못했습니다"}
    if strip_company(cover.company) != strip_company(official_name):
        return {**label, "ok": False,
                "message": f"다른 회사의 보고서입니다 (표지 회사명: {cover.company}, 선택한 기업의 정식 회사명: {official_name})"}
    return {**label, "ok": True, "message": cover.company}


def _period_check(slot: str, cover: Cover, base_year: int, kind_ok: bool) -> dict:
    label = {"key": "period", "label": "사업연도 기간"}
    if not kind_ok:  # 종류가 맞지 않으면 기간은 판단하지 않는다 (이유는 종류 확인에 나온다)
        return {**label, "ok": None, "message": "보고서 종류가 맞지 않아 확인하지 않음"}
    if cover.start is None or cover.end is None:
        return {**label, "ok": False, "message": "표지에서 사업연도 기간을 찾지 못했습니다"}
    shown = f"{cover.start.isoformat()} ~ {cover.end.isoformat()}"
    expected = _expected_period(slot, cover.kind, base_year)
    if (cover.start, cover.end) == expected:
        return {**label, "ok": True, "message": shown}
    want = (f"{base_year} 사업보고서" if slot == "annual" else f"{base_year + 1} 반기보고서 또는 3분기보고서")
    if cover.start.month == 1 and cover.start.day == 1 and cover.end.month in (6, 9, 12):
        return {**label, "ok": False,
                "message": f"이 PDF는 {cover.end.year} {KIND_LABELS[cover.kind]}입니다. {want}를 올려 주세요"}
    return {**label, "ok": False,
            "message": f"사업연도 기간({shown})이 기대한 기간({expected[0].isoformat()} ~ {expected[1].isoformat()})과 다릅니다. "
                       "12월 결산 기업만 확인할 수 있습니다"}


def verify(doc: PdfDoc, slot: str, official_name: str, base_year: int) -> CheckResult:
    """확인 ①~④. slot: annual(사업보고서 칸) | interim(반기/3분기 칸). base_year: 기준 사업연도 N."""
    head = sum(len(norm(p)) for p in doc.pages[:HEAD_PAGES])
    readable = {"key": "readable", "label": "글자 읽힘", "ok": head >= MIN_TEXT_CHARS,
                "message": "읽힘" if head >= MIN_TEXT_CHARS else UNREADABLE}
    if not readable["ok"]:
        return CheckResult(False, None, [readable])
    cover = read_cover(doc)
    if cover is None:
        return CheckResult(True, None, [readable, {"key": "cover", "label": "표지", "ok": False,
                                                    "message": "책갈피와 앞 10쪽에서 표지(사업연도가 적힌 쪽)를 찾지 못했습니다. "
                                                               "DART 공시뷰어에서 받은 PDF를 올려 주세요"}])
    kind = _kind_check(slot, cover.kind)
    return CheckResult(True, cover, [readable, kind, _company_check(cover, official_name),
                                     _period_check(slot, cover, base_year, kind["ok"])])


# ───────── ⑤ 요약재무정보 매출액 대조 (경고만)
def _amount(text: str) -> float | None:
    t = text.strip()
    neg = t.startswith("(") or t.startswith("-")
    digits = re.sub(r"[^\d]", "", t)
    if not digits:
        return None
    return -float(digits) if neg else float(digits)


def find_summary_revenue(doc: PdfDoc, consolidated: bool) -> tuple[float | None, int | None, int | None]:
    """(매출액 원 단위, 쪽 번호 1부터, 단위) — "III-1 요약재무정보"의 첫 열(당기 또는 당기 누적). 못 찾으면 (None, 쪽, None)."""
    p = find_page(doc, "요약재무정보")
    if p is None:
        return None, None, None
    lines = [x for page in doc.pages[p:p + 2] for x in page.split("\n") if not TOC_LINE.search(x)]
    want = "요약연결재무정보" if consolidated else "요약재무정보"
    start = next((i for i, x in enumerate(lines) if want in norm(x) and (consolidated or "연결" not in norm(x))
                  and not re.match(r"^\d+\.요약재무정보$", norm(x))), None)  # "1. 요약재무정보" 장 제목 말고 "가./나." 표 제목
    if start is None:  # 연결 표 제목을 못 찾으면 첫 요약 표를 쓴다
        start = next((i for i, x in enumerate(lines) if "요약" in norm(x) and "재무정보" in norm(x)), 0)
    unit = None
    for x in lines[start:]:
        if "단위" in x:
            unit = next((v for name, v in UNITS if name in norm(x)), None)
            break
    names = "|".join(re.escape(n) for n in REVENUE_NAMES)
    row = re.compile(rf"^\s*(?:{names})\s+([\(\-]?[\d,]+\)?)")
    for x in lines[start:]:
        m = row.match(x)
        if m:
            value = _amount(m.group(1))
            return (value * unit if value is not None and unit else None), p + 1, unit
    return None, p + 1, unit


def compare_revenue(doc: PdfDoc, dart_won: float | None, consolidated: bool) -> dict:
    """{"status": match | mismatch | not_found, "message", "pdf_won", "dart_won", "page"}. 단위 반올림 차이는 허용한다."""
    pdf_won, page, unit = find_summary_revenue(doc, consolidated)
    base = {"pdf_won": pdf_won, "dart_won": dart_won, "page": page}
    if pdf_won is None or dart_won is None:
        why = ("DART 값이 없음" if dart_won is None and pdf_won is not None
               else "PDF 요약재무정보에서 매출액을 찾지 못함" if pdf_won is None and page is not None
               else "PDF에서 요약재무정보를 찾지 못함" if page is None else "DART 값이 없음")
        return {**base, "status": "not_found", "message": f"재무 숫자를 대조하지 못했습니다 ({why})"}
    if abs(pdf_won - dart_won) < (unit or 1):
        return {**base, "status": "match", "message": f"재무 숫자 일치 (요약재무정보 매출액, {page}쪽)"}
    return {**base, "status": "mismatch",
            "message": f"재무 숫자를 대조하지 못했습니다 (요약재무정보 매출액이 DART 값과 다름, {page}쪽)"}
