"""보고서 서술 섹션을 DART 공시 원문(OpenDART document.xml)에서 자동으로 만든다 (2026-11-04, PDF 올리기 대신).

- 올릴 보고서(기준 사업연도 N의 사업보고서 + N+1년 최근 반기/3분기보고서)는 pdf_uploads.fetch_guide가 공시 목록에서 고른다
- 원문 zip은 dart_docs가 data/dart_docs에 저장해 다시 받지 않는다
- 섹션 8개(II-1~II-7, IV)는 PDF와 같은 키·이름으로 만들어 report_pdfs에 같은 모양으로 저장한다 → 8-D(AI 추출·인용 확인)는 그대로 쓴다
- 원문 XML에는 쪽 번호가 없어 pages는 [{page: None, text}] 한 덩어리이고, 인용 출처는 "2025 사업보고서 II-7 기타 참고사항" + 공시뷰어 링크가 된다
"""
import hashlib
import re
from datetime import date
from html import unescape

import httpx

from .dart_docs import _SECTION, _TAG, financial_notes, load_document_zip, main_document, note_text, to_text
from .pdf_reader import AI_INPUT_LIMIT, BUSINESS, SECTIONS, _strip_number
from .pdf_uploads import fetch_guide

PERIOD_END = {"annual": (12, 31), "half": (6, 30), "q3": (9, 30)}


def split_xml(xml: str) -> list[dict]:
    """원문 XML → PDF와 같은 모양의 섹션 8개. 못 찾은 섹션도 found=False로 넣는다."""
    heads = [(m.start(), int(m.group(1)[-1]), _strip_number(unescape(_TAG.sub("", m.group(2))))) for m in _SECTION.finditer(xml)]

    def cut(i: int) -> str:
        start, rank, _ = heads[i]
        end = next((s for s, lv, _ in heads[i + 1:] if lv <= rank), len(xml))
        return to_text(xml[start:end])

    def index(name: str, under_business: bool) -> int | None:
        if not under_business:
            return next((i for i, (_, lv, t) in enumerate(heads) if lv == 1 and t == name), None)
        parent = next((i for i, (_, lv, t) in enumerate(heads) if lv == 1 and t == BUSINESS), None)
        if parent is None:
            return None
        for i in range(parent + 1, len(heads)):
            if heads[i][1] <= 1:
                return None
            if heads[i][1] == 2 and heads[i][2] == name:
                return i
        return None

    out = []
    for key, label, name, under_business in SECTIONS:
        i = index(name, under_business)
        text = cut(i) if i is not None else ""
        found = bool(text)
        out.append({"key": key, "label": label, "found": found, "title": label if found else None, "page_start": None, "page_end": None,
                    "chars": len(text), "over_limit": len(text) > AI_INPUT_LIMIT, "pages": [{"page": None, "text": text}] if found else []})
    # 사업 구조 탭(2026-11-04): 연결재무제표 주석의 영업부문 정보(부문별 매출·영업이익, 주요 고객 매출)도 섹션으로 둔다
    notes = financial_notes(xml)
    seg = (note_text(notes, "영업부문") or note_text(notes, "부문")) if notes else None
    out.append({"key": "segment_note", "label": "III. 연결재무제표 주석 · 영업부문", "found": bool(seg), "title": "영업부문" if seg else None,
                "page_start": None, "page_end": None, "chars": len(seg or ""), "over_limit": len(seg or "") > AI_INPUT_LIMIT,
                "pages": [{"page": None, "text": seg}] if seg else []})
    return out


def to_record(item: dict, slot: str, xml: str) -> dict:
    """report_pdfs에 저장할 모양 (pdf_uploads.to_record와 같은 키)."""
    year = item["year"]
    m, d = PERIOD_END.get(item["kind"], (12, 31))
    return {"slot": slot, "file_name": f"DART 공시 원문 · {item['title']} ({item['date']} 제출)",
            "sha256": hashlib.sha256(xml.encode("utf-8")).hexdigest(), "page_count": 0, "kind": item["kind"],
            "corrected": "정정" in item["title"], "period_start": date(year, 1, 1), "period_end": date(year, m, d),
            "checks": [{"key": "source", "label": "출처", "ok": True, "message": f"DART 공시 원문 자동 수집 (접수번호 {item['rcept_no']})"}],
            "revenue_check": None, "split_method": "dart_xml", "sections": split_xml(xml)}


async def fetch_records(client: httpx.AsyncClient, corp_code: str) -> tuple[int | None, list[dict]]:
    """(기준 사업연도, [사업보고서, 반기/3분기보고서 기록]). 사업보고서가 없으면 (None, [])."""
    guide = await fetch_guide(client, corp_code)
    out = []
    for slot in ("annual", "interim"):
        item = guide.get(slot)
        if not item:
            continue
        zip_bytes = await load_document_zip(client, item["rcept_no"])
        out.append(to_record(item, slot, main_document(zip_bytes, item["rcept_no"])))
    return guide["base_year"], out
