"""사업보고서·반기/3분기보고서 PDF 읽기: 쪽별 글자, 책갈피(목차), 서술 섹션 8개 나누기 (docs/spec.md F2·F3 "PDF에서 읽는 섹션").

- 라이브러리는 pdfplumber(MIT). pypdf는 표를 쪽 맨 끝으로 보내 섹션 경계가 틀어져 쓰지 않는다(8-C 비교, progress.md)
- 쪽 번호는 PDF 뷰어의 쪽 번호(1부터). DART PDF는 1~3쪽이 목차라 인쇄된 "Page N"보다 3 크다
- 섹션 경계는 책갈피를 먼저 쓰고, 책갈피가 없으면 본문 제목 줄(목차의 점선 줄 제외)로 찾는다. 같은 쪽 안의 시작·끝은 제목 줄 위치로 자른다
- AI 입력 길이 상한(12,000자)은 8-D에서 자른다. 여기서는 전체를 저장하고 넘는지만 표시한다
"""
import io
import re
from dataclasses import dataclass

import pdfplumber
from pdfminer.pdftypes import resolve1
from pdfminer.psparser import PSLiteral

AI_INPUT_LIMIT = 12_000  # 섹션당 AI 입력 상한 (spec F3)
FOOTER = re.compile(r"^\s*전자공시시스템\s*dart\.fss\.or\.kr\s*Page\s*\d+\s*$")
TOC_LINE = re.compile(r"\.{4,}\s*\d+\s*$")  # 목차의 "제목 ........ 12" 줄
ROMAN = re.compile(r"^(XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I)\.(.+)$")
NUMBERED = re.compile(r"^(\d+)\.(.+)$")
ROMAN_ORDER = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII")

# II. 사업의 내용 아래 하위 목차 (DART 서식 공통). 본문 제목으로 찾을 때 경계로 쓴다
BUSINESS_PARTS = ("사업의개요", "주요제품및서비스", "원재료및생산설비", "매출및수주상황", "위험관리및파생거래",
                  "주요계약및연구개발활동", "기타참고사항")
BUSINESS = "사업의내용"
MDA = "이사의경영진단및분석의견"

# (키, 화면 이름, 찾을 제목(공백 제거), II 아래인지)
SECTIONS = (
    ("business_overview", "II-1 사업의 개요", "사업의개요", True),
    ("products", "II-2 주요 제품 및 서비스", "주요제품및서비스", True),  # 1장 주력 사업 (2026-11-03 추가)
    ("materials_facilities", "II-3 원재료 및 생산설비", "원재료및생산설비", True),
    ("sales_orders", "II-4 매출 및 수주상황", "매출및수주상황", True),
    ("risk_derivatives", "II-5 위험관리 및 파생거래", "위험관리및파생거래", True),
    ("contracts_rnd", "II-6 주요계약 및 연구개발활동", "주요계약및연구개발활동", True),
    ("other_info", "II-7 기타 참고사항", "기타참고사항", True),
    ("mda", "IV. 이사의 경영진단 및 분석의견", MDA, False),
)


class PdfReadError(Exception):
    """PDF가 아니거나 열 수 없는 파일."""


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


@dataclass
class PdfDoc:
    pages: list[str]  # 쪽별 글자 (0번 = 1쪽)
    outline: list[tuple[int, str, int | None]]  # 책갈피 (깊이, 제목, 쪽 번호 1부터). 없으면 빈 목록


def extract(data: bytes) -> PdfDoc:
    """쪽별 글자와 책갈피를 읽는다. 411쪽 사업보고서에 약 10초 (호출하는 쪽에서 스레드로 돌린다)."""
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
            outline = _outline(pdf)
    except Exception as e:  # 손상·암호·PDF 아님 (pdfminer는 종류가 여러 가지라 모두 받는다)
        raise PdfReadError(type(e).__name__) from None
    return PdfDoc(pages, outline)


def _outline(pdf) -> list[tuple[int, str, int | None]]:
    ids = {p.page_obj.pageid: i + 1 for i, p in enumerate(pdf.pages)}
    out = []
    try:
        for level, title, dest, action, _se in pdf.doc.get_outlines():
            out.append((level, (title or "").strip(), _dest_page(pdf.doc, dest, action, ids)))
    except Exception:  # 책갈피가 없거나(PDFNoOutlines) 깨졌으면 본문 제목으로 찾는다
        return []
    return out


def _dest_page(doc, dest, action, ids: dict) -> int | None:
    d = dest
    if d is None and action is not None:
        a = resolve1(action)
        d = a.get("D") if isinstance(a, dict) else None
    d = resolve1(d)
    if isinstance(d, (bytes, str, PSLiteral)):  # 이름 붙은 목적지
        try:
            d = resolve1(doc.get_dest(d.name if isinstance(d, PSLiteral) else d))
        except Exception:
            return None
    if isinstance(d, dict):
        d = resolve1(d.get("D"))
    if isinstance(d, list) and d and hasattr(d[0], "objid"):
        return ids.get(d[0].objid)
    return None


# ───────── 섹션 나누기
@dataclass
class Mark:
    """경계가 되는 제목 줄. level 1 = 로마 숫자 장, 2 = 그 아래 번호 목차."""
    level: int
    title: str
    page: int  # 0부터
    line: int  # 그 쪽의 몇 번째 줄


def _lines(page: str) -> list[str]:
    return page.split("\n")


def _find_line(page: str, title: str) -> int | None:
    lines = [norm(x) for x in _lines(page)]
    t = norm(title)
    for i, x in enumerate(lines):
        if x == t:
            return i
    for i, x in enumerate(lines):
        if x.startswith(t) and not TOC_LINE.search(x):
            return i
    return None


def _marks_from_outline(doc: PdfDoc) -> list[Mark]:
    marks = []
    for level, title, page in doc.outline:
        if page is None or not 1 <= page <= len(doc.pages):
            continue
        p, line = page - 1, _find_line(doc.pages[page - 1], title)
        if line is None and page < len(doc.pages):  # 책갈피가 앞쪽 맨 아래를 가리키고 제목은 다음 쪽 첫머리인 경우 (LG 2025 사업보고서 II-3: 55 → 56쪽)
            nxt = _find_line(doc.pages[page], title)
            if nxt is not None:
                p, line = page, nxt
        marks.append(Mark(level, title, p, 0 if line is None else line))
    if not marks:
        return []
    top = min(m.level for m in marks)
    for m in marks:  # pdfminer 깊이는 1부터지만 PDF마다 다를 수 있어 맨 위를 1로 맞춘다
        m.level = m.level - top + 1
    return marks


def _marks_from_headings(doc: PdfDoc) -> list[Mark]:
    """책갈피가 없을 때: 로마 숫자 장 제목과 II장 하위 목차 제목 줄을 찾는다(목차 쪽의 점선 줄은 건너뛴다).

    장 제목은 쪽의 첫 줄에 있고(DART PDF는 장마다 새 쪽에서 시작) 번호가 앞 장보다 큰 줄만 본다
    (표 안의 "I. 매출액 97,146,675", "V. 영업이익" 같은 줄을 거른다).
    """
    marks: list[Mark] = []
    in_business = False
    chapter = 0  # 다음 장 번호는 이것 이상이어야 한다
    for p, page in enumerate(doc.pages):
        first = next((i for i, x in enumerate(_lines(page)) if x.strip()), None)
        for i, raw in enumerate(_lines(page)):
            if TOC_LINE.search(raw) or FOOTER.match(raw):
                continue
            line = norm(raw)
            if len(line) > 40:
                continue
            r = ROMAN.match(line)
            if r and i == first and ROMAN_ORDER.index(r.group(1)) >= chapter:
                chapter = ROMAN_ORDER.index(r.group(1)) + 1
                marks.append(Mark(1, raw.strip(), p, i))
                in_business = r.group(2) == BUSINESS
                continue
            n = NUMBERED.match(line)
            if in_business and n and n.group(2) in BUSINESS_PARTS:
                marks.append(Mark(2, raw.strip(), p, i))
    return marks


def _strip_number(title: str) -> str:
    t = norm(title)
    m = ROMAN.match(t) or NUMBERED.match(t)
    return m.group(2) if m else t


def _target_index(marks: list[Mark], name: str, under_business: bool) -> int | None:
    if not under_business:
        return next((i for i, m in enumerate(marks) if m.level == 1 and _strip_number(m.title) == name), None)
    parent = next((i for i, m in enumerate(marks) if m.level == 1 and _strip_number(m.title) == BUSINESS), None)
    if parent is None:
        return None
    for i in range(parent + 1, len(marks)):
        if marks[i].level <= marks[parent].level:
            return None
        if marks[i].level == marks[parent].level + 1 and _strip_number(marks[i].title) == name:
            return i
    return None


def _has_content_before(page: str, line: int) -> bool:
    return any(x.strip() and not FOOTER.match(x) for x in _lines(page)[:line])


def _cut(doc: PdfDoc, start: Mark, end: Mark | None) -> tuple[list[dict], int, int]:
    """(쪽별 글자 [{page, text}], 시작 쪽, 끝 쪽). 쪽 번호는 1부터. 꼬리말 줄은 뺀다."""
    last_page = end.page if end else len(doc.pages) - 1
    chunks = []
    for p in range(start.page, last_page + 1):
        lines = _lines(doc.pages[p])
        lo = start.line if p == start.page else 0
        hi = end.line if (end and p == end.page) else len(lines)
        text = "\n".join(x for x in lines[lo:hi] if not FOOTER.match(x)).strip()
        if text:
            chunks.append({"page": p + 1, "text": text})
    page_end = last_page + 1
    if end and not _has_content_before(doc.pages[end.page], end.line) and end.page > start.page:
        page_end = end.page  # 다음 제목이 쪽 맨 위에서 시작하면 그 앞쪽에서 끝난다
    return chunks, start.page + 1, page_end


def split_sections(doc: PdfDoc) -> tuple[str, list[dict]]:
    """(나눈 방법 'bookmarks' | 'headings', 섹션 목록). 못 찾은 섹션도 found=False로 목록에 넣는다."""
    marks = _marks_from_outline(doc)
    method = "bookmarks"
    if _target_index(marks, BUSINESS_PARTS[0], True) is None:  # 책갈피가 없거나 II장 아래 목차가 없으면
        marks, method = _marks_from_headings(doc), "headings"
    sections = []
    for key, label, name, under_business in SECTIONS:
        i = _target_index(marks, name, under_business)
        if i is None:
            sections.append({"key": key, "label": label, "found": False, "title": None, "page_start": None,
                             "page_end": None, "chars": 0, "over_limit": False, "pages": []})
            continue
        end = next((m for m in marks[i + 1:] if m.level <= marks[i].level), None)
        chunks, p0, p1 = _cut(doc, marks[i], end)
        chars = sum(len(c["text"]) for c in chunks)
        sections.append({"key": key, "label": label, "found": True, "title": marks[i].title, "page_start": p0,
                         "page_end": p1, "chars": chars, "over_limit": chars > AI_INPUT_LIMIT, "pages": chunks})
    return method, sections


def find_page(doc: PdfDoc, name: str) -> int | None:
    """제목(공백 제거, 번호 제외)으로 쪽 번호(0부터)를 찾는다. 책갈피 → 본문 제목 줄 순서."""
    for _level, title, page in doc.outline:
        if page and _strip_number(title) == name:
            return page - 1
    for p, page in enumerate(doc.pages):
        for raw in _lines(page):
            if not TOC_LINE.search(raw) and _strip_number(raw) == name:
                return p
    return None
